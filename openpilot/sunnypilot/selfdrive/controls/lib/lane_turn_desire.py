"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from openpilot.cereal import custom

from openpilot.common.constants import CV
from openpilot.common.params import Params

from openpilot.sunnypilot.selfdrive.controls.lib.lever import LEVER_LATCHED, LEVER_ONE_TOUCH, lever_maneuver

TurnDirection = custom.ModelDataV2SP.TurnDirection

LANE_CHANGE_SPEED_MIN = 20 * CV.MPH_TO_MS

# CP-1 BlinkerLatchedTurn code default (km/h). The key is not registered in
# common/params_keys.h yet, so Params.get raises UnknownKeyName / returns None
# until the key is registered; 0.0 keeps the lever semantics off and the
# behavior identical to the blinker-only implementation.
BLINKER_LATCHED_TURN_DEFAULT = 0.0  # km/h, 0 = off


class LaneTurnController:
  def __init__(self, desire_helper, params=None):
    self.DH = desire_helper
    self.turn_direction = TurnDirection.none
    self.params = params if params is not None else Params()
    self.lane_turn_value = float(self.params.get("LaneTurnValue", return_default=True)) * CV.MPH_TO_MS
    self.blinker_latched_turn = self._read_param_float("BlinkerLatchedTurn", BLINKER_LATCHED_TURN_DEFAULT) * CV.KPH_TO_MS
    self.param_read_counter = 0
    self.enabled = self.params.get_bool("LaneTurnDesire")

  def _read_param_float(self, key: str, default: float) -> float:
    """Robust Params.get for keys that may be unregistered (UnknownKeyName) or unset (None)."""
    try:
      value = self.params.get(key)
    except Exception:
      return default
    if value is None:
      return default
    try:
      return float(value)
    except (TypeError, ValueError):
      return default

  def read_params(self):
    self.enabled = self.params.get_bool("LaneTurnDesire")
    value = float(self.params.get("LaneTurnValue", return_default=True)) * CV.MPH_TO_MS
    self.lane_turn_value = min(float(LANE_CHANGE_SPEED_MIN), value)
    # CP-1: lever-based turn decision speed gate (km/h, 0 = off), see lever_maneuver.
    self.blinker_latched_turn = self._read_param_float("BlinkerLatchedTurn", BLINKER_LATCHED_TURN_DEFAULT) * CV.KPH_TO_MS

  def update_params(self) -> None:
    if self.param_read_counter % 50 == 0:
      self.read_params()
    self.param_read_counter += 1

  def update_lane_turn(self, blindspot_left: bool, blindspot_right: bool, left_blinker: bool, right_blinker: bool,
                       v_ego: float, carstate=None) -> None:
    # CP-1 (BlinkerLatchedTurn): when the car exposes the turn-signal lever position
    # (carState.blinkerLever, Hyundai CAN-FD) and the feature is enabled, the lever
    # decides turn vs lane change and takes priority over the blinker-only guess:
    # a latched lever at/below BlinkerLatchedTurn is a turn, a one-touch (half)
    # detent is a lane change (undecided -> no turn desire), and anything above the
    # speed gate is a lane change. Cars without the signal (getattr -> None, e.g.
    # Toyota) and with the param off (default) keep the legacy path below unchanged.
    lever = getattr(carstate, "blinkerLever", None) if carstate is not None else None
    if lever is not None and self.blinker_latched_turn > 0.0 and (left_blinker or right_blinker):
      lever_pos = int(lever)
      if lever_pos in (LEVER_ONE_TOUCH, LEVER_LATCHED):
        # SP has no carState.blinkerLamp: a latched lever approximates the
        # forced-turn gesture (one-touch, two lamp lightings, then latched).
        maneuver, _undecided = lever_maneuver(lever_pos, v_ego, self.blinker_latched_turn,
                                              forced_turn=lever_pos == LEVER_LATCHED)
        if maneuver == "turn" and left_blinker != right_blinker:
          self.turn_direction = TurnDirection.turnLeft if left_blinker else TurnDirection.turnRight
        else:
          self.turn_direction = TurnDirection.none
        return
      # LEVER_RELEASED: the lever gives no information (lamp may still flash),
      # fall through to the legacy blinker-based decision.
    if left_blinker and not right_blinker and v_ego < self.lane_turn_value and not blindspot_left:
      self.turn_direction = TurnDirection.turnLeft
    elif right_blinker and not left_blinker and v_ego < self.lane_turn_value and not blindspot_right:
      self.turn_direction = TurnDirection.turnRight
    else:
      self.turn_direction = TurnDirection.none

  def get_turn_direction(self):
    if not self.enabled:
      return TurnDirection.none
    return self.turn_direction
