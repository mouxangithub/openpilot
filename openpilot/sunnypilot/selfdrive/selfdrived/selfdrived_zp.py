"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of zoompilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from openpilot.cereal import custom, log
from opendbc.car import structs
from openpilot.common.params import Params

ButtonType = structs.CarState.ButtonEvent.Type
EventName = log.OnroadEvent.EventName
EventNameSP = custom.OnroadEventSP.EventName

# selfdrived runs at 100 Hz
DISTANCE_LONG_PRESS = 50  # frames the distance button is held to switch experimental mode
PARAMS_READ_FRAMES = 100


class SelfdrivedZP:
  """zoompilot's additions to selfdrived: the experimental/chill switch (upstream went experimental
  only), the wheel's "farther" distance button and ICBM's activation following card."""

  def __init__(self, CP: structs.CarParams, params: Params | None = None):
    self.CP = CP
    self.params = params or Params()
    self.frame = 0

    self.experimental_mode = self._read_experimental_mode()
    self.gap_frames = 0
    self.experimental_mode_switched = False
    self.distance_farther_prev = False

  def _read_experimental_mode(self) -> bool:
    return self.CP.openpilotLongitudinalControl and self.params.get_bool("ExperimentalMode")

  def update(self, CS, CS_SP, events, events_sp, icbm, personality: int) -> int:
    """Run just before selfdrived's own personality step; returns the personality."""
    self.frame += 1
    if self.frame % PARAMS_READ_FRAMES == 0:
      self.experimental_mode = self._read_experimental_mode()

    if self.CP.openpilotLongitudinalControl:
      if CS.cruiseState.available:
        self._update_gap_frames(CS)
        # switch experimental mode once per distance button hold
        if self.gap_frames >= DISTANCE_LONG_PRESS and not self.experimental_mode_switched:
          self.experimental_mode = not self.experimental_mode
          # blocking: the alert reads the param back this frame to name the new mode
          self.params.put_bool("ExperimentalMode", self.experimental_mode, block=True)
          events_sp.add(EventNameSP.experimentalModeSwitchedDEPRECATED)
          self.experimental_mode_switched = True

      # the farther button steps the personality up, unless upstream's gapAdjustCruise release
      # steps it down this frame
      gap_released = any(not be.pressed and be.type == ButtonType.gapAdjustCruise for be in CS.buttonEvents)
      if self.distance_farther_released(CS_SP) and not gap_released:
        personality = (personality + 1) % 3
        self.params.put('LongitudinalPersonality', personality)
        events.add(EventName.personalityChanged)
    else:
      self.distance_farther_released(CS_SP)

    icbm.update_activation(CS_SP)
    return personality

  def gap_release_steps(self) -> bool:
    """For selfdrived's step on a gapAdjustCruise release: False for the release that ends a long
    press, which switched experimental mode instead."""
    switched, self.experimental_mode_switched = self.experimental_mode_switched, False
    return not switched

  def distance_farther_released(self, CS_SP) -> bool:
    """The release edge of the wheel's "farther" distance button (carStateSP.zoompilot), the
    opposite direction to upstream's gapAdjustCruise cycle. False on cars without one."""
    pressed = bool(CS_SP.zoompilot.distanceFarther)
    released = self.distance_farther_prev and not pressed
    self.distance_farther_prev = pressed
    return released

  def _update_gap_frames(self, CS) -> None:
    if self.gap_frames > 0:
      self.gap_frames += 1
    for be in CS.buttonEvents:
      if be.type == ButtonType.gapAdjustCruise:
        self.gap_frames = int(be.pressed)

  def publish(self, ss_sp) -> None:
    ss_sp.zoompilot.experimentalMode = self.experimental_mode
