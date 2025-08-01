#!/usr/bin/env python3
import numpy as np
import time

import openpilot.system.sentry as sentry

from cereal import messaging
from common.filter_simple import FirstOrderFilter
from common.realtime import DT_CTRL

from openpilot.frogpilot.common.frogpilot_utilities import wait_for_no_driver

MOVEMENT_THRESHOLD = 0.01
MOVEMENT_TIME = 60
SENTRY_COOLDOWN_TIME = MOVEMENT_TIME + 5

class SentryMode:
  def __init__(self):
    self.sm = messaging.SubMaster(["accelerometer", "deviceState", "driverMonitoringState", "managerState", "pandaStates"], poll="accelerometer")

    self.sentry_tripped = False

    self.movement_timestamp = 0
    self.sentry_tripped_timestamp = 0

    self.acceleration_filters = [FirstOrderFilter(0, 0.5, DT_CTRL) for _ in range(3)]

    self.previous_accelerations = None

  def update(self):
    self.sm.update()

    accelerations = self.sm["accelerometer"].acceleration.v
    if len(accelerations) == 3:
      if self.previous_accelerations is not None:
        acceleration_change = np.array(accelerations) - np.array(self.previous_accelerations)
        for idx in range(3):
          self.acceleration_filters[idx].update(acceleration_change[idx])

      self.previous_accelerations = accelerations

    self.check_for_movement()

  def check_for_movement(self):
    now_timestamp = time.monotonic()

    movement = any(abs(acceleration_filter.x) > MOVEMENT_THRESHOLD for acceleration_filter in self.acceleration_filters)
    if movement:
      self.movement_timestamp = float(now_timestamp)

    reset_tripped_state = now_timestamp - self.movement_timestamp > MOVEMENT_TIME
    reset_tripped_state &= now_timestamp - self.sentry_tripped_timestamp > SENTRY_COOLDOWN_TIME

    if movement:
      sentry_tripped = True
    elif self.sentry_tripped and not reset_tripped_state:
      sentry_tripped = True
    else:
      sentry_tripped = False

    if sentry_tripped and not self.sentry_tripped:
      self.sentry_tripped_timestamp = time.monotonic()

    self.sentry_tripped = sentry_tripped

def main():
  sentry_mode = SentryMode()

  try:
    while True:
      wait_for_no_driver(sentry_mode.sm, True)

      sentry_mode.update()

      if sentry_mode.sentry_tripped:
        print(f"*** ALERT: Sentry tripped at {sentry_mode.sentry_tripped_timestamp} ***\n")
  except Exception as exception:
    print(f"An error occurred: {exception}")
    sentry.capture_exception(exception)

if __name__ == "__main__":
  main()
