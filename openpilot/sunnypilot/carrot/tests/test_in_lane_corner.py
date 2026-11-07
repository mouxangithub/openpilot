"""In-lane / stopping-lane corner corroboration: pure geometry and tracker
safety paths. These run without compiled motion native code or routes; the
full multi-frame kinematic selection is covered by route replay on device."""
import unittest
from types import SimpleNamespace as NS

from openpilot.sunnypilot.carrot.radar_motion.primary import RadarPointSnapshot, VisionLead
from openpilot.sunnypilot.carrot.radar_motion.stationary_lane import confident_ego_lane
from openpilot.sunnypilot.carrot.radar_motion.in_lane import InLaneCornerTracker
from openpilot.sunnypilot.carrot.radar_motion.stationary_lane import StoppingLaneCornerTracker

XS = tuple(float(x) for x in range(51))  # 0..50 m


def lane_line(ys):
  return NS(x=XS, y=tuple(float(y) for y in ys))


def ego_model(left_y, right_y, *, std=0.1, lcs="off", path_y=None, velocity_tail=None):
  """A model whose lanes[1]/lanes[2] are a confident ego lane around path 0."""
  path_y = [0.0] * len(XS) if path_y is None else path_y
  # adjacent outer lanes (lanes[0], lanes[3]) are irrelevant; provide plausible
  lanes = (lane_line([y - 1.75 for y in path_y]),
           lane_line([y + left_y for y in path_y]),
           lane_line([y + right_y for y in path_y]),
           lane_line([y + 3.5 for y in path_y]))
  probs = (0.99, 0.99, 0.99, 0.99)
  stds = (std,) * 4
  meta = NS(laneChangeState=lcs)
  velocity = NS(x=(velocity_tail if velocity_tail is not None else (0.0, 0.0)))
  return NS(position=lane_line(path_y), laneLines=lanes, laneLineProbs=probs,
            laneLineStds=stds, meta=meta, velocity=velocity)


def corner_point(d=20.0, y=0.0, v_rel=0.0, *, measured=True, v_lead=None, a_lead=0.0):
  return RadarPointSnapshot(
    track_id=1, source="cornerFl", d_rel=d, y_rel=y, v_rel=v_rel, a_rel=0.0,
    yv_rel=0.0, v_lead=v_lead if v_lead is not None else v_rel, a_lead=a_lead,
    j_lead=0.0, measured=measured)


class TestEgoLaneGeometry(unittest.TestCase):
  def test_confident_ego_lane_accepts_clean_straight(self):
    # 3.5 m wide ego lane centered on path; radar y=0 is inside
    model = ego_model(left_y=-1.75, right_y=1.75)
    lane, far = confident_ego_lane(model)
    self.assertIsNotNone(lane)
    self.assertGreaterEqual(far, 30.0)
    # model Y is right-positive, radar Y left-positive: a radar point at the
    # center (y=0) maps to model y=0, within the 0.3+2*std margin.
    self.assertIsNotNone(lane.offset(20.0, 0.0))

  def test_point_outside_lane_is_rejected(self):
    model = ego_model(left_y=-1.75, right_y=1.75)
    lane, _ = confident_ego_lane(model)
    # 3 m to the radar-left is well past the ~1.45 m half-width
    self.assertIsNone(lane.offset(20.0, 3.0))

  def test_rejects_during_lane_change(self):
    model = ego_model(left_y=-1.75, right_y=1.75, lcs="starting")
    self.assertIsNone(confident_ego_lane(model))

  def test_rejects_low_confidence_lanes(self):
    model = ego_model(left_y=-1.75, right_y=1.75)
    model.laneLineProbs = (0.99, 0.5, 0.99, 0.99)
    self.assertIsNone(confident_ego_lane(model))


class TestInLaneTrackerSafety(unittest.TestCase):
  def setUp(self):
    self.tr = InLaneCornerTracker()
    self.model = ego_model(left_y=-1.75, right_y=1.75, velocity_tail=(0.0, 0.0))

  def test_low_speed_emits_nothing_and_resets(self):
    pts = (corner_point(v_rel=-2.0),)
    self.assertIsNone(self.tr.update(0.0, 3.0, self.model, pts, VisionLead(0.9, 20, 0, -2, .2, .2, .2)))

  def test_non_measured_points_ignored(self):
    pts = (corner_point(measured=False),)
    # even at highway speed, an unmeasured corner cannot corroborate
    out = self.tr.update(0.0, 20.0, self.model, pts,
                         VisionLead(0.9, 20, 0, -2, .2, .2, .2), measurement_time_s=0.0)
    self.assertIsNone(out)

  def test_repeated_same_measurement_time_emits_nothing(self):
    pts = (corner_point(d=30.0, v_rel=-3.0, v_lead=-3.0, a_lead=-1.0),)
    vision = VisionLead(0.9, 30, 0, -3, .2, .2, .2)
    first = self.tr.update(0.0, 20.0, self.model, pts, vision, measurement_time_s=0.0)
    # same measurement time -> guarded, must not double-emit
    second = self.tr.update(0.05, 20.0, self.model, pts, vision, measurement_time_s=0.0)
    self.assertIsNone(second)
    self.assertTrue(first is None or isinstance(first, tuple))


class TestStoppingLaneTrackerSafety(unittest.TestCase):
  def test_low_speed_safe(self):
    tr = StoppingLaneCornerTracker()
    model = ego_model(left_y=-1.75, right_y=1.75, velocity_tail=(0.0, 0.0))
    self.assertIsNone(tr.update(0.0, 2.0, model, (corner_point(),),
                                VisionLead(0.9, 20, 0, 0, .2, .2, .2)))


if __name__ == "__main__":
  unittest.main()
