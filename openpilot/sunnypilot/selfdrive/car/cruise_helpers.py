"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""

from openpilot.cereal import custom
from opendbc.car.structs import car
from opendbc.car import structs
from openpilot.common.params import Params

ButtonType = car.CarState.ButtonEvent.Type
EventNameSP = custom.OnroadEventSP.EventName

DISTANCE_LONG_PRESS = 50

# Number of entries in cereal's LongitudinalPersonality enum (aggressive/standard/
# relaxed). Used to clamp the value adopted from the car's own gap report; the MPC
# raises NotImplementedError for anything outside it, so this is a hard bound rather
# than a preference.
PERSONALITY_LEVELS = 3

# Ported from cp's carrot/cruise_gap.py. These bound the gap cycle the distance button
# drives and are kept as module functions so the policy has one home.
#
# Only 3- and 4-level vehicles are supported; anything else is treated as 3, matching cp.
# A reduced cycle (levels < vehicle max) still visits its own top gap before wrapping,
# which is what next_gap_personality's `0 < current < levels` ordering preserves.
def supported_gap_levels(value: int) -> int:
  return value if value in (3, 4) else 3


def cruise_gap_levels(requested: int, vehicle_max: int) -> int:
  maximum = supported_gap_levels(vehicle_max)
  return min(maximum, max(2, requested)) if requested > 0 else maximum


def next_gap_personality(current: int, levels: int) -> int:
  return current - 1 if 0 < current < levels else levels - 1


class CruiseHelper:
  def __init__(self, CP: structs.CarParams):
    self.CP = CP
    self.params = Params()

    self.button_frame_counts = {ButtonType.gapAdjustCruise: 0}
    self._experimental_mode = False
    self.experimental_mode_switched = False
    # Set on a fresh distance-button press, consumed once, so holding the button does
    # not walk the whole gap cycle.
    self._gap_press_pending = False

  def update(self, CS, events, experimental_mode) -> None:
    if self.CP.openpilotLongitudinalControl:
      if CS.cruiseState.available:
        self.update_button_frame_counts(CS)

        # toggle experimental mode once on distance button hold
        self.update_experimental_mode(events, experimental_mode)

        # A short press cycles the follow gap instead. Skipped while the long press is
        # in progress, so holding the button does not also change the gap.
        if self.button_frame_counts[ButtonType.gapAdjustCruise] < DISTANCE_LONG_PRESS:
          self.update_gap_personality(CS, events)

  def update_gap_personality(self, CS, events) -> None:
    if not self._gap_press_pending:
      return
    self._gap_press_pending = False

    """Advance LongitudinalPersonality when the distance button is tapped.

    Two cases, and the car decides which applies through ``CS.pcmCruiseGap``:

      * the car reports its own gap (pcmCruiseGap in 1..4, PCM-controlled distance
        button): adopt what the car says rather than counting presses, so our idea of the
        gap follows the one the driver sees on the cluster.
      * the car does not report it (0), or the configured cycle is shorter than the
        vehicle's maximum: count the presses ourselves.

    Ported from cp cruise.py:625-635. Kept in CruiseHelper rather than in the cruise
    button handler so the gap policy lives with the button it belongs to.
    """
    vehicle_max = supported_gap_levels(self.params.get_int("LongitudinalPersonalityMax"))
    gap_levels = cruise_gap_levels(self.params.get_int("CruiseGapLevels"), vehicle_max)
    if not self.CP.openpilotLongitudinalControl:
      gap_levels = vehicle_max

    pcm_gap = int(getattr(CS, "pcmCruiseGap", 0) or 0)
    if pcm_gap != 0 or gap_levels < vehicle_max:
      current = self.params.get_int("LongitudinalPersonality")
      personality = next_gap_personality(current, gap_levels)
    else:
      # The cluster reports gaps 1..N; LongitudinalPersonality is a 0-based enum of
      # PERSONALITY_LEVELS entries (aggressive/standard/relaxed). Clamp to the enum, not
      # to vehicle_max: a raw signal can carry a value wider than the enum and
      # log_mpc.get_T_FOLLOW raises NotImplementedError outside it.
      personality = min(max(pcm_gap - 1, 0), PERSONALITY_LEVELS - 1)

    self.params.put_int_nonblocking("LongitudinalPersonality", personality)

  def update_button_frame_counts(self, CS) -> None:
    for button in self.button_frame_counts:
      if self.button_frame_counts[button] > 0:
        self.button_frame_counts[button] += 1

    for button_event in CS.buttonEvents:
      button = button_event.type.raw
      if button in self.button_frame_counts:
        self.button_frame_counts[button] = int(button_event.pressed)
        if button == ButtonType.gapAdjustCruise and button_event.pressed:
          self._gap_press_pending = True

  def update_experimental_mode(self, events, experimental_mode) -> None:
    if self.button_frame_counts[ButtonType.gapAdjustCruise] >= DISTANCE_LONG_PRESS and not self.experimental_mode_switched:
      self._experimental_mode = not experimental_mode
      self.params.put_bool("ExperimentalMode", self._experimental_mode)
      events.add(EventNameSP.experimentalModeSwitched)
      self.experimental_mode_switched = True
