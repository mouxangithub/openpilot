"""Tests for the cabana truth extraction layer (ai/services/cabana/truth.py)."""

from __future__ import annotations

import ai.tests.bootstrap_pc  # noqa: F401  # PC mocks before ai imports
import contextlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from ai.services.cabana import truth
from ai.tests.cabana_fixtures import (
  FakeLogReader,
  T0_ABS,
  accel_long_at,
  make_truth_messages,
  speed_at,
  yaw_at,
)


class TruthExtractionTest(unittest.TestCase):
  def _stack(self, messages: list, cache_dir: str | None = None) -> contextlib.ExitStack:
    stack = contextlib.ExitStack()
    stack.enter_context(patch.object(truth, "_route_dir", return_value=Path("fake/route")))
    stack.enter_context(patch.object(truth, "_find_qlogs", return_value=[Path("fake/route/qlog")]))
    stack.enter_context(patch.object(truth, "_find_rlogs", return_value=[]))
    stack.enter_context(patch.object(truth, "LogReader", lambda _path: FakeLogReader(messages)))
    if cache_dir is not None:
      stack.enter_context(patch.object(truth, "_cabana_cache_dir", return_value=Path(cache_dir)))
    return stack

  def test_extracts_series_with_absolute_time(self):
    msgs = make_truth_messages(duration_sec=20.0)
    with self._stack(msgs):
      out = truth._extract_truth_series("route")
    self.assertTrue(out["available"])
    accel = out["series"][truth.ACCEL_LONG]
    self.assertEqual(len(accel["t"]), len(accel["v"]))
    self.assertGreater(len(accel["t"]), 1000)
    # Absolute seconds come straight from logMonoTime/1e9.
    self.assertAlmostEqual(accel["t"][0], T0_ABS, delta=0.05)
    # Values follow the fixture physical profile (v[0] = longitudinal accel).
    self.assertAlmostEqual(max(accel["v"]), accel_long_at(0.0), delta=0.01)
    vert = out["series"][truth.ACCEL_VERT]
    self.assertTrue(all(abs(v) < 0.1 for v in vert["v"][:100]))  # gravity removed
    yaw = out["series"][truth.YAW_RATE]
    self.assertAlmostEqual(max(yaw["v"]), max(yaw_at(t) for t in (0.0, 1.75)), delta=0.01)
    gps = out["series"][truth.GPS_SPEED]
    self.assertAlmostEqual(max(gps["v"]), max(speed_at(t) for t in (0.0, 2.5)) + 0.05, delta=0.01)

  def test_series_frequencies(self):
    msgs = make_truth_messages(duration_sec=30.0, accel_hz=100.0, gps_hz=10.0)
    with self._stack(msgs):
      out = truth._extract_truth_series("route")
    accel = out["series"][truth.ACCEL_LONG]
    span = accel["t"][-1] - accel["t"][0]
    self.assertAlmostEqual(len(accel["t"]) / span, 100.0, delta=1.0)
    gps = out["series"][truth.GPS_SPEED]
    span = gps["t"][-1] - gps["t"][0]
    self.assertAlmostEqual(len(gps["t"]) / span, 10.0, delta=0.2)

  def test_legacy_log_fallback(self):
    msgs = make_truth_messages(duration_sec=10.0, style="legacy")
    with self._stack(msgs):
      out = truth._extract_truth_series("route")
    self.assertTrue(out["available"])
    self.assertTrue(out["series"][truth.ACCEL_LONG]["t"])
    self.assertTrue(out["series"][truth.YAW_RATE]["t"])
    self.assertTrue(out["series"][truth.GPS_SPEED]["t"])

  def test_no_sensor_messages_degrades(self):
    msgs = make_truth_messages(duration_sec=1.0, style="none")
    with self._stack(msgs):
      out = truth._extract_truth_series("route")
    self.assertFalse(out["available"])
    self.assertTrue(out["note"])

  def test_gps_accel_derived(self):
    msgs = make_truth_messages(duration_sec=20.0)
    with self._stack(msgs):
      out = truth._extract_truth_series("route")
    ga = out["series"][truth.GPS_ACCEL]
    self.assertTrue(ga["t"])
    self.assertAlmostEqual(max(ga["v"]), accel_long_at(0.0), delta=0.3)

  def test_series_decimated_to_max_points(self):
    ts = [float(i) for i in range(25000)]
    vs = [float(i) for i in range(25000)]
    out_t, out_v = truth._decimate_series(ts, vs)
    self.assertLessEqual(len(out_t), truth.TRUTH_MAX_POINTS)
    self.assertEqual(len(out_t), len(out_v))
    self.assertEqual(out_t[0], 0.0)

  def test_sensor_v_rejects_short_vectors(self):
    from ai.tests.cabana_fixtures import _FakeSensorEvent

    self.assertIsNone(truth._sensor_v(_FakeSensorEvent("acceleration", [1.0, 2.0])))
    self.assertIsNone(truth._sensor_v("not-an-event"))


class TruthCacheTest(unittest.TestCase):
  def setUp(self):
    self._tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self._tmp.cleanup)
    self.msgs = make_truth_messages(duration_sec=5.0)

  def _stack(self, reader_factory) -> contextlib.ExitStack:
    stack = contextlib.ExitStack()
    stack.enter_context(patch.object(truth, "_route_dir", return_value=Path("fake/route")))
    stack.enter_context(patch.object(truth, "_find_qlogs", return_value=[Path("fake/route/qlog")]))
    stack.enter_context(patch.object(truth, "_find_rlogs", return_value=[]))
    stack.enter_context(patch.object(truth, "LogReader", reader_factory))
    stack.enter_context(patch.object(truth, "_cabana_cache_dir", return_value=Path(self._tmp.name)))
    return stack

  def test_cache_hit_avoids_log_reader(self):
    calls = []

    def factory(_path):
      calls.append(1)
      return FakeLogReader(self.msgs)

    with self._stack(factory):
      first = truth._load_truth_cached("route")
    self.assertTrue(first and first["available"])
    self.assertEqual(len(calls), 1)

    def factoryboom(_path):
      raise AssertionError("LogReader must not be opened on cache hit")

    with self._stack(factoryboom):
      second = truth._load_truth_cached("route")
    self.assertEqual(second, {k: first[k] for k in ("available", "note", "series")})

  def test_unavailable_truth_not_cached(self):
    msgs = make_truth_messages(duration_sec=1.0, style="none")
    with self._stack(lambda _p: FakeLogReader(msgs)):
      out = truth._load_truth_cached("route")
    self.assertFalse(out["available"])
    # Nothing cached: a fresh call re-reads the log without error.
    with self._stack(lambda _p: FakeLogReader(msgs)):
      again = truth._load_truth_cached("route")
    self.assertFalse(again["available"])

  def test_missing_route_returns_none(self):
    with patch.object(truth, "_route_dir", return_value=None):
      self.assertIsNone(truth._load_truth_cached("nope"))


if __name__ == "__main__":
  unittest.main()
