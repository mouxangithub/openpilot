from openpilot.cereal import log, custom
from openpilot.common.constants import CV
from openpilot.common.params import Params
from openpilot.common.realtime import DT_MDL
from openpilot.sunnypilot.selfdrive.controls.lib.auto_lane_change import AutoLaneChangeController, AutoLaneChangeMode
from openpilot.sunnypilot.selfdrive.controls.lib.lane_turn_desire import LaneTurnController
from openpilot.sunnypilot.selfdrive.controls.lib.desire_arbiter import DesireArbiter
# Bluetooth HID remote lane commands (carrot_bluetooth daemon → /dev/shm/carrot-bluetooth/lane.json).
from openpilot.sunnypilot.carrot.bluetooth.model import CommandReader
from openpilot.selfdrive.controls.lib.desire_lib.side_state import SideState

LaneChangeState = log.LaneChangeState
LaneChangeDirection = log.LaneChangeDirection
TurnDirection = custom.ModelDataV2SP.TurnDirection

LANE_CHANGE_SPEED_MIN = 20 * CV.MPH_TO_MS
LANE_CHANGE_TIME_MAX = 10.
LANE_CHANGE_START_TIME = 0.5

# cp blinker states (desire_lib.constants). sp keeps them inline so the FSM below
# can switch to the full cp ATC semantics without pulling the whole enum set.
BLINKER_NONE = 0
BLINKER_LEFT = 1
BLINKER_RIGHT = 2

TURN_DESIRES = {
  TurnDirection.none: log.Desire.none,
  TurnDirection.turnLeft: log.Desire.turnLeft,
  TurnDirection.turnRight: log.Desire.turnRight,
}

# cp ATC types. Right-side fork/ATC may start the lane change without driver
# confirmation (the off-ramp case); left-side ones are manual-only in cp, because
# a left fork usually crosses oncoming traffic lanes.
ATC_TURN_TYPES = ("turn left", "turn right")
ATC_FORK_TYPES = ("fork left", "fork right", "atc left", "atc right")
ATC_AUTO_TYPES = ("fork right", "atc right")
ATC_MANUAL_ONLY_TYPES = ("fork left", "atc left")


class DesireHelper:
  def __init__(self):
    self.lane_change_state = LaneChangeState.off
    self.lane_change_direction = LaneChangeDirection.none
    self.lane_change_timer = 0.0
    self.prev_one_blinker = False
    self.prev_desire_enabled = False   # cp: combined (driver|ATC) desire edge, tracked even when lateral is off
    self.prev_driver_enabled = False   # cp: driver lamp edge for fresh-intent rearm
    self.desire = log.Desire.none
    self.alc = AutoLaneChangeController(self)
    self.lane_turn_controller = LaneTurnController(self)
    self.lane_turn_direction = TurnDirection.none

    # CarrotPilot ATC state (cp desire_lib semantics).
    self.carrot_atc_active = False
    self.carrot_cmd_index_last = 0
    self.carrot_virtual_blinker = 0  # 0=none, 1=left, 2=right (kept for the arbiter path)
    self.carrot_blinker_state = BLINKER_NONE
    self.carrot_lane_change_count = 0  # frames remaining for a forced server LANECHANGE
    self.atc_type_last = ""
    self.atc_active = 0  # 0: none, 1: ATC active, 2: conflict with driver blinker
    self.blinker_ignore = False  # driver cancelled with opposite torque; ATC ignored until lamps dark

    # cp SideState: per-side obstacle/BSD hold for the ATC auto-start gate.
    self.left = SideState("left")
    self.right = SideState("right")

    self._params = Params()
    # Bluetooth HID remote lane commands.
    self.bluetooth_commands = CommandReader('lane')
    self._bt_lane_count = 0  # frames remaining for a Bluetooth lane command

    # Killswitch for the synthetic-blinker path, OFF by default.
    #
    # Not just a UI convenience: a carrot packet saying "turn left" used to make this
    # class treat a blinker as pressed with no switch at all. That synthetic blinker
    # reaches the vehicle - one_blinker -> LaneChangeState.preLaneChange ->
    # modelV2.meta.laneChangeState -> controlsd CC.leftBlinker/rightBlinker -> the car's
    # own turn-signal CAN message (opendbc hyundai carcontroller create_spas_messages).
    # A navigation intent driving a vehicle actuation has to be opt-in.
    self.carrot_atc_blinker_enabled = self._params.get_bool("CarrotAtcBlinkerEnabled")
    self._carrot_atc_blinker_param_t = 0.0

    # Unified lateral arbiter (default OFF; preserves historical behavior when disabled).
    self.desire_arbiter = DesireArbiter()

    # LaneChangeNeedTorque gates the driver lamp exactly as in cp; cached here
    # because _driver_blinker_state needs it every frame.
    self.lane_change_need_torque = self._params.get_int("LaneChangeNeedTorque")
    self._param_read_frame = 0

  def _driver_blinker_state(self, carstate) -> tuple[int, bool]:
    """cp _update_driver_blinker: exactly-one lamp means enabled (unless LaneChangeNeedTorque < 0)."""
    st = carstate.leftBlinker * 1 + carstate.rightBlinker * 2
    enabled = st in (BLINKER_LEFT, BLINKER_RIGHT)
    if self.lane_change_need_torque < 0:
      enabled = False
    return st, enabled

  def _update_atc_blinker(self, carrot_man, driver_blinker_state: int, remote=None) -> tuple[int, bool]:
    """cp _update_atc_blinker, verbatim semantics.

    Returns (atc_blinker_state, atc_desire_enabled). The ATC lamp can act alone:
    the caller falls back to it whenever the driver has no lamp of its own.
    """
    atc_type = str(getattr(carrot_man, "atcType", "") or "")
    atc_blinker_state = BLINKER_NONE

    # The forced server LANECHANGE window keeps the lamp lit for 0.2 s.
    if self.carrot_lane_change_count > 0:
      atc_blinker_state = self.carrot_blinker_state
    elif remote in ('laneLeft', 'laneRight'):
      self.carrot_lane_change_count = int(0.2 / DT_MDL)
      self.carrot_blinker_state = BLINKER_LEFT if remote == 'laneLeft' else BLINKER_RIGHT
      atc_blinker_state = self.carrot_blinker_state
    elif int(getattr(carrot_man, "carrotCmdIndex", 0)) != self.carrot_cmd_index_last and \
        str(getattr(carrot_man, "carrotCmd", "") or "") == "LANECHANGE":
      self.carrot_cmd_index_last = int(getattr(carrot_man, "carrotCmdIndex", 0))
      self.carrot_lane_change_count = int(0.2 / DT_MDL)
      self.carrot_blinker_state = BLINKER_LEFT if str(getattr(carrot_man, "carrotArg", "") or "") == "LEFT" else BLINKER_RIGHT
      atc_blinker_state = self.carrot_blinker_state
    elif atc_type in ATC_TURN_TYPES:
      if self.atc_active != 2:
        atc_blinker_state = BLINKER_LEFT if atc_type == "turn left" else BLINKER_RIGHT
        self.atc_active = 1
        self.blinker_ignore = False
    elif atc_type in ATC_FORK_TYPES:
      if self.atc_active != 2:
        atc_blinker_state = BLINKER_LEFT if atc_type in ("fork left", "atc left") else BLINKER_RIGHT
        self.atc_active = 1
    else:
      self.atc_active = 0

    # Driver and ATC lamps on opposite sides: the driver wins and ATC is invalidated
    # (atc_active=2) until its type goes back to none.
    if driver_blinker_state != BLINKER_NONE and atc_blinker_state != BLINKER_NONE and \
        driver_blinker_state != atc_blinker_state:
      atc_blinker_state = BLINKER_NONE
      self.atc_active = 2

    atc_desire_enabled = atc_blinker_state in (BLINKER_LEFT, BLINKER_RIGHT)

    # blinker_ignore: after a torque cancel, ATC stays suppressed until the driver lamp goes dark.
    if driver_blinker_state == BLINKER_NONE:
      self.blinker_ignore = False
    if self.blinker_ignore:
      atc_blinker_state = BLINKER_NONE
      atc_desire_enabled = False

    # A fresh ATC type is ignored for one frame (gap between "prepare" transitions).
    if self.atc_type_last != atc_type:
      atc_desire_enabled = False
    self.atc_type_last = atc_type

    # Expose the same view the arbiter path has always used.
    self.carrot_atc_active = atc_desire_enabled
    self.carrot_virtual_blinker = atc_blinker_state
    return atc_blinker_state, atc_desire_enabled

  def get_lane_change_direction(self, blinker_state: int):
    return LaneChangeDirection.left if blinker_state == BLINKER_LEFT else LaneChangeDirection.right

  def update(self, carstate, lateral_active, lane_change_prob, left_edge_detected=False, right_edge_detected=False,
             left_lane_line_blocked=False, right_lane_line_blocked=False, carrot_man=None, radar_state=None):
    self.alc.update_params()
    self.lane_turn_controller.update_params()
    self._update_params_periodic()
    v_ego = carstate.vEgo
    below_lane_change_speed = v_ego < LANE_CHANGE_SPEED_MIN

    # Bluetooth HID remote lane commands (carrot_bluetooth daemon publishes to /dev/shm/carrot-bluetooth/lane.json).
    remote = self.bluetooth_commands.read(
      allowed=(lateral_active and carstate.canValid and not below_lane_change_speed and
               not getattr(carstate, 'trailerConnected', False)),
    )
    if remote in ('laneLeft', 'laneRight') and self._bt_lane_count == 0:
      self._bt_lane_count = int(0.2 / DT_MDL)  # 200 ms window
    if self._bt_lane_count > 0:
      self._bt_lane_count -= 1

    # Refresh the ATC killswitch at most once a second (update() runs at 100 Hz).
    self._carrot_atc_blinker_param_t += DT_MDL
    if self._carrot_atc_blinker_param_t >= 1.0:
      self._carrot_atc_blinker_param_t = 0.0
      self.carrot_atc_blinker_enabled = self._params.get_bool("CarrotAtcBlinkerEnabled")

    driver_st, driver_enabled = self._driver_blinker_state(carstate)

    # cp SideState obstacle/BSD hold per side (only meaningful when radarState is fed).
    if radar_state is not None:
      self.left.update_obstacles(v_ego, radar_state.leadLeft, carstate.leftBlindspot, ignore_bsd=False,
                                 radar_objects=tuple(getattr(radar_state, "leadsLeft", ())))
      self.right.update_obstacles(v_ego, radar_state.leadRight, carstate.rightBlindspot, ignore_bsd=False,
                                  radar_objects=tuple(getattr(radar_state, "leadsRight", ())))
    else:
      self.left.update_obstacles(v_ego, None, carstate.leftBlindspot, ignore_bsd=False)
      self.right.update_obstacles(v_ego, None, carstate.rightBlindspot, ignore_bsd=False)

    if carrot_man is not None and self.carrot_atc_blinker_enabled:
      self.carrot_lane_change_count = max(0, self.carrot_lane_change_count - 1)
      atc_st, atc_enabled = self._update_atc_blinker(carrot_man, driver_st, remote)
    else:
      # Killswitch off: no synthetic lamp. Keep the bookkeeping state clean so a
      # later opt-in starts from a blank slate.
      self.carrot_lane_change_count = 0
      if carrot_man is not None:
        self.carrot_cmd_index_last = int(getattr(carrot_man, "carrotCmdIndex", 0))
      self.carrot_atc_active = False
      self.carrot_virtual_blinker = 0
      self.carrot_blinker_state = BLINKER_NONE
      self.atc_active = 0
      self.atc_type_last = ""
      atc_st, atc_enabled = BLINKER_NONE, False

    # cp: the driver lamp wins; without one, the ATC lamp acts on its own.
    desire_enabled = driver_enabled or atc_enabled
    blinker_state = driver_st if driver_enabled else atc_st
    one_blinker = blinker_state in (BLINKER_LEFT, BLINKER_RIGHT)
    if one_blinker:
      self.lane_change_direction = self.get_lane_change_direction(blinker_state)

    # Lane turn controller update (driver blinkers only, sp speed gate; ATC turn
    # desires are applied separately below).
    self.lane_turn_controller.update_lane_turn(blindspot_left=carstate.leftBlindspot, blindspot_right=carstate.rightBlindspot,
                                               left_blinker=carstate.leftBlinker, right_blinker=carstate.rightBlinker, v_ego=v_ego,
                                               carstate=carstate)
    self.lane_turn_direction = self.lane_turn_controller.get_turn_direction()

    # ATC turn types become turn desires directly (cp classify_maneuver_type gives
    # "turn left/right" a strong turn score); they must not enter the lane-change FSM.
    atc_turn_desire = TurnDirection.none
    if atc_enabled and not driver_enabled and self.atc_type_last in ATC_TURN_TYPES:
      atc_turn_desire = TurnDirection.turnLeft if self.atc_type_last == "turn left" else TurnDirection.turnRight

    if not lateral_active or self.lane_change_timer > LANE_CHANGE_TIME_MAX + self.alc.lane_change_time_extra or \
       self.alc.lane_change_set_timer == AutoLaneChangeMode.OFF:
      self.lane_change_state = LaneChangeState.off
      self.lane_change_direction = LaneChangeDirection.none
      self.lane_change_timer = 0.0
    else:
      # cp semantics: the combined desire edge OR a fresh driver lamp request arms
      # the FSM. A driver lamp while the ATC desire is already high is still fresh
      # intent; a persisting ATC desire alone never re-arms.
      driver_changed = driver_enabled and not self.prev_driver_enabled
      driver_desire_started = driver_enabled and driver_changed
      if self.lane_change_state == LaneChangeState.off and one_blinker and desire_enabled and \
          (not self.prev_desire_enabled or driver_desire_started) and \
          not below_lane_change_speed:
        self.lane_change_state = LaneChangeState.preLaneChange
        self.lane_change_timer = 0.0
        # Initialize lane change direction to prevent UI alert flicker
        self.lane_change_direction = self.get_lane_change_direction(blinker_state)

      elif self.lane_change_state == LaneChangeState.preLaneChange:
        # Update lane change direction
        self.lane_change_direction = self.get_lane_change_direction(blinker_state)

        torque_applied = carstate.steeringPressed and \
                         ((carstate.steeringTorque > 0 and self.lane_change_direction == LaneChangeDirection.left) or
                          (carstate.steeringTorque < 0 and self.lane_change_direction == LaneChangeDirection.right))

        # Blind-spot and the carrot lane-line block are hard blocks a nudge may not
        # override; a road edge is soft and update_lane_change lets a steering nudge
        # through it. Edge must not be folded into blindspot_detected, or the BSM
        # branch blocks what the nudge is meant to allow (test_nudge_overrides_edge).
        left_bsm = carstate.leftBlindspot or left_lane_line_blocked
        right_bsm = carstate.rightBlindspot or right_lane_line_blocked
        blindspot_detected = ((left_bsm and self.lane_change_direction == LaneChangeDirection.left) or
                              (right_bsm and self.lane_change_direction == LaneChangeDirection.right))

        edge_detected = ((left_edge_detected and self.lane_change_direction == LaneChangeDirection.left) or
                         (right_edge_detected and self.lane_change_direction == LaneChangeDirection.right))

        self.alc.update_lane_change(blindspot_detected, edge_detected, carstate.brakePressed, torque_applied)

        # cp ATC start rules: a right-side fork/ATC ("下匝道") may start on its own
        # once the lamp is armed; the left side stays manual-only. Hard blocks
        # (BSD / carrot lane-line) are always respected; the soft edge block is
        # deliberately not applied here — the ramp is exactly where the road edge
        # opens up, and carrot_serv already pauses ATC on opposite steering torque.
        atc_only = atc_enabled and not driver_enabled
        atc_side_hard_blocked = (left_bsm and self.lane_change_direction == LaneChangeDirection.left) or \
                                (right_bsm and self.lane_change_direction == LaneChangeDirection.right)
        side = self.left if self.lane_change_direction == LaneChangeDirection.left else self.right
        atc_side_unsafe = (radar_state is not None and
                           (side.side_object_detected or side.bsd_hold_counter > 0))
        # cp: within the forced window (server LANECHANGE / bluetooth lane command) the
        # start is allowed outright; otherwise only right-side fork/ATC auto-starts.
        atc_forced = self.carrot_lane_change_count > 0
        atc_auto_start = (atc_only and (self.atc_type_last in ATC_AUTO_TYPES or atc_forced) and
                          self._atc_delay_ready() and not atc_side_hard_blocked and not atc_side_unsafe)

        if not one_blinker or below_lane_change_speed:
          self.lane_change_state = LaneChangeState.off
          self.lane_change_direction = LaneChangeDirection.none
          self.lane_change_timer = 0.0
        elif (torque_applied or self.alc.auto_lane_change_allowed or atc_auto_start) and not self.alc.lane_change_blocked:
          self.lane_change_state = LaneChangeState.laneChangeStarting
          self.lane_change_timer = 0.0

      elif self.lane_change_state == LaneChangeState.laneChangeStarting:
        self.lane_change_timer += DT_MDL

        if lane_change_prob < 0.02 and self.lane_change_timer >= LANE_CHANGE_START_TIME:
          self.lane_change_timer = 0.0
          if one_blinker:
            self.lane_change_state = LaneChangeState.preLaneChange
            self.lane_change_direction = self.get_lane_change_direction(blinker_state)
          else:
            self.lane_change_state = LaneChangeState.off
            self.lane_change_direction = LaneChangeDirection.none

    # cp cancel: opposite torque during a change kills it and suppresses ATC
    # (blinker_ignore) until the driver lamp goes dark.
    if self.lane_change_state != LaneChangeState.off and carstate.steeringPressed:
      steering_pressed_cancel = ((carstate.steeringTorque < 0 and blinker_state == BLINKER_LEFT) or
                                 (carstate.steeringTorque > 0 and blinker_state == BLINKER_RIGHT))
      if steering_pressed_cancel:
        self.lane_change_direction = LaneChangeDirection.none
        self.lane_change_state = LaneChangeState.off
        self.blinker_ignore = True

    self.prev_one_blinker = one_blinker and lateral_active and desire_enabled
    # cp: desire edges are tracked regardless of lateral_active, so a persisting
    # ATC desire is not re-armed when lateral control comes back on.
    self.prev_desire_enabled = desire_enabled
    self.prev_driver_enabled = driver_enabled

    # cp TURN mode: an ATC turn keeps the lane-change FSM off while the turn desire is live.
    if atc_turn_desire != TurnDirection.none:
      self.lane_change_state = LaneChangeState.off
      self.lane_change_direction = LaneChangeDirection.none
      self.lane_change_timer = 0.0
      self.lane_turn_direction = atc_turn_desire

    if self.lane_turn_direction != TurnDirection.none:
      self.desire = TURN_DESIRES[self.lane_turn_direction]
    else:
      self.desire = log.Desire.none
      if self.lane_change_state == LaneChangeState.laneChangeStarting:
        if self.lane_change_direction == LaneChangeDirection.left:
          self.desire = log.Desire.laneChangeLeft
        elif self.lane_change_direction == LaneChangeDirection.right:
          self.desire = log.Desire.laneChangeRight

    # Optional unified arbiter. When enabled it overrides the historical desire
    # selection with a single converged source, gated by multi-frame confirmation.
    # Default OFF so existing behavior is preserved unless the user opts in.
    if self.desire_arbiter.enabled:
      carrot_turn_left = self.carrot_atc_active and self.carrot_virtual_blinker == 1
      carrot_turn_right = self.carrot_atc_active and self.carrot_virtual_blinker == 2
      lane_turn_left = self.lane_turn_direction == TurnDirection.turnLeft
      lane_turn_right = self.lane_turn_direction == TurnDirection.turnRight
      alc_left = self.lane_change_state == LaneChangeState.laneChangeStarting and self.lane_change_direction == LaneChangeDirection.left
      alc_right = self.lane_change_state == LaneChangeState.laneChangeStarting and self.lane_change_direction == LaneChangeDirection.right
      safety_veto = not lateral_active
      self.desire = self.desire_arbiter.resolve(
        carrot_turn_left, carrot_turn_right,
        False, False,  # Amap turn hints are not yet populated; reserved for Phase 2 follow-up.
        lane_turn_left, lane_turn_right,
        alc_left, alc_right,
        safety_veto=safety_veto,
        log_desire=log.Desire,
      )

    self.alc.update_state()

  def _update_params_periodic(self) -> None:
    if self._param_read_frame % 100 == 0:
      self.lane_change_need_torque = self._params.get_int("LaneChangeNeedTorque")
    self._param_read_frame += 1

  def _atc_delay_ready(self) -> bool:
    """Arming window for ATC auto starts.

    The timed ALC modes wait out their delay first (mirrors cp's lane_change_delay);
    NUDGE/NUDGELESS arm immediately, because the ATC lamp itself is the navigation
    intent and carrot_serv has already applied its distance-based arming windows.
    """
    if self.alc.lane_change_set_timer in (AutoLaneChangeMode.HALF_SECOND, AutoLaneChangeMode.ONE_SECOND,
                                          AutoLaneChangeMode.TWO_SECONDS, AutoLaneChangeMode.THREE_SECONDS):
      return self.alc.lane_change_wait_timer > self.alc.lane_change_delay
    return True
