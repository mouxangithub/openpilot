from openpilot.cereal import log, custom
from openpilot.common.constants import CV
from openpilot.common.realtime import DT_MDL
from openpilot.sunnypilot.selfdrive.controls.lib.auto_lane_change import AutoLaneChangeController, AutoLaneChangeMode
from openpilot.sunnypilot.selfdrive.controls.lib.lane_turn_desire import LaneTurnController

LaneChangeState = log.LaneChangeState
LaneChangeDirection = log.LaneChangeDirection
TurnDirection = custom.ModelDataV2SP.TurnDirection

LANE_CHANGE_SPEED_MIN = 20 * CV.MPH_TO_MS
LANE_CHANGE_TIME_MAX = 10.
LANE_CHANGE_START_TIME = 0.5

TURN_DESIRES = {
  TurnDirection.none: log.Desire.none,
  TurnDirection.turnLeft: log.Desire.turnLeft,
  TurnDirection.turnRight: log.Desire.turnRight,
}

class DesireHelper:
  def __init__(self):
    self.lane_change_state = LaneChangeState.off
    self.lane_change_direction = LaneChangeDirection.none
    self.lane_change_timer = 0.0
    self.prev_one_blinker = False
    self.desire = log.Desire.none
    self.alc = AutoLaneChangeController(self)
    self.lane_turn_controller = LaneTurnController(self)
    self.lane_turn_direction = TurnDirection.none
    # CarrotPilot ATC (auto turn control) state
    self.carrot_atc_active = False
    self.carrot_cmd_index_last = 0
    self.carrot_virtual_blinker = 0  # 0=none, 1=left, 2=right

  def get_lane_change_direction(self, CS):
    if self.carrot_virtual_blinker == 1 and CS.leftBlinker:
      return LaneChangeDirection.left
    elif self.carrot_virtual_blinker == 2 and CS.rightBlinker:
      return LaneChangeDirection.right
    return LaneChangeDirection.left if CS.leftBlinker else LaneChangeDirection.right

  def update(self, carstate, lateral_active, lane_change_prob, left_edge_detected=False, right_edge_detected=False,
             left_lane_line_blocked=False, right_lane_line_blocked=False, carrot_man=None):
    self.alc.update_params()
    self.lane_turn_controller.update_params()
    v_ego = carstate.vEgo
    one_blinker = carstate.leftBlinker != carstate.rightBlinker
    below_lane_change_speed = v_ego < LANE_CHANGE_SPEED_MIN

    # CarrotPilot ATC: process carrotMan commands to inject virtual blinker
    if carrot_man is not None:
      atc_type = carrot_man.atcType
      if atc_type in ["turn left", "turn right", "atc left", "atc right", "fork left", "fork right"]:
        self.carrot_atc_active = True
        if "left" in atc_type:
          self.carrot_virtual_blinker = 1
        else:
          self.carrot_virtual_blinker = 2
        # For turns at low speed, use turn desire directly
        if atc_type in ["turn left", "turn right"]:
          below_lane_change_speed = True
      else:
        self.carrot_atc_active = False
        self.carrot_virtual_blinker = 0

      # Process LANECHANGE/OVERTAKE commands
      if carrot_man.carrotCmdIndex != self.carrot_cmd_index_last:
        self.carrot_cmd_index_last = carrot_man.carrotCmdIndex
        if carrot_man.carrotCmd in ["LANECHANGE", "OVERTAKE"]:
          if carrot_man.carrotArg == "LEFT":
            self.carrot_virtual_blinker = 1
          elif carrot_man.carrotArg == "RIGHT":
            self.carrot_virtual_blinker = 2
    else:
      self.carrot_atc_active = False
      self.carrot_virtual_blinker = 0

    virtual_blinker_matches = ((self.carrot_virtual_blinker == 1 and carstate.leftBlinker) or
                               (self.carrot_virtual_blinker == 2 and carstate.rightBlinker))
    one_blinker = one_blinker or virtual_blinker_matches

    # Lane turn controller update
    self.lane_turn_controller.update_lane_turn(blindspot_left=carstate.leftBlindspot, blindspot_right=carstate.rightBlindspot,
                                               left_blinker=carstate.leftBlinker, right_blinker=carstate.rightBlinker, v_ego=v_ego)
    self.lane_turn_direction = self.lane_turn_controller.get_turn_direction()

    if not lateral_active or self.lane_change_timer > LANE_CHANGE_TIME_MAX or self.alc.lane_change_set_timer == AutoLaneChangeMode.OFF:
      self.lane_change_state = LaneChangeState.off
      self.lane_change_direction = LaneChangeDirection.none
      self.lane_change_timer = 0.0
    else:
      if self.lane_change_state == LaneChangeState.off and one_blinker and not self.prev_one_blinker and not below_lane_change_speed:
        self.lane_change_state = LaneChangeState.preLaneChange
        self.lane_change_timer = 0.0
        # Initialize lane change direction to prevent UI alert flicker
        self.lane_change_direction = self.get_lane_change_direction(carstate)

      elif self.lane_change_state == LaneChangeState.preLaneChange:
        # Update lane change direction
        self.lane_change_direction = self.get_lane_change_direction(carstate)

        torque_applied = carstate.steeringPressed and \
                         ((carstate.steeringTorque > 0 and self.lane_change_direction == LaneChangeDirection.left) or
                          (carstate.steeringTorque < 0 and self.lane_change_direction == LaneChangeDirection.right))

        left_blocked = carstate.leftBlindspot or left_edge_detected or left_lane_line_blocked
        right_blocked = carstate.rightBlindspot or right_edge_detected or right_lane_line_blocked
        blindspot_detected = ((left_blocked and self.lane_change_direction == LaneChangeDirection.left) or
                              (right_blocked and self.lane_change_direction == LaneChangeDirection.right))

        self.alc.update_lane_change(blindspot_detected, carstate.brakePressed)

        if not one_blinker or below_lane_change_speed:
          self.lane_change_state = LaneChangeState.off
          self.lane_change_direction = LaneChangeDirection.none
          self.lane_change_timer = 0.0
        elif (torque_applied or self.alc.auto_lane_change_allowed) and not blindspot_detected:
          self.lane_change_state = LaneChangeState.laneChangeStarting
          self.lane_change_timer = 0.0

      elif self.lane_change_state == LaneChangeState.laneChangeStarting:
        self.lane_change_timer += DT_MDL

        if lane_change_prob < 0.02 and self.lane_change_timer >= LANE_CHANGE_START_TIME:
          self.lane_change_timer = 0.0
          if one_blinker:
            self.lane_change_state = LaneChangeState.preLaneChange
            self.lane_change_direction = self.get_lane_change_direction(carstate)
          else:
            self.lane_change_state = LaneChangeState.off
            self.lane_change_direction = LaneChangeDirection.none

    self.prev_one_blinker = one_blinker and lateral_active

    if self.lane_turn_direction != TurnDirection.none:
      self.desire = TURN_DESIRES[self.lane_turn_direction]
    else:
      self.desire = log.Desire.none
      if self.lane_change_state == LaneChangeState.laneChangeStarting:
        if self.lane_change_direction == LaneChangeDirection.left:
          self.desire = log.Desire.laneChangeLeft
        elif self.lane_change_direction == LaneChangeDirection.right:
          self.desire = log.Desire.laneChangeRight

    self.alc.update_state()
