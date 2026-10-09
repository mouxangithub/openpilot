"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""
Tests for the full vision curve-speed envelope ported from CarrotPilot.

``curve_speed`` and ``VisionCurveSpeed`` are pure geometry/state, so these need no
cereal runtime, no SubMaster and no car - only model-shaped arrays. Run with:

    cd /e/sp && PYTHONPATH=. python -m pytest \\
      openpilot/sunnypilot/carrot/tests/test_curve_speed.py -q

What is worth asserting here is not "the code runs" but the four properties that
separate this envelope from a bare v = sqrt(a_lat / kappa) lookup:

  * a straight road reports NO limit rather than a number,
  * the limit depends on how far away the curve is, not only on its radius,
  * unusable geometry is None, never confused with "no constraint",
  * the ceiling releases only against several fresh frames, never on one.
"""
import math
import unittest

import numpy as np

from openpilot.selfdrive.modeld.constants import ModelConstants
from openpilot.sunnypilot.carrot.curve_speed import (
  NO_LIMIT_KPH,
  CurveSpeed,
  VisionCurveSpeed,
  curve_speed,
)

N = ModelConstants.IDX_N
T_IDXS = ModelConstants.T_IDXS


class _Seq:
  """Minimal length/index iterable so the module sees model-shaped arrays."""

  def __init__(self, values):
    self._v = list(values)

  def __len__(self):
    return len(self._v)

  def __iter__(self):
    return iter(self._v)

  def __getitem__(self, i):
    return self._v[i]


class _Model:
  def __init__(self, x, y, z, vx, yaw):
    self.position = type("P", (), {"x": _Seq(x), "y": _Seq(y), "z": _Seq(z)})()
    self.velocity = type("V", (), {"x": _Seq(vx)})()
    self.orientationRate = type("O", (), {"z": _Seq(yaw)})()


def straight(v_ego: float) -> _Model:
  return _Model([v_ego * t for t in T_IDXS], [0.0] * N, [0.0] * N, [v_ego] * N, [0.0] * N)


def arc(v_ego: float, radius: float, start_m: float = 0.0) -> _Model:
  """Straight until ``start_m``, then a constant-radius arc (yaw rate = v / R)."""
  x, y, yaw = [0.0] * N, [0.0] * N, [0.0] * N
  for i, t in enumerate(T_IDXS):
    d = v_ego * t
    if d <= start_m or radius <= 0.0:
      x[i], y[i], yaw[i] = d, 0.0, 0.0
      continue
    ang = (d - start_m) / radius
    x[i] = start_m + radius * math.sin(ang)
    y[i] = radius * (1 - math.cos(ang))
    yaw[i] = v_ego / radius
  return _Model(x, y, [0.0] * N, [v_ego] * N, yaw)


class TestCurveSpeedGeometry(unittest.TestCase):
  def test_straight_road_reports_no_constraint(self):
    r = curve_speed(straight(20.0), 20.0, 1.0, 30.0)
    self.assertIsNotNone(r)
    self.assertEqual(r.approach_kph, NO_LIMIT_KPH)
    self.assertEqual(r.curve_kph, NO_LIMIT_KPH)

  def test_curve_constrains_below_the_sentinel(self):
    r = curve_speed(arc(20.0, 60.0), 20.0, 1.0, 30.0)
    self.assertIsNotNone(r)
    self.assertLess(r.curve_kph, NO_LIMIT_KPH)

  def test_limit_depends_on_distance_to_the_curve(self):
    """The envelope is distance-aware; an argmax lookup is not.

    Same radius and speed, only the lead-in differs. The farther curve must permit
    more speed now, because there is more braking room to spend.
    """
    near = curve_speed(arc(10.0, 60.0, start_m=20.0), 10.0, 1.0, 30.0)
    far = curve_speed(arc(10.0, 60.0, start_m=45.0), 10.0, 1.0, 30.0)
    self.assertIsNotNone(near)
    self.assertIsNotNone(far)
    self.assertGreater(far.approach_kph, near.approach_kph)

  def test_envelope_is_not_a_bare_curve_lookup(self):
    """Guard against the reduced implementation creeping back in.

    If ``approach_kph`` were pinned to ``curve_kph`` the two distances above would
    report the same number, so this test would fail. That is the mutation the
    distance-aware assertion is there to catch.
    """
    near = curve_speed(arc(10.0, 60.0, start_m=20.0), 10.0, 1.0, 30.0)
    self.assertNotAlmostEqual(near.approach_kph, near.curve_kph, places=3)

  def test_higher_sensitivity_slows_more(self):
    gentle = curve_speed(arc(20.0, 60.0), 20.0, 1.0, 30.0)
    aggressive = curve_speed(arc(20.0, 60.0), 20.0, 1.5, 30.0)
    self.assertLess(aggressive.curve_kph, gentle.curve_kph)

  def test_lower_limit_floor_is_respected(self):
    r = curve_speed(arc(20.0, 5.0), 20.0, 1.0, 60.0)
    self.assertIsNotNone(r)
    self.assertGreaterEqual(r.curve_kph, 60.0 - 1e-6)

  def test_single_frame_yaw_spike_does_not_anchor_the_result(self):
    """The three-node median must reject one isolated spike."""
    m = straight(20.0)
    m.orientationRate.z._v[10] = 5.0
    r = curve_speed(m, 20.0, 1.0, 30.0)
    self.assertIsNotNone(r)
    self.assertGreater(r.curve_kph, 60.0)

  def test_unusable_geometry_is_none_not_a_limit(self):
    """None means "unknown"; a caller must not read it as a straight road."""
    self.assertIsNone(curve_speed(straight(20.0), 20.0, 0.0, 30.0), "sensitivity <= 0")
    self.assertIsNone(curve_speed(straight(20.0), float("nan"), 1.0, 30.0), "NaN v_ego")
    self.assertIsNone(curve_speed(straight(20.0), -1.0, 1.0, 30.0), "negative v_ego")
    short = _Model([1.0] * 5, [0.0] * 5, [0.0] * 5, [20.0] * 5, [0.0] * 5)
    self.assertIsNone(curve_speed(short, 20.0, 1.0, 30.0), "wrong-length path")

  def test_nan_position_is_rejected(self):
    m = straight(20.0)
    m.position.x._v[3] = float("nan")
    self.assertIsNone(curve_speed(m, 20.0, 1.0, 30.0))


class TestVisionCurveSpeedHold(unittest.TestCase):
  def setUp(self):
    self.v = VisionCurveSpeed()
    self.curve = curve_speed(arc(20.0, 60.0), 20.0, 1.0, 30.0)
    self.straight = curve_speed(straight(20.0), 20.0, 1.0, 30.0)

  def test_tightens_on_the_first_frame(self):
    self.assertEqual(self.v.update(self.curve, 1.0, model_time=1.0), self.curve.approach_kph)

  def test_one_straight_frame_does_not_release(self):
    held = self.v.update(self.curve, 1.0, model_time=1.0)
    after = self.v.update(self.straight, 1.05, model_time=1.05)
    self.assertEqual(after, held)

  def test_sustained_straight_geometry_releases(self):
    held = self.v.update(self.curve, 1.0, model_time=1.0)
    for t in (1.10, 1.20, 1.35, 1.50):
      last = self.v.update(self.straight, t, model_time=t)
    self.assertGreater(last, held)

  def test_reReading_one_model_frame_is_not_an_exit(self):
    """Two calls on the same model stamp cannot confirm the road straightened."""
    self.v.update(self.curve, 2.0, model_time=2.0)
    before = self.v.speed
    self.v.update(self.straight, 2.1, model_time=2.0)
    self.assertEqual(self.v.speed, before)

  def test_missing_geometry_holds_then_ramps_out(self):
    held = self.v.update(self.curve, 3.0, model_time=3.0)
    self.assertEqual(self.v.update(None, 3.1), held)
    late = self.v.update(None, 3.6)
    self.assertGreater(late, held)

  def test_direction_is_carried_from_the_geometry(self):
    left = curve_speed(arc(20.0, 60.0), 20.0, 1.0, 30.0)
    out = self.v.update(left, 4.0, model_time=4.0)
    self.assertEqual(math.copysign(1.0, out), math.copysign(1.0, left.direction * 1.0))


class TestNoLimitSentinel(unittest.TestCase):
  def test_default_curvespeed_is_unconstrained(self):
    d = CurveSpeed()
    self.assertEqual(d.approach_kph, NO_LIMIT_KPH)
    self.assertEqual(d.curve_kph, NO_LIMIT_KPH)
    self.assertEqual(d.distance, 0.0)

  def test_frozen(self):
    with self.assertRaises(Exception):
      CurveSpeed().approach_kph = 1.0


if __name__ == "__main__":
  unittest.main()
