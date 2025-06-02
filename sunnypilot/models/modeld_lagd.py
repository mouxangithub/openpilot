"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import time
from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog


class ModeldLagd:
  def __init__(self):
    self._cached_lagd_toggle_state = False
    self._last_toggle_check_time = 0.0
    self._toggle_check_interval = 1.0
    self._update_cached_toggle_state()

  def _update_cached_toggle_state(self):
    self._cached_lagd_toggle_state = Params().get_bool("LagdToggle")
    self._last_toggle_check_time = time.monotonic()

  def lagd_main(self, CP, sm, model):
    current_time = time.monotonic()
    if (current_time - self._last_toggle_check_time) > self._toggle_check_interval:
      self._update_cached_toggle_state()

    if self._cached_lagd_toggle_state:
      lateral_delay = sm["liveDelay"].lateralDelay
      lat_smooth = model.LAT_SMOOTH_SECONDS
      result = lateral_delay + lat_smooth
      cloudlog.debug(f"LAGD USING LIVE DELAY: {lateral_delay:.3f} + {lat_smooth:.3f} = {result:.3f}")
      return result
    else:
      steer_actuator_delay = CP.steerActuatorDelay
      lat_smooth = model.LAT_SMOOTH_SECONDS
      result = (steer_actuator_delay + 0.2) + lat_smooth
      cloudlog.debug(f"LAGD USING STEER ACTUATOR: {steer_actuator_delay:.3f} + 0.2 + {lat_smooth:.3f} = {result:.3f}")
      return result
