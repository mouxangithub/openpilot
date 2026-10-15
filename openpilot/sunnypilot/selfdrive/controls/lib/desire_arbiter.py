from __future__ import annotations
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""
Lateral desire arbiter for carrot / Amap / stock ALC / lane-turn sources.

Converges multiple lateral-intent sources into a single ``log.Desire`` value so
that the model sees one consistent lateral request. The arbiter is deliberately
simple and defensive: when in doubt it outputs ``none``.

The arbiter is gated by ``DesireArbiterEnabled`` (default OFF). When off,
``DesireHelper`` falls back to its historical desire-selection logic.
"""

from enum import IntEnum
from typing import Any

from openpilot.sunnypilot.carrot.config import UnifiedParams


class RawDesire(IntEnum):
  NONE = 0
  TURN_LEFT = 1
  TURN_RIGHT = 2
  LANE_CHANGE_LEFT = 3
  LANE_CHANGE_RIGHT = 4


# Hold / confirmation frames at 20 Hz model ticks.
_TURN_CONFIRM_FRAMES = 3
_LANE_CHANGE_CONFIRM_FRAMES = 2


class DesireArbiter:
  """Pick one lateral desire from carrot/Amap/ALC/lane-turn sources."""

  def __init__(self) -> None:
    self._params = UnifiedParams()
    self.enabled = self._params.get_bool("DesireArbiterEnabled")
    self._param_count = 0

    self.desire = RawDesire.NONE
    self._turn_left_frames = 0
    self._turn_right_frames = 0
    self._lc_left_frames = 0
    self._lc_right_frames = 0

  def _refresh_params(self) -> None:
    self._param_count += 1
    if self._param_count % 100 == 0:
      self.enabled = self._params.get_bool("DesireArbiterEnabled")

  @staticmethod
  def _to_log_desire(raw: RawDesire, log_desire: Any) -> Any:
    """Map internal raw desire to the caller's ``log.Desire`` enum."""
    mapping = {
      RawDesire.NONE: log_desire.none,
      RawDesire.TURN_LEFT: log_desire.turnLeft,
      RawDesire.TURN_RIGHT: log_desire.turnRight,
      RawDesire.LANE_CHANGE_LEFT: log_desire.laneChangeLeft,
      RawDesire.LANE_CHANGE_RIGHT: log_desire.laneChangeRight,
    }
    return mapping.get(raw, log_desire.none)

  def update(self,
             carrot_turn_left: bool,
             carrot_turn_right: bool,
             amap_turn_left: bool,
             amap_turn_right: bool,
             lane_turn_left: bool,
             lane_turn_right: bool,
             alc_left: bool,
             alc_right: bool,
             safety_veto: bool = False) -> RawDesire:
    """Run one arbitration step and return the selected raw desire."""
    self._refresh_params()

    if safety_veto:
      self.desire = RawDesire.NONE
      self._reset_counts()
      return self.desire

    # Sustained-frame counters.
    self._turn_left_frames = self._turn_left_frames + 1 if carrot_turn_left or amap_turn_left or lane_turn_left else 0
    self._turn_right_frames = self._turn_right_frames + 1 if carrot_turn_right or amap_turn_right or lane_turn_right else 0
    self._lc_left_frames = self._lc_left_frames + 1 if alc_left else 0
    self._lc_right_frames = self._lc_right_frames + 1 if alc_right else 0

    turn_left_c = self._turn_left_frames >= _TURN_CONFIRM_FRAMES
    turn_right_c = self._turn_right_frames >= _TURN_CONFIRM_FRAMES
    lc_left_c = self._lc_left_frames >= _LANE_CHANGE_CONFIRM_FRAMES
    lc_right_c = self._lc_right_frames >= _LANE_CHANGE_CONFIRM_FRAMES

    # Conflict: do not command a lateral maneuver when both directions are
    # requested at the same time.
    if turn_left_c and turn_right_c:
      self.desire = RawDesire.NONE
      return self.desire
    if lc_left_c and lc_right_c:
      self.desire = RawDesire.NONE
      return self.desire

    # Priority 1: forced navigation turn (any sustained turn request).
    if turn_left_c:
      self.desire = RawDesire.TURN_LEFT
      return self.desire
    if turn_right_c:
      self.desire = RawDesire.TURN_RIGHT
      return self.desire

    # Priority 2: auto lane change (only when no turn is requested).
    if lc_left_c:
      self.desire = RawDesire.LANE_CHANGE_LEFT
      return self.desire
    if lc_right_c:
      self.desire = RawDesire.LANE_CHANGE_RIGHT
      return self.desire

    self.desire = RawDesire.NONE
    return self.desire

  def _reset_counts(self) -> None:
    self._turn_left_frames = 0
    self._turn_right_frames = 0
    self._lc_left_frames = 0
    self._lc_right_frames = 0

  def resolve(self,
              carrot_turn_left: bool,
              carrot_turn_right: bool,
              amap_turn_left: bool,
              amap_turn_right: bool,
              lane_turn_left: bool,
              lane_turn_right: bool,
              alc_left: bool,
              alc_right: bool,
              safety_veto: bool = False,
              log_desire: Any = None) -> Any:
    """High-level helper that returns the caller's ``log.Desire`` enum value."""
    raw = self.update(carrot_turn_left, carrot_turn_right,
                      amap_turn_left, amap_turn_right,
                      lane_turn_left, lane_turn_right,
                      alc_left, alc_right, safety_veto)
    if log_desire is None:
      # Avoid a hard import of log.Desire at module load so unit tests without
      # a cereal build can still import this module.
      from openpilot.cereal import log
      log_desire = log.Desire
    return self._to_log_desire(raw, log_desire)
