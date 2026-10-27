"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of zoompilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from openpilot.cereal import custom, log
from opendbc.car import structs
from openpilot.common.params import Params
from openpilot.sunnypilot.selfdrive.car.cruise_ext import update_manual_button_timers
from openpilot.sunnypilot.selfdrive.controls.lib.relc import RoadEdgeMode, read_road_edge_mode

ButtonType = structs.CarState.ButtonEvent.Type
EventName = log.OnroadEvent.EventName
EventNameSP = custom.OnroadEventSP.EventName

# StarPilot's lateral-only experimental allow-list (starpilot/common/lateral_only_experimental.py),
# copied verbatim: stock-ACC platforms that may run Experimental Mode for lateral/model testing
# while the longitudinal actuator gate stays closed. Kept narrow on purpose so stock-ACC
# vehicles do not gain an experimental control path accidentally.
# sp's opendbc does not fingerprint HYUNDAI_PALISADE_2023 as its own platform yet, so the
# allow-list matches nothing today and lights up when the platform is ported.
LATERAL_ONLY_EXPERIMENTAL_CARS = frozenset({
  "HYUNDAI_PALISADE_2023",  # StarPilot CAR.HYUNDAI_PALISADE_2023 (also identifies 2023+ Kia Telluride)
})


def lateral_only_experimental_available(CP) -> bool:
  """Return whether this car may expose Experimental Mode without openpilot long."""
  return (
    not bool(getattr(CP, "openpilotLongitudinalControl", False)) and
    getattr(CP, "carFingerprint", None) in LATERAL_ONLY_EXPERIMENTAL_CARS
  )


# selfdrived runs at 100 Hz
DISTANCE_LONG_PRESS = 50  # frames the distance button is held to switch experimental mode
PARAMS_READ_FRAMES = 100


class SelfdrivedZP:
  """zoompilot's additions to selfdrived: the experimental/chill switch (upstream went experimental
  only), the wheel's "farther" distance button, ICBM's activation following card and the road edge
  alert's sound."""

  # the mode the last long press switched to, for the alert (one selfdrived per process)
  switched_to: bool = True
  # RoadEdgeLaneChangeEnabled is silent: the road edge alert drops its chime
  road_edge_silent: bool = False

  def __init__(self, CP: structs.CarParams, params: Params | None = None):
    self.CP = CP
    self.params = params or Params()
    self.frame = 0

    # Experimental Mode is valid with openpilot long, or on a lateral-only whitelist car
    # (stock ACC) - StarPilot's experimental_mode_available, see the allow-list above.
    self.experimental_mode_available = self.CP.openpilotLongitudinalControl or lateral_only_experimental_available(self.CP)
    self.experimental_mode = self._read_experimental_mode()
    self._read_road_edge_silent()
    self.gap_timers = {ButtonType.gapAdjustCruise: 0}
    self.experimental_mode_switched = False
    # upstream steps the personality down on a gapAdjustCruise release unless it ended a long press
    self.gap_release_steps = True
    self.distance_farther_prev = False

  def _read_experimental_mode(self) -> bool:
    return self.experimental_mode_available and self.params.get_bool("ExperimentalMode")

  def _read_road_edge_silent(self) -> None:
    SelfdrivedZP.road_edge_silent = read_road_edge_mode(self.params) == RoadEdgeMode.SILENT

  def update(self, CS, CS_SP, events, events_sp, icbm, personality: int) -> int:
    """Run just before selfdrived's own personality step; returns the personality."""
    self.frame += 1
    if self.frame % PARAMS_READ_FRAMES == 0:
      self.experimental_mode = self._read_experimental_mode()
      self._read_road_edge_silent()

    self.gap_release_steps = True
    if self.experimental_mode_available:
      gap_released = any(not be.pressed and be.type == ButtonType.gapAdjustCruise for be in CS.buttonEvents)
      if CS.cruiseState.available:
        update_manual_button_timers(CS, self.gap_timers)
        # switch experimental mode once per distance button hold
        if self.gap_timers[ButtonType.gapAdjustCruise] >= DISTANCE_LONG_PRESS and not self.experimental_mode_switched:
          self.experimental_mode = not self.experimental_mode
          self.params.put_bool("ExperimentalMode", self.experimental_mode)
          # A wheel-button long press is the driver's own acknowledgement, so
          # enabling also records the confirmation bit; disabling leaves it alone.
          # (Inherited from the sp CruiseHelper this class replaced.)
          if self.experimental_mode:
            self.params.put_bool("ExperimentalModeConfirmed", True)
          SelfdrivedZP.switched_to = self.experimental_mode
          events_sp.add(EventNameSP.experimentalModeSwitchedDEPRECATED)
          self.experimental_mode_switched = True
      if gap_released:
        self.gap_release_steps = not self.experimental_mode_switched
        self.experimental_mode_switched = False

      # the farther button steps the personality up, unless upstream's gapAdjustCruise release
      # steps it down this frame. Longitudinal personality has no actuator to act on without
      # openpilot long, so the step stays long-only (lateral-only whitelist cars skip it).
      if self.distance_farther_released(CS_SP) and not gap_released and self.CP.openpilotLongitudinalControl:
        personality = (personality + 1) % 3
        self.params.put('LongitudinalPersonality', personality)
        events.add(EventName.personalityChanged)
    else:
      self.distance_farther_released(CS_SP)

    icbm.update_activation(CS_SP)
    return personality

  def distance_farther_released(self, CS_SP) -> bool:
    """The release edge of the wheel's "farther" distance button (carStateSP.zoompilot), the
    opposite direction to upstream's gapAdjustCruise cycle. False on cars without one."""
    pressed = bool(CS_SP.zoompilot.distanceFarther)
    released = self.distance_farther_prev and not pressed
    self.distance_farther_prev = pressed
    return released

  def publish(self, ss_sp) -> None:
    ss_sp.zoompilot.experimentalMode = self.experimental_mode
