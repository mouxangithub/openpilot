import unittest

from openpilot.sunnypilot.selfdrive.controls.lib.lane_change_close_gap import (
  DIRECTION_LEFT, DIRECTION_RIGHT, LC_STATE_FINISHING, LC_STATE_PRE, LC_STATE_STARTING)
from openpilot.sunnypilot.selfdrive.controls.lib.lane_change_merge_floor import (
  LC_MERGE_ACCEL_BIAS, LC_MERGE_BRAKE_FLOOR, get_lane_change_merge_accel_floor)

LC_STATE_OFF = 0  # cereal LaneChangeState.off


def floor_for(**overrides):
  args = {
    'v_ego': 25.0, 'standstill': False, 'brake_pressed': False,
    'blindspot_left': False, 'blindspot_right': False,
    'lane_change_state': LC_STATE_STARTING, 'direction': DIRECTION_LEFT,
    'lead_status': True, 'lead_d_rel': 45.0, 'lead_v_lead': 0.0,
    'allow_throttle': True, 'v_cruise': 29.0, 'action_t': 0.55, 'dt': 0.05,
  }
  args.update(overrides)
  return get_lane_change_merge_accel_floor(**args)


class TestLaneChangeMergeFloor(unittest.TestCase):
  def test_far_slow_closing_lead_yields_bias(self):
    # 45 m ahead, closing 2 m/s: TTC 22.5 s, ample headroom -> accel bias.
    # (StarPilot semantics: the floor can be positive - it is a lower bound
    # on the accel, and with room to cruise it raises toward the bias.)
    self.assertAlmostEqual(LC_MERGE_ACCEL_BIAS, floor_for(lead_v_lead=23.0), places=9)

  def test_brake_floor_applies_when_throttle_not_allowed(self):
    # Same scene without throttle authority: the -0.4 floor still caps braking.
    self.assertAlmostEqual(LC_MERGE_BRAKE_FLOOR,
                           floor_for(lead_v_lead=23.0, allow_throttle=False), places=9)

  def test_close_lead_keeps_full_braking_authority(self):
    for name, overrides in (
      ('small_gap', {'lead_d_rel': 29.9, 'lead_v_lead': 23.0}),
      ('short_ttc', {'lead_d_rel': 45.0, 'lead_v_lead': 0.0}),  # TTC 1.8 s
    ):
      with self.subTest(case=name):
        self.assertIsNone(floor_for(**overrides))

  def test_barely_closing_treated_as_infinite_ttc(self):
    # StarPilot verbatim: closing at or below the minimum yields TTC = inf,
    # so a far lead being left very slowly still gets the accel bias.
    self.assertAlmostEqual(LC_MERGE_ACCEL_BIAS, floor_for(lead_d_rel=45.0, lead_v_lead=24.9), places=9)

  def test_accel_bias_when_amply_clear(self):
    # TTC = 45/1 = 45 s, headroom 4 m/s over 0.55 s action time: cap = 4/0.55 > bias.
    self.assertAlmostEqual(LC_MERGE_ACCEL_BIAS,
                           floor_for(lead_v_lead=24.0, v_cruise=29.0), places=9)

  def test_accel_bias_capped_by_cruise_headroom(self):
    # headroom 2 m/s spread over a 10 s action time caps the bias at 0.2 m/s^2.
    self.assertAlmostEqual(0.2, floor_for(lead_v_lead=24.0, v_cruise=27.0, action_t=10.0), places=9)
    # below the headroom minimum the floor stays at the brake floor
    self.assertAlmostEqual(LC_MERGE_BRAKE_FLOOR, floor_for(lead_v_lead=24.0, v_cruise=26.5), places=9)

  def test_no_throttle_authority_keeps_floor_only(self):
    self.assertAlmostEqual(LC_MERGE_BRAKE_FLOOR, floor_for(lead_v_lead=24.0, allow_throttle=False), places=9)

  def test_vetoes(self):
    for name, overrides in (
      ('standstill', {'standstill': True}),
      ('brake_pressed', {'brake_pressed': True}),
      ('slow_ego', {'v_ego': 8.0}),
      ('off_state', {'lane_change_state': LC_STATE_OFF}),
      ('blindspot_left', {'direction': DIRECTION_LEFT, 'blindspot_left': True}),
      ('blindspot_right', {'direction': DIRECTION_RIGHT, 'blindspot_right': True}),
      ('no_lead', {'lead_status': False}),
    ):
      with self.subTest(case=name):
        self.assertIsNone(floor_for(**overrides))

  def test_all_active_lane_change_states_qualify(self):
    for state in (LC_STATE_PRE, LC_STATE_STARTING, LC_STATE_FINISHING):
      with self.subTest(state=state):
        self.assertAlmostEqual(LC_MERGE_BRAKE_FLOOR,
                               floor_for(lane_change_state=state, lead_v_lead=23.0,
                                         allow_throttle=False), places=9)


if __name__ == '__main__':
  unittest.main()
