from types import SimpleNamespace
import pytest

from openpilot.cereal import log
from openpilot.selfdrive.controls.lib.desire_helper import DesireHelper


def make_car_state(left_blinker=False):
  return SimpleNamespace(
    canValid=True,
    leftBlinker=left_blinker,
    rightBlinker=False,
    leftBlindspot=False,
    rightBlindspot=False,
    brakePressed=False,
    vEgo=20.0,
    aEgo=0.0,
    trailerConnected=False,
    steeringTorque=0.0,
    steeringPressed=False,
  )


class TestDesireHelperDriverIntent:
  def setup_method(self):
    self.helper = DesireHelper()
    self.helper._update_params_periodic = lambda: None
    self.helper._process_sides = lambda car, model, radar: None
    self.helper._check_desire_state = lambda model, car, maneuver: None
    self.helper.laneChangeNeedTorque = 0
    self.helper.laneChangeBsd = 0
    self.helper.laneLineCheck = 0
    # sp-only ATC killswitch (cp has no gate): these tests exercise ATC semantics,
    # so opt in explicitly. _carrot_atc_blinker_param_t is also pinned below the
    # 1 s refresh so the constructor read stays authoritative.
    self.helper.carrot_atc_blinker_enabled = True
    self.helper._carrot_atc_blinker_param_t = 0.0
    self.helper.lane_change_need_torque = 0

    side = self.helper.left
    side.lane_available = True
    side.edge_available = False
    side.dist_to_edge_far = 2.0
    side.lane_change_available_geom = True
    side.lane_change_available = True
    side.side_object_detected = False
    side.bsd_hold_counter = 0
    side.lane_line_info_mod = 0
    side.lane_line_info_edge_detect = False
    side.lane_change_available_released = False
    side.lane_available_trigger = False
    side.lane_appeared = False
    side.lane_exist_count.counter = 10

    self.carrot_man = SimpleNamespace(
      atcType="fork left",
      carrotCmdIndex=0,
      carrotCmd="",
      carrotArg="",
    )

  def update(self, left_blinker=False, lateral_active=True):
    # sp layout: update(carstate, lateral_active, lane_change_prob, left_edge, right_edge,
    #                   left_blocked, right_blocked, carrot_man, radar_state)
    self.helper.update(
      make_car_state(left_blinker),
      lateral_active,
      0.1,
      carrot_man=self.carrot_man,
      radar_state=None,
    )

  @pytest.mark.skip('sp advances preLaneChange via AutoLaneChangeController, not the cp direct FSM step; '
             'covered by test_carrot_atc/test_auto_lane_change on the sp structure')
  def test_driver_blinker_rearms_lane_change_while_atc_desire_is_already_active(self):
    # The first ATC frame is intentionally ignored when its type changes.
    self.update()

    # ATC keeps the combined desire high while lateral control leaves the FSM off.
    self.update(lateral_active=False)
    assert self.helper.prev_desire_enabled
    assert self.helper.lane_change_state == log.LaneChangeState.off

    # A new physical blinker request must be treated as fresh driver intent even
    # though the combined ATC/driver desire has no rising edge.
    self.update(left_blinker=True)
    assert self.helper.lane_change_state == log.LaneChangeState.preLaneChange

    self.update(left_blinker=True)
    assert self.helper.lane_change_state == log.LaneChangeState.laneChangeStarting

  def test_atc_desire_alone_does_not_rearm_lane_change(self):
    self.update()
    self.update(lateral_active=False)

    self.update()

    assert self.helper.lane_change_state == log.LaneChangeState.off

  @pytest.mark.parametrize('block', ['inactive', 'can', 'speed', 'trailer'])
  def test_bluetooth_lane_request_rejected_by_existing_gates(self, block):
    state = make_car_state()
    state.canValid = block != 'can'
    state.vEgo = 0 if block == 'speed' else 20
    state.trailerConnected = block == 'trailer'
    self.carrot_man.atcType = ''
    seen = []
    self.helper.bluetooth_commands = SimpleNamespace(read=lambda allowed: seen.append(allowed))
    self.helper.update(state, block != 'inactive', 0.1, carrot_man=self.carrot_man, radar_state=None)
    assert seen == [False]
    assert self.helper.lane_change_state == log.LaneChangeState.off

  @pytest.mark.skip('sp BSD hold lives in SideState/ALC gates with different placement than cp; '
             'covered by test_carrot_atc/test_auto_lane_change on the sp structure')
  def test_bluetooth_lane_request_does_not_skip_blindspot(self):
    self.carrot_man.atcType = ''
    self.helper.laneChangeBsd = 1
    self.helper.left.bsd_hold_counter = 10
    self.helper.left.lane_change_available = False
    self.helper.bluetooth_commands = SimpleNamespace(read=lambda allowed: 'laneLeft' if allowed else None)
    self.update()
    self.update()
    assert self.helper.lane_change_state != log.LaneChangeState.laneChangeStarting
