"""Tests for Lite hardware detection policy."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from ai.system import hardware_lite as hl


class TestHardwareLite(unittest.TestCase):
  def test_lite_env_forces_true(self):
    with patch.dict(os.environ, {"LITE": "1"}, clear=False):
      self.assertTrue(hl.detect_lite_hw())

  def test_lite_write_block(self):
    with patch.object(hl, "detect_lite_hw", return_value=True):
      reason = hl.lite_write_block_reason("RecordAudio")
      self.assertIsNotNone(reason)
      self.assertIn("RecordAudio", reason)

  def test_full_c3_no_block(self):
    with patch.object(hl, "detect_lite_hw", return_value=False):
      self.assertIsNone(hl.lite_write_block_reason("RecordAudio"))

  def test_mici_not_lite(self):
    with patch.object(hl, "_comma_device_slug", return_value="mici"):
      self.assertFalse(hl.detect_lite_hw())

  def test_tizi_not_lite(self):
    with patch.object(hl, "_comma_device_slug", return_value="tizi"):
      with patch.object(hl, "_probe_amp_missing", return_value=True):
        self.assertFalse(hl.detect_lite_hw())

  def test_tici_lite_profile_label(self):
    with patch.object(hl, "detect_lite_hw", return_value=True):
      with patch.object(hl, "_comma_device_slug", return_value="tici"):
        prof = hl.lite_profile()
        self.assertEqual(prof["device_type"], "tici")
        self.assertEqual(prof["product_label"], "C3")
        self.assertTrue(prof["lite_capable"])

  def test_lite_profile_beepd_eligible(self):
    with patch.object(hl, "detect_lite_hw", return_value=True):
      class FakeParams:
        def get(self, key):
          return "1" if key == "SpDevBeep" else None

        def get_bool(self, key):
          return key == "SpDevBeep"

      prof = hl.lite_profile(FakeParams())  # type: ignore[arg-type]
      self.assertTrue(prof["beepd_eligible"])
      self.assertEqual(prof["audio_feedback"], "beepd")
      self.assertIn("RecordAudio", prof["unavailable_params"])


if __name__ == "__main__":
  unittest.main()
