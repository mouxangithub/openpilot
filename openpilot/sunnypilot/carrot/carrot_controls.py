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
  def __init__(self, CP):
    self.CP = CP
    self.params = Params()
    self.lat_suspend_active = False
    self.lat_suspend_enter_t = 0.0
    self.lat_suspend_hold_t = 0.0

  def lat_suspend_control(self, CS, latActive):
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

    if self.lat_suspend_active:
      latActive = False
    return latActive
