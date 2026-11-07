from __future__ import annotations
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""
Carrot-specific lateral control overrides.

Ported and adapted from CarrotPilot's selfdrive/carrot/carrot_controls.py.
The lat-suspend feature temporarily disables lateral actuation when the driver
is applying large steering torque at a large steering angle. This matches the
behavior expected by CarrotPilot users and prevents the controller from
fighting the driver during tight turns or parking maneuvers.
"""

from openpilot.common.realtime import DT_CTRL
from openpilot.common.params import Params


class CarrotControls:
  """Carrot lat-suspend: pause lateral actuation while the driver steers hard.

  This used to be applied by controlsd.py *after* the sunnypilot lateral-enable
  arbitration, which made it a second, independent gate on CC.latActive. It is now a
  pure predicate consulted from inside ControlsExt.get_lat_active, so there is one
  place that decides whether lateral is active.
  """

  def __init__(self, CP):
    self.CP = CP
    self.params = Params()
    self.lat_suspend_active = False
    self.lat_suspend_enter_t = 0.0
    self.lat_suspend_hold_t = 0.0
    self.enabled = False
    self._param_update_t = 0.0

  def update_params(self):
    """Refresh the master switch. Called from get_params_sp at PARAMS_UPDATE_PERIOD."""
    self.enabled = self.params.get_bool("CarrotEnabled")

  def wants_suspend(self, CS) -> bool:
    """True when carrot wants lateral paused right now. Never touches latActive."""
    if not self.enabled:
      return False

    suspend_angle = float(self.params.get("LatSuspendAngleDeg"))
    resume_angle = 15.0
    delay_sec = 1.0
    hold_sec = 0.5

    # Enter condition: driver is actively steering at a large angle.
    enter_cond = CS.steeringPressed and abs(CS.steeringAngleDeg) > suspend_angle
    if not self.lat_suspend_active:
      if enter_cond:
        self.lat_suspend_enter_t += DT_CTRL
        if self.lat_suspend_enter_t >= delay_sec:
          self.lat_suspend_active = True
          self.lat_suspend_hold_t = 0.0
      else:
        self.lat_suspend_enter_t = 0.0

    # While suspended: enforce minimum hold time plus hysteresis exit.
    if self.lat_suspend_active:
      self.lat_suspend_hold_t += DT_CTRL

      exit_cond = (abs(CS.steeringAngleDeg) < resume_angle) and (not CS.steeringPressed)
      if (self.lat_suspend_hold_t >= hold_sec) and exit_cond:
        self.lat_suspend_active = False
        self.lat_suspend_enter_t = 0.0

    return self.lat_suspend_active
