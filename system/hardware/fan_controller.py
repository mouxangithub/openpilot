#!/usr/bin/env python3
import numpy as np

from openpilot.common.pid import PIDController
from openpilot.system.hardware import HARDWARE

# raise fan setpoint on tici/tizi to reduce noise
# after raising LMH threshold in AGNOS 18.1 to prevent CPU throttling
# (evaluates to 0 on mici, i.e. no bump)
OFFSET = 0 if HARDWARE.get_device_type() == "mici" else 5


class FanController:
  def __init__(self, rate: int) -> None:
    self.last_ignition = False
    self.controller = PIDController(k_p=0, k_i=4e-3, rate=rate)
    # dp: mici keeps the upstream 0.11.1 response; the older comma three / three X
    # run hotter with the +5C bump, so they use the classic pre-0.11.1 response.
    self._mici = HARDWARE.get_device_type() == "mici"

  def update(self, cur_temp: float, ignition: bool) -> int:
    self.controller.pos_limit = 100 if ignition else 30
    self.controller.neg_limit = 30 if ignition else 0

    if ignition != self.last_ignition:
      self.controller.reset()
    self.last_ignition = ignition

    if self._mici:
      # upstream 0.11.1 (OFFSET == 0 on mici)
      return int(self.controller.update(
                   error=(cur_temp - (75 + OFFSET)),  # temperature setpoint in C
                   feedforward=np.interp(cur_temp, [60.0 + OFFSET, 100.0 + OFFSET], [0, 100])
                ))

    # classic pre-0.11.1 (comma three / three X)
    return int(self.controller.update(
                 error=(cur_temp - 75),  # temperature setpoint in C
                 feedforward=np.interp(cur_temp, [60.0, 100.0], [0, 100])
              ))
