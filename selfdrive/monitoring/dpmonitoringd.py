#!/usr/bin/env python3
import time
import cereal.messaging as messaging
from openpilot.common.params import Params
from openpilot.common.realtime import config_realtime_process, Ratekeeper, DT_DMON
from cereal import log

EventName = log.OnroadEvent.EventName

class SimpleDriverMonitoring:
  def __init__(self):
    # Timing configuration (in seconds)
    self.FIRST_WARNING_TIME = 45.0
    self.SECOND_WARNING_TIME = 60.0
    self.THIRD_WARNING_TIME = 75.0

    # State variables
    self.awareness = 1.0  # Full awareness
    self.current_events = []
    # self.last_interaction_time = 0
    self.hands_on_steering = False

    # Warning thresholds (normalized to 0-1 scale)
    self.threshold_prompt = self.FIRST_WARNING_TIME / self.THIRD_WARNING_TIME  # ~0.643 for first warning
    self.threshold_critical = self.SECOND_WARNING_TIME / self.THIRD_WARNING_TIME  # ~0.857 for second warning

    # Step change (how much awareness decreases per step)
    self.step_change = DT_DMON / self.THIRD_WARNING_TIME

    params = Params()
    self.is_rhd = params.get_bool("dp_device_is_rhd")
    self.monitoring_disabled = params.get_bool("dp_device_monitoring_disabled")

  def update_events(self, reset_condition, op_engaged):
    self.current_events = []

    if self.monitoring_disabled:
      return

    # If not engaged, reset awareness and return
    if not op_engaged:
      self.awareness = 1.0
      return

    # Reset awareness on any reset condition (standstill, any input)
    if reset_condition:
      self.awareness = 1.0
      return

    # Only decrease awareness if we're not detecting hands on steering
    self.awareness = max(self.awareness - self.step_change, 0.0)

    # Determine alert level based on awareness
    if self.awareness <= 0.0:
      # Third warning (red alert) at 70 seconds
      self.current_events.append(EventName.driverUnresponsive)
    elif self.awareness <= (1.0 - self.threshold_critical):
      # Second warning (orange alert) at 60 seconds
      self.current_events.append(EventName.promptDriverUnresponsive)
    elif self.awareness <= (1.0 - self.threshold_prompt):
      # First warning (green alert) at 45 seconds
      self.current_events.append(EventName.preDriverUnresponsive)

  def get_state_packet(self, valid=True):
    # Create driver monitoring state message
    dat = messaging.new_message('driverMonitoringState', valid=valid)
    events = []

    for event_name in self.current_events:
      event = log.OnroadEvent.new_message()
      event.name = event_name
      events.append(event)

    dat.driverMonitoringState = {
      "events": events,
      "faceDetected": False,  # Not using face detection
      "isDistracted": self.awareness <= (1.0 - self.threshold_prompt),
      "distractedType": 0,  # Not using distraction types
      "awarenessStatus": 1.0, #self.awareness, (always 1.0 so no decel)
      "posePitchOffset": 0.0,
      "posePitchValidCount": 0,
      "poseYawOffset": 0.0,
      "poseYawValidCount": 0,
      "stepChange": self.step_change,
      "awarenessActive": self.awareness,
      "awarenessPassive": self.awareness,
      "isLowStd": True,
      "hiStdCount": 0,
      "isActiveMode": True,
      "isRHD": self.is_rhd,
    }
    return dat

def dmonitoringd_thread():
  # Configure process priority
  config_realtime_process([0, 1, 2, 3], 5)

  # Initialize parameters and messaging
  pm = messaging.PubMaster(['driverMonitoringState'])
  sm = messaging.SubMaster(['carState', 'selfdriveState'])

  # Initialize driver monitoring system
  DM = SimpleDriverMonitoring()

  # Create ratekeeper for 20Hz operation
  rk = Ratekeeper(20, None)

  # Main loop running at 20Hz
  while True:
    sm.update()

    # Check if steering is touched (only monitoring steering for hands-on)

    # Reset conditions: not engaged, standstill, or any input
    reset_condition = (
      sm['carState'].standstill or
      sm['carState'].steeringPressed or
      sm['carState'].gasPressed or
      sm['carState'].brakePressed or
      sm['carState'].leftBlinker or
      sm['carState'].rightBlinker
    )

    # Process driver monitoring - monitoring only steering for hands-on
    # but resetting on any input
    DM.update_events(
      reset_condition=reset_condition,
      op_engaged=sm['selfdriveState'].enabled
    )

    # Publish driver monitoring state
    dat = DM.get_state_packet()
    pm.send('driverMonitoringState', dat)

    # Maintain 20Hz
    rk.keep_time()

def main():
  dmonitoringd_thread()

if __name__ == '__main__':
  main()
