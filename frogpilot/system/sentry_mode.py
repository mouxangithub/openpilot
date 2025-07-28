#!/usr/bin/env python3
import numpy as np
import time

import cereal.messaging as messaging
import openpilot.system.sentry as sentry

from cereal.services import SERVICE_LIST
from openpilot.common.realtime import Ratekeeper

DETECTED_INSIDE_TIME = 5.0
GRAVITY = 9.81
HIT_THRESHOLD = 2.5
INSIDE_THRESHOLD = 0.1
SENSOR_FREQ = SERVICE_LIST["accelerometer"].frequency

class SentryMode:
  def __init__(self):
    self.sm = messaging.SubMaster(["accelerometer"])

    self.inside_motion_threshold = int(DETECTED_INSIDE_TIME * SENSOR_FREQ)

    self.inside_motion_counter = 0

  def update(self):
    self.sm.update()

    if not self.sm.updated["accelerometer"]:
      return None

    acceleration_delta = abs(np.linalg.norm(self.sm["accelerometer"].acceleration.v) - GRAVITY)
    print(f"acceleration_delta = {acceleration_delta:.2f} m/s^2")

    if acceleration_delta > HIT_THRESHOLD:
      print(f"EVENT: Vehicle HIT detected! Δg = {acceleration_delta:.2f} m/s^2")
      self.inside_motion_counter = 0
      return "HIT"

    if acceleration_delta > INSIDE_THRESHOLD:
      self.inside_motion_counter += 1

      if self.inside_motion_counter >= self.inside_motion_threshold:
        print(f"EVENT: Sustained motion detected! Person likely INSIDE. (Δg = {acceleration_delta:.2f} m/s^2)")
        self.inside_motion_counter = 0
        return "INSIDE"
    else:
      self.inside_motion_counter = 0

    return None

def main():
  rate_keeper = Ratekeeper(SENSOR_FREQ, None)
  sentry_mode = SentryMode()

  try:
    while True:
      event = sentry_mode.update()
      if event:
        print(f"*** ALERT: Event '{event}' triggered at {time.ctime()} ***\n")

      rate_keeper.keep_time()
  except Exception as error:
    print(f"An error occurred: {error}")
    sentry.capture_exception(error)

if __name__ == "__main__":
  main()
