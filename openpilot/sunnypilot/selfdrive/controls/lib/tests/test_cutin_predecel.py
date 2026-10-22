"""cutin_predecel: bounded negative accel ceiling for strong early cut-in risk.
Reads RadarState.leadCutInRisk (sp uses `present`, cp used `status`)."""
import unittest
from types import SimpleNamespace as NS

from openpilot.sunnypilot.selfdrive.controls.lib.cutin_predecel import (
  apply_cutin_predecel_accel_limit, get_cutin_predecel_accel_limit,
)


def _lead(d=30.0, v=-8.0, score=0.5, radar=True, present=True, use_status=False):
  kw = {"status": present} if use_status else {"present": present}
  return NS(dRel=d, vRel=v, score=score, radar=radar, **kw)


def _radar(lead=None):
  return NS(leadCutInRisk=lead)


class TestGetCutinPredecelLimit(unittest.TestCase):
  def test_no_lead_is_none(self):
    self.assertIsNone(get_cutin_predecel_accel_limit(_radar(None)))

  def test_not_present_is_none(self):
    self.assertIsNone(get_cutin_predecel_accel_limit(_radar(_lead(present=False))))

  def test_status_alias_supported(self):
    self.assertIsNotNone(get_cutin_predecel_accel_limit(_radar(_lead(use_status=True))))

  def test_vision_only_lead_ignored(self):
    self.assertIsNone(get_cutin_predecel_accel_limit(_radar(_lead(radar=False))))

  def test_low_score_ignored(self):
    self.assertIsNone(get_cutin_predecel_accel_limit(_radar(_lead(score=0.05))))

  def test_receding_lead_ignored(self):
    self.assertIsNone(get_cutin_predecel_accel_limit(_radar(_lead(v=2.0))))

  def test_close_fast_approach_is_bounded(self):
    lim = get_cutin_predecel_accel_limit(_radar(_lead(d=5.0, v=-20.0, score=0.9)))
    self.assertIsNotNone(lim)
    self.assertTrue(-0.65 <= lim <= -0.25)

  def test_far_slow_approach_is_gentle(self):
    lim = get_cutin_predecel_accel_limit(_radar(_lead(d=60.0, v=-1.0, score=0.9)))
    self.assertIsNotNone(lim)
    self.assertTrue(-0.65 <= lim <= -0.25)


class TestApplyCutinPredecelLimit(unittest.TestCase):
  def test_no_limit_uses_normal_step(self):
    # without a limit, cap stays but accel cannot drop faster than 0.05/plan
    self.assertEqual(apply_cutin_predecel_accel_limit(1.0, 0.0, None), 1.0)
    self.assertEqual(apply_cutin_predecel_accel_limit(1.0, 0.0, None), max(1.0, -0.05))

  def test_limit_lowers_cap(self):
    out = apply_cutin_predecel_accel_limit(1.0, -0.5, -0.3)
    self.assertLessEqual(out, 0.0)

  def test_never_raises_above_normal(self):
    out = apply_cutin_predecel_accel_limit(2.0, 0.0, -0.4)
    self.assertLessEqual(out, 2.0)


if __name__ == "__main__":
  unittest.main()
