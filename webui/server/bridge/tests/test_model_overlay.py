"""Unit tests for model overlay serialization helpers."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("WEBUI_DEV_PC", "1")

from webui.server.bridge.model_overlay import (  # noqa: E402
  _digest_geometry,
  _finalize_overlay,
  _limit_gradient,
  _quantize_poly,
  overlay_frame_key,
  snapshot_model_overlay,
)


class ModelOverlayTests(unittest.TestCase):
  def test_quantize_poly(self) -> None:
    poly = _quantize_poly([[1.23456, 9.87654]])
    self.assertEqual(poly, [[1.2, 9.9]])

  def test_limit_gradient(self) -> None:
    stops = [{"pos": i / 20, "rgba": [i, i, i, 255]} for i in range(21)]
    limited = _limit_gradient(stops, max_stops=16)
    self.assertEqual(len(limited), 16)

  def test_dev_snapshot_has_frame_key(self) -> None:
    frame = snapshot_model_overlay(800, 600)
    self.assertTrue(frame["ok"])
    self.assertIn("frame_key", frame)
    self.assertGreater(len(frame["lanes"]), 0)

  def test_frame_key_stable_for_same_geometry(self) -> None:
    payload = {
      "model_mono_time": 123,
      "width": 800,
      "height": 600,
      "experimental": False,
      "rainbow": False,
      "allow_throttle": True,
      "path_blend": 1.0,
      "chevron_alpha": 0.0,
      "lanes": [{"prob": 0.9, "polygon": [[1.0, 2.0], [3.0, 4.0]]}],
      "edges": [],
      "path_polygon": [[0.0, 1.0], [1.0, 2.0]],
      "path_gradient": [],
      "leads": [],
    }
    a = _finalize_overlay({**payload})
    b = _finalize_overlay({**payload})
    self.assertEqual(a["frame_key"], b["frame_key"])
    self.assertEqual(overlay_frame_key(a), overlay_frame_key(b))

  def test_clear_frame_key(self) -> None:
    frame = {"clear": True, "frame_key": "thermal:800x600"}
    self.assertEqual(overlay_frame_key(frame), "thermal:800x600")

  def test_digest_changes_with_geometry(self) -> None:
    base = {
      "model_mono_time": 1,
      "width": 800,
      "height": 600,
      "experimental": False,
      "rainbow": False,
      "allow_throttle": True,
      "path_blend": 1.0,
      "chevron_alpha": 0.0,
      "lanes": [{"prob": 0.9, "polygon": [[1.0, 2.0]]}],
      "edges": [],
      "path_polygon": [],
      "path_gradient": [],
      "leads": [],
    }
    other = {**base, "lanes": [{"prob": 0.9, "polygon": [[2.0, 2.0]]}]}
    self.assertNotEqual(_digest_geometry(base), _digest_geometry(other))

  def test_digest_accepts_nanosecond_mono_time(self) -> None:
    """Regression: `model_mono_time` is cereal logMonoTime in nanoseconds, so it
    passes 2**32 after ~4.3 s of uptime. Packing it as 32-bit made every
    non-empty overlay frame raise struct.error (HTTP 500)."""
    frame = {
      "model_mono_time": 26_049_708_786_700,   # ~7.2 h uptime, ns
      "width": 2100,
      "height": 1020,
      "experimental": True,
      "rainbow": True,
      "allow_throttle": True,
      "lanes": [],
      "edges": [],
      "path_polygon": [],
      "path_gradient": [],
      "leads": [],
    }
    digest = _digest_geometry(frame)          # must not raise
    self.assertEqual(len(digest), 16)


if __name__ == "__main__":
  unittest.main()
