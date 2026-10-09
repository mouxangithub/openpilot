"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""

import numpy as np

from opendbc.sunnypilot.car.interfaces import get_tune_scale
from openpilot.common.params import Params


class LatControlTorqueExtOverride:
  def __init__(self, CP):
    self.CP = CP
    self.params = Params()
    self.enforce_torque_control_toggle = self.params.get_bool("EnforceTorqueControl")  # only during init
    self.torque_override_enabled = self.params.get_bool("TorqueParamsOverrideEnabled")
    self.frame = -1
    # cached at the 3 s poll below; preloaded so the values are valid from frame 0
    self._override_lat_accel_factor = float(self.params.get("TorqueParamsOverrideLatAccelFactor", return_default=True))
    self._override_friction = float(self.params.get("TorqueParamsOverrideFriction", return_default=True))

    # Speed-dep state (set by LatControlTorqueExt subclass)
    self._speed_dep_active = False
    self._speed_dep_speed_bp = []
    self._speed_dep_lat_accel_factor_bp = []
    self._speed_dep_friction_bp = []
    self._speed_dep_car_cfg = None
    self._last_vego = 0.0

    # The manual override is typed on the scale upstream's tunes use (TUNE_STEER_MAX), which is
    # 1.5x off the Mazda EPS envelope's STEER_MAX; 1.0 everywhere else.
    self._tune_scale = get_tune_scale(CP)

  @staticmethod
  def _write_torque_params(torque_params, lat_accel_factor: float, friction: float) -> bool:
    # torque_params is a capnp Float32 builder: compare in float32 or update_limits runs every frame
    lat_accel_factor = float(np.float32(lat_accel_factor))
    friction = float(np.float32(friction))
    if lat_accel_factor == torque_params.latAccelFactor and friction == torque_params.friction:
      return False
    torque_params.latAccelFactor = lat_accel_factor
    torque_params.friction = friction
    return True

  def update_override_torque_params(self, torque_params) -> bool:
    changed = False

    # Manual override first: it must own the params on every frame, or the speed-dep interp
    # below out-writes it between the 3 s polls. The cached values apply each frame.
    if self.enforce_torque_control_toggle:
      self.frame += 1
      if self.frame % 300 == 0:
        self.torque_override_enabled = self.params.get_bool("TorqueParamsOverrideEnabled")
        if self.torque_override_enabled:
          self._override_lat_accel_factor = float(self.params.get("TorqueParamsOverrideLatAccelFactor", return_default=True))
          self._override_friction = float(self.params.get("TorqueParamsOverrideFriction", return_default=True))

      if self.torque_override_enabled:
        return self._write_torque_params(torque_params, self._override_lat_accel_factor * self._tune_scale,
                                         self._override_friction / self._tune_scale)

    # Speed-dep latAccelFactor and friction, interpolated by speed each frame.
    if self._speed_dep_active and self._speed_dep_speed_bp:
      new_lat_accel_factor = float(np.interp(self._last_vego, self._speed_dep_speed_bp, self._speed_dep_lat_accel_factor_bp))
      new_fric = float(np.interp(self._last_vego, self._speed_dep_speed_bp, self._speed_dep_friction_bp))
      changed = self._write_torque_params(torque_params, new_lat_accel_factor, new_fric)

    return changed
