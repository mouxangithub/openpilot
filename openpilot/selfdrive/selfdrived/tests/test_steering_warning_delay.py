"""The temporary-steering warning is presented only after 120 ms of accumulated
faults - but the event itself never waits.

Why this exists
---------------
`steerTempUnavailable` fires for single-frame steering hiccups, and an alert
that flashes for one frame trains the driver to ignore it. The delay in
`Events.create_alerts` withholds only the rendered WARNING/SOFT_DISABLE alert;
the event stays in `self.events`, so the state machine, the soft-disable timer,
no-entry and critical takeover alerts are untouched. These tests pin both
halves of that promise.

Adapted from cp commit 6a33883d's suite. unittest so it runs on the device
(PC still lacks a compiled msgq, which `events.py` imports at module level).
"""

import unittest

from openpilot.cereal import log
from opendbc.car.structs import car
from openpilot.selfdrive.selfdrived.alertmanager import AlertManager
from openpilot.selfdrive.selfdrived.events import AlertStatus, ET, Events
from openpilot.selfdrive.selfdrived.state import StateMachine
from openpilot.sunnypilot.selfdrive.selfdrived.events_base import EmptyAlert

EventName = log.OnroadEvent.EventName
State = log.SelfdriveState.OpenpilotState


def callback_args(brand="hyundai", control="torque", flags=0, timer=300):
  return [car.CarParams(brand=brand, steerControlType=control, flags=flags), car.CarState(),
          None, False, timer, log.LongitudinalPersonality.standard]


def tick(events, event, args=None):
  events.clear()
  if event is not None:
    events.add(event)
  return events.create_alerts([ET.SOFT_DISABLE, ET.WARNING], args or callback_args())


class TestThePresentationDelay(unittest.TestCase):
  def test_twelve_completed_cycles_before_the_warning(self):
    for event in (EventName.steerTempUnavailable, EventName.steerTempUnavailableSilent):
      events = Events()
      args = callback_args()
      for cycle in range(14):
        with self.subTest(event=event, cycle=cycle):
          alerts = tick(events, event, args)
          self.assertEqual(bool(alerts), cycle >= 12)
          self.assertIn(event, events.names)
          self.assertTrue(events.contains(ET.SOFT_DISABLE if event == EventName.steerTempUnavailable else ET.WARNING))

  def test_short_fault_does_not_reach_alert_manager(self):
    events, manager = Events(), AlertManager()
    for frame in range(230):
      alerts = tick(events, EventName.steerTempUnavailable if frame < 7 else None)
      manager.add_many(frame, alerts)
      manager.process_alerts(frame, set())
      self.assertIs(manager.current_alert, EmptyAlert)

  def test_repeated_short_faults_accumulate_without_alerting_while_clear(self):
    events = Events()
    for _ in range(7):
      self.assertFalse(tick(events, EventName.steerTempUnavailable))
    for _ in range(3):
      self.assertFalse(tick(events, None))
    for cycle in range(7):
      with self.subTest(cycle=cycle):
        self.assertEqual(bool(tick(events, EventName.steerTempUnavailable)), cycle >= 5)
    self.assertFalse(tick(events, None))
    self.assertTrue(tick(events, EventName.steerTempUnavailable))

  def test_full_second_without_temporary_event_resets_delay(self):
    for healthy_cycles, immediate in ((99, True), (100, False)):
      with self.subTest(healthy_cycles=healthy_cycles):
        events = Events()
        for _ in range(13):
          tick(events, EventName.steerTempUnavailable)
        for _ in range(healthy_cycles):
          self.assertFalse(tick(events, None))
        self.assertEqual(bool(tick(events, EventName.steerTempUnavailable)), immediate)

  def test_silent_and_audible_variants_share_history(self):
    events = Events()
    for cycle in range(14):
      with self.subTest(cycle=cycle):
        event = EventName.steerTempUnavailable if cycle % 2 else EventName.steerTempUnavailableSilent
        self.assertEqual(bool(tick(events, event)), cycle >= 12)

  def test_repeated_rendering_and_duplicate_events_do_not_advance_time(self):
    events = Events()
    events.add(EventName.steerTempUnavailable)
    events.add(EventName.steerTempUnavailable)
    for _ in range(100):
      self.assertFalse(events.create_alerts([ET.SOFT_DISABLE], callback_args()))
    for cycle in range(12):
      with self.subTest(cycle=cycle):
        self.assertEqual(bool(tick(events, EventName.steerTempUnavailable)), cycle == 11)


class TestWhatTheDelayMustNotTouch(unittest.TestCase):
  def test_no_entry_and_serialized_event_remain_immediate(self):
    events = Events()
    self.assertFalse(tick(events, EventName.steerTempUnavailable))
    self.assertTrue(events.contains(ET.NO_ENTRY))
    self.assertTrue(events.create_alerts([ET.NO_ENTRY], callback_args()))
    message, = events.to_msg()
    self.assertTrue(message.noEntry)
    self.assertTrue(message.softDisable)

  def test_critical_takeover_bypasses_delay(self):
    events = Events()
    alert, = tick(events, EventName.steerTempUnavailable, callback_args(timer=49))
    self.assertEqual(alert.alert_status, AlertStatus.critical)
    self.assertEqual(alert.audible_alert, car.CarControl.HUDControl.AudibleAlert.warningImmediate)

  def test_other_faults_remain_immediate(self):
    for event, kind in ((EventName.steerUnavailable, ET.IMMEDIATE_DISABLE),
                        (EventName.canError, ET.IMMEDIATE_DISABLE),
                        (EventName.vehicleSensorsInvalid, ET.IMMEDIATE_DISABLE),
                        (EventName.overheat, ET.SOFT_DISABLE)):
      with self.subTest(event=event, kind=kind):
        events = Events()
        events.add(event)
        self.assertTrue(events.create_alerts([kind], callback_args()))

  def test_short_fault_keeps_existing_state_machine_recovery(self):
    events, machine = Events(), StateMachine()
    machine.state = State.enabled
    for cycle in range(7):
      with self.subTest(cycle=cycle):
        self.assertFalse(tick(events, EventName.steerTempUnavailable))
        enabled, active = machine.update(events)
        self.assertTrue(enabled and active)
        self.assertEqual(machine.state, State.softDisabling)
        self.assertEqual(machine.soft_disable_timer, 300 - cycle)
    tick(events, None)
    self.assertEqual(machine.update(events), (True, True))
    self.assertEqual(machine.state, State.enabled)

  def test_persistent_fault_does_not_extend_soft_disable_deadline(self):
    events, machine = Events(), StateMachine()
    machine.state = State.enabled
    for cycle in range(301):
      tick(events, EventName.steerTempUnavailable)
      machine.update(events)
      self.assertEqual(machine.state, State.softDisabling if cycle < 300 else State.disabled)


if __name__ == "__main__":
  unittest.main()
