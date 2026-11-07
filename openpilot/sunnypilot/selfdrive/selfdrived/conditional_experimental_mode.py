"""
Copyright (c) 2026-, sunnypilot and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

Conditional Experimental Mode, a sunnypilot-shaped port of StarPilot's conditional_experimental_mode.

The StarPilot original lives inside its planner skeleton and scores conditions off StarPilotPlanner
attributes (model_length, lane widths, stop-sign latches). This port keeps the parts that only need
data selfdrived already subscribes to - curvature, radarState lead, blinkers - and drives the very
same ExperimentalMode param the manual switch uses, so planner/UI keep their single consumption path
(selfdriveStateSP.zoompilot.experimentalMode). No capnp change, no planner change.

Priority model: when the master switch is on, conditions own the mode; a manual switch (wheel long
press or onroad button) takes over for MANUAL_HOLD_SECONDS, after which conditions resume. At
standstill the current mode is frozen rather than re-evaluated.
"""
import time

import numpy as np

from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.common.params import Params
from opendbc.car import structs

# selfdrived runs at 100 Hz (Ratekeeper(100)); DT_CTRL inlined from common.realtime to keep
# this module importable on PC, where common.hardware (and its fcntl chain) is unavailable.
DT_CTRL = 0.01

# CEStatus values published on the memory params for UI/debugging: why EXP is on right now.
CE_OFF = 0
CE_CURVES = 1
CE_LEAD = 2
CE_SIGNAL = 3
CE_MANUAL = 4

# --- curve trigger ------------------------------------------------------------
CURVE_LAT_ACC = 2.0            # m/s^2 of lateral acceleration that counts as "demanding"
CURVE_FILTER_TIME = 0.8        # s; lower = snappier, higher = smoother
CURVE_MIN_EGO = 13.4           # m/s (~30 mph); curves at parking speeds are not highway curves
CURVE_THRESHOLD = 0.5          # filtered score that trips the trigger (filter input is bool)

# --- slow lead trigger ---------------------------------------------------------
LEAD_MAX_EGO = 35.31           # m/s (~79 mph); above this, slow leads stop switching modes
LEAD_CONTINUITY_MAX_TIME = 4.0
LEAD_CONTINUITY_MIN_DISTANCE = 40.0
LEAD_MIN_CLOSING_SPEED = 0.75  # m/s; slower closing speeds are just traffic, not a trigger
LEAD_FILTER_TIME = 0.8

# --- hysteresis ----------------------------------------------------------------
TRANSITION_GUARD_TIME = 0.50   # a trigger holds the mode this long even if it clears
TRANSITION_BUFFER_TIME = 0.25  # after the hold, this grace keeps the mode through flickers

# --- manual interaction ---------------------------------------------------------
MANUAL_HOLD_SECONDS = 60.0     # a manual switch muzzles the conditions for this long
PARAMS_READ_PERIOD = 1.0       # s; matches SelfdrivedZP's PARAMS_READ_FRAMES cadence


def _scale_threshold(v_ego: float) -> float:
  """Speed-scaled lead filter threshold, from StarPilot: harder to trip with speed."""
  bp = [0.0, 17.9, 26.8, 35.8, 44.7]
  fp = [0.58, 0.60, 0.62, 0.75, 0.90]
  return float(np.interp(v_ego, bp, fp))


class ConditionalExperimentalMode:
  def __init__(self, CP: structs.CarParams, params: Params | None = None, now_fn=time.monotonic):
    self.CP = CP
    self.params = params or Params()
    self._now = now_fn

    self.frame = 0
    self._params_read_frame = 0

    self.enabled = False
    self.curves_enabled = True
    self.curves_lead_enabled = True
    self.lead_enabled = True
    self.signal_speed = 0.0  # m/s; 0 disables the signal trigger

    self.curve_filter = FirstOrderFilter(0.0, CURVE_FILTER_TIME, DT_CTRL)
    self.lead_filter = FirstOrderFilter(0.0, LEAD_FILTER_TIME, DT_CTRL)

    self.experimental_mode = False
    self._last_written_mode: bool | None = None
    self._ce_status = CE_OFF
    self._last_ce_status_written: int | None = None

    self.mode_hold_until = 0.0
    self.mode_false_since = 0.0
    self.manual_hold_until = 0.0

    # initial read so toggles/configure values apply from the first frame, not after the
    # first 1 s refresh tick
    self._read_params()

  def _read_params(self) -> None:
    self.enabled = self.CP.openpilotLongitudinalControl and self.params.get_bool("ConditionalExperimental")
    # get_bool never consults the registered default, so default-on keys must go through
    # get(..., return_default=True) or an untouched install reads them as False.
    self.curves_enabled = bool(self.params.get("CECurves", return_default=True))
    self.curves_lead_enabled = bool(self.params.get("CECurvesLead", return_default=True))
    self.lead_enabled = bool(self.params.get("CELead", return_default=True))
    try:
      self.signal_speed = float(self.params.get("CESignalSpeed", return_default=True))
    except (TypeError, ValueError):
      self.signal_speed = 0.0

  @property
  def manual_override_active(self) -> bool:
    return self._now() < self.manual_hold_until

  def update(self, CS, sm) -> bool:
    """Run every selfdrived frame (100 Hz). Returns the experimental mode."""
    self.frame += 1
    now = self._now()

    if self.frame % int(PARAMS_READ_PERIOD / DT_CTRL) == 0:
      self._read_params()

    standstill = bool(CS.standstill)

    # A manual switch (wheel long press via selfdrived_zp, or the onroad button) writes the
    # ExperimentalMode param itself. Any divergence from what we last wrote is a driver action:
    # adopt it and muzzle the conditions for a while.
    if self._last_written_mode is not None and not self.manual_override_active:
      param_mode = self.params.get_bool("ExperimentalMode")
      if param_mode != self._last_written_mode:
        self.manual_hold_until = now + MANUAL_HOLD_SECONDS
        self.experimental_mode = param_mode

    if self.manual_override_active:
      self._reset_holds()
      self.experimental_mode = self.params.get_bool("ExperimentalMode")
      self._publish(self.experimental_mode, CE_MANUAL)
      return self.experimental_mode

    if not self.enabled:
      # Master switch off: pure manual behaviour, nothing to do. One publish so a stale
      # CEStatus gets cleared, then go quiet.
      self._publish(self.params.get_bool("ExperimentalMode"), CE_OFF)
      self._reset_holds()
      return self.experimental_mode

    if standstill:
      # Freeze: neither evaluate conditions nor drop the mode while stopped.
      return self.experimental_mode

    status, triggered = self._evaluate(CS, sm)

    if triggered:
      self.mode_hold_until = now + TRANSITION_GUARD_TIME
      self.mode_false_since = 0.0
    elif self.experimental_mode and self.mode_false_since == 0.0:
      self.mode_false_since = now
    elif not self.experimental_mode:
      self.mode_false_since = 0.0

    hold_active = now < self.mode_hold_until
    buffer_active = self.mode_false_since != 0.0 and (now - self.mode_false_since) < TRANSITION_BUFFER_TIME
    self.experimental_mode = triggered or hold_active or buffer_active

    ce_value = status if self.experimental_mode else CE_OFF
    self._publish(self.experimental_mode, ce_value)
    return self.experimental_mode

  def _evaluate(self, CS, sm) -> tuple[int, bool]:
    """Returns (status_if_triggered, triggered). Conditions ordered by priority."""
    v_ego = float(CS.vEgo)

    following_lead = self._following_lead(sm)

    if self.curves_enabled and (self.curves_lead_enabled or not following_lead):
      if self._curve_detected(sm, v_ego):
        return CE_CURVES, True

    if self.lead_enabled and v_ego <= LEAD_MAX_EGO and self._slow_lead(sm, v_ego):
      return CE_LEAD, True

    if self.signal_speed > 0.0 and v_ego < self.signal_speed and (CS.leftBlinker or CS.rightBlinker):
      return CE_SIGNAL, True

    return CE_OFF, False

  def _curve_detected(self, sm, v_ego: float) -> bool:
    if v_ego <= CURVE_MIN_EGO:
      self.curve_filter.update(0.0)
      return False

    try:
      curvature = abs(float(sm["controlsState"].desiredCurvature))
    except (KeyError, TypeError, AttributeError):
      self.curve_filter.update(0.0)
      return False

    lat_acc = curvature * v_ego * v_ego
    self.curve_filter.update(lat_acc >= CURVE_LAT_ACC)
    return bool(self.curve_filter.x >= CURVE_THRESHOLD)

  def _slow_lead(self, sm, v_ego: float) -> bool:
    try:
      lead = sm["radarState"].leadOne
      lead_status = bool(lead.status)
      lead_distance = float(lead.dRel)
      lead_speed = float(lead.vLead)
    except (KeyError, TypeError, AttributeError):
      self.lead_filter.update(0.0)
      return False

    if not lead_status:
      self.lead_filter.update(0.0)
      return False

    closing_speed = max(0.0, v_ego - lead_speed)
    min_closing_speed = max(LEAD_MIN_CLOSING_SPEED, 0.04 * v_ego)
    in_range = lead_distance < max(LEAD_CONTINUITY_MIN_DISTANCE, v_ego * LEAD_CONTINUITY_MAX_TIME)

    candidate = bool(in_range and closing_speed >= min_closing_speed and lead_speed < v_ego - 0.5)
    self.lead_filter.update(candidate)
    return bool(self.lead_filter.x >= _scale_threshold(v_ego))

  @staticmethod
  def _following_lead(sm) -> bool:
    try:
      return bool(sm["radarState"].leadOne.status)
    except (KeyError, TypeError, AttributeError):
      return False

  def _publish(self, mode: bool, ce_status: int) -> None:
    if mode != self._last_written_mode:
      self.params.put_bool("ExperimentalMode", mode)
      self._last_written_mode = mode
    if ce_status != self._last_ce_status_written:
      try:
        self.params.put_int("CEStatus", ce_status)
      except Exception:
        pass  # CEStatus is a UI hint only; never let it break the mode logic
      self._last_ce_status_written = ce_status
    self._ce_status = ce_status

  def _reset_holds(self) -> None:
    self.mode_hold_until = 0.0
    self.mode_false_since = 0.0
