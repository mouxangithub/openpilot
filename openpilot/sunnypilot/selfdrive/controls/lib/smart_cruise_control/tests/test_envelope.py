import numpy as np
import unittest

from openpilot.sunnypilot.selfdrive.controls.lib.smart_cruise_control.envelope import (
  EnvelopeController, correct_far_field, extract_curve_profile, CSC_FARFIELD_GAIN)


def flat_model(n=33, curvature=0.01, speed=25.0):
  """A modelV2 stand-in: constant curve at constant speed."""
  class _Vec:
    def __init__(self, values):
      self.z = list(values)
      self.x = list(values)
  class _Model:
    pass
  model = _Model()
  model.orientationRate = _Vec([curvature * speed] * n)
  model.velocity = _Vec([speed] * n)
  model.position = _Vec([float(i) * speed * 0.5 for i in range(n)])  # 0.5 s per point
  return model


class TestExtractCurveProfile(unittest.TestCase):
  def test_constant_curve_extracted(self):
    k, d = extract_curve_profile(flat_model(curvature=0.01, speed=25.0))
    self.assertEqual(33, len(k))
    self.assertTrue(np.allclose(k, 0.01))
    self.assertTrue(np.all(np.diff(d) > 0))

  def test_low_speed_zeroes_curvature(self):
    k, _ = extract_curve_profile(flat_model(curvature=0.01, speed=2.0))
    self.assertTrue(np.all(k == 0.0))

  def test_malformed_model_returns_empty(self):
    class _Broken:
      orientationRate = None
    k, d = extract_curve_profile(_Broken())
    self.assertEqual(0, len(k))
    self.assertEqual(0, len(d))


class TestFarField(unittest.TestCase):
  def test_firm_far_points_gained(self):
    ks = np.array([0.005, 0.005, 0.005])
    ds = np.array([10.0, 30.0, 100.0])
    out = correct_far_field(ks, ds)
    self.assertAlmostEqual(0.005, out[0], places=12)
    self.assertAlmostEqual(0.005 * CSC_FARFIELD_GAIN, out[1], places=12)
    self.assertAlmostEqual(0.005 * CSC_FARFIELD_GAIN, out[2], places=12)

  def test_capped_at_profile_max(self):
    out = correct_far_field(np.array([0.09]), np.array([100.0]))
    self.assertLessEqual(out[0], 0.1)


class TestEnvelopeController(unittest.TestCase):
  def setUp(self):
    self.env = EnvelopeController(dt=0.05)

  def test_empty_plan_returns_none(self):
    self.assertIsNone(self.env.compute(20.0, 30.0, np.array([]), np.array([]), lambda k: 2.0))

  def test_binding_point_slows_for_far_curve(self):
    # A sharp curve 200 m out: approach speed from the envelope must sit below
    # the curve point speed (decel headroom) and above zero.
    n = 33
    ks = np.array([0.0] * (n - 10) + [0.02] * 10)
    ds = np.linspace(50.0, 200.0, n)[::-1]  # nearest point first
    target = self.env.compute(25.0, 33.0, ks, ds, lambda k: 2.5)
    self.assertIsNotNone(target)
    self.assertLess(target, 33.0)
    self.assertGreater(target, 5.0)

  def test_rate_limited_downward(self):
    n = 33
    ks = np.array([0.0] * 5 + [0.02] * (n - 5))
    ds = np.linspace(10.0, 300.0, n)
    first = self.env.compute(30.0, 33.0, ks, ds, lambda k: 2.0)
    second = self.env.compute(30.0, 33.0, ks, ds, lambda k: 2.0)
    self.assertLess(second, first)
    self.assertGreaterEqual(first - second, 2.5 * 0.05 - 1e-9)
    self.assertLessEqual(first - second, 2.5 * 0.05 + 1e-9)  # exactly one step down

  def test_seed_never_below_ego_plus_headroom(self):
    n = 33
    ks = np.array([0.05] * n)
    ds = np.linspace(5.0, 100.0, n)
    target = self.env.compute(30.0, 40.0, ks, ds, lambda k: 2.0)
    self.assertGreaterEqual(target, 30.0)  # v_ego + headroom clamps the seed

  def test_reset_reseeds(self):
    n = 33
    ks = np.array([0.02] * n)
    ds = np.linspace(10.0, 200.0, n)
    self.env.compute(25.0, 33.0, ks, ds, lambda k: 2.0)
    self.env.reset()
    self.assertTrue(self.env._seed_pending)
    self.assertEqual(0.0, self.env.binding_distance)


if __name__ == "__main__":
  unittest.main()
