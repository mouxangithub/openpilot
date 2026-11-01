"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Tests for the wheel_controls store and daemon on injected fakes: a fake clock, fake
params, a fake command publisher, a recorded favorite-slot applier and tmp file paths.
Nothing here touches a real /dev/input or Params - the daemon drives itself through the
same entry points a real event would."""
import tempfile
import unittest
from unittest import mock

from openpilot.sunnypilot.system.wheel_controls import store, wheel_controlsd
from openpilot.sunnypilot.system.wheel_controls.wheel_controlsd import WheelControlsDaemon


class _TempDirTestCase(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    self.config_path = f"{self.tmp.name}/wheel_controls.json"
    self.control_path = f"{self.tmp.name}/control.json"
    self.status_path = f"{self.tmp.name}/status.json"


class FakeClock:
  def __init__(self):
    self.now = 1000.0

  def __call__(self):
    return self.now

  def advance(self, seconds):
    self.now += seconds


class FakeParams:
  def __init__(self, **values):
    self.values = {"IsOffroad": True, "IsEngaged": False, "SafeMode": False}
    self.values.update(values)
    self.puts = {}

  def get_bool(self, key):
    return bool(self.values.get(key))

  def get_int(self, key):
    return int(self.values.get(key, 0))

  def put_int(self, key, value):
    self.puts[key] = value


class FakePublisher:
  def __init__(self):
    self.sent = []

  def send_merged(self, address, action, now):
    self.sent.append((address, action, now))


class FakeSource(store.InputSource):
  @classmethod
  def make(cls, device_id="abc123"):
    return cls(path="/dev/input/event5", device_id=device_id, name="Test Gamepad", bus=3, vendor=1, product=2)


class TestStore(_TempDirTestCase):
  def test_config_roundtrip_and_sanitize(self):
    written = store.write_config({
      "mappings": [{"device_id": "abc", "device_name": "Pad", "event_code": 42, "slot": 3}],
      "action_slots": [{"enabled": True, "key": "accelCruise", "label": "Resume"}],
      "enabled": True, "joystick_device": "abc",
    }, self.config_path)
    self.assertEqual(["accelCruise"], [slot["key"] for slot in written["action_slots"] if slot["enabled"]])
    self.assertTrue(written["enabled"])
    read = store.read_config(self.config_path)
    self.assertEqual(written, read)

  def test_normalize_mappings_rejects_and_dedups(self):
    value = [
      {"device_id": "a", "event_code": 1, "slot": 0},
      {"device_id": "a", "event_code": 1, "slot": 5},  # duplicate signature
      {"device_id": "a", "event_code": 2, "slot": 99},  # out of range
      {"device_id": "", "event_code": 3, "slot": 0},  # no device
      "garbage",
    ]
    mappings = store.normalize_mappings(value)
    self.assertEqual(1, len(mappings))
    self.assertEqual(0, mappings[0]["slot"])
    self.assertEqual(store.mapping_id("a", 1), mappings[0]["id"])

  def test_normalize_action_slots_only_known_keys(self):
    slots = store.normalize_action_slots([
      {"key": "accelCruise", "label": "Resume"},
      {"key": "__not_an_action__"},
      {"key": "cancel"},
    ])
    self.assertTrue(slots[0]["enabled"])
    self.assertEqual("accelCruise", slots[0]["key"])
    self.assertFalse(slots[1]["enabled"])
    self.assertIsNone(slots[1]["key"])
    self.assertTrue(slots[2]["enabled"])

  def test_event_names_for_hat_switch(self):
    self.assertEqual("DPAD_RIGHT", store.event_name(store.hat_event_code(store.ABS_HAT0X, 1)))
    self.assertEqual("DPAD_UP", store.event_name(store.hat_event_code(store.ABS_HAT0X + 1, -1)))
    # unknown-keycode fallback: independent of whether the optional `inputs` package
    # (which gives real key names like KEY_LEFTSHIFT) is installed
    with mock.patch.object(store, "KEY_NAMES", {}):
      self.assertEqual("KEY_42", store.event_name(42))

  def test_inspect_input_source_filters_internal_bus(self):
    import os
    sysfs = f"{self.tmp.name}/sysfs"
    for event, modalias, name in (
      ("event5", "input:b0003v054cp1234e0110", "USB Gamepad"),
      ("event6", "input:b0019v0000p0000e0000", "Touchscreen"),
    ):
      device = os.path.join(sysfs, event, "device")
      os.makedirs(device)
      with open(os.path.join(device, "modalias"), "w") as f:
        f.write(modalias)
      with open(os.path.join(device, "name"), "w") as f:
        f.write(name)

    source = store.inspect_input_source("/dev/input/event5", sysfs)
    self.assertIsNotNone(source)
    self.assertEqual(0x0003, source.bus)
    self.assertEqual("USB Gamepad", source.name)
    self.assertTrue(source.device_id)

    self.assertIsNone(store.inspect_input_source("/dev/input/event6", sysfs))


class TestDaemonLearning(_TempDirTestCase):
  def _daemon(self, **param_values):
    self.clock = FakeClock()
    self.params = FakeParams(**param_values)
    return WheelControlsDaemon("/dev/input", "/sys/class/input",
                               config_path=self.config_path, control_path=self.control_path,
                               status_path=self.status_path, params=self.params, clock=self.clock,
                               publisher=FakePublisher(), apply_favorite=self.applier)

  def setUp(self):
    super().setUp()
    self.applier_calls = []
    self.applier = lambda slot: self.applier_calls.append(slot) or True

  def _start_learning(self, daemon, slot):
    store.write_control({"token": "t1", "learn_slot": slot + 1}, self.control_path)
    daemon._update_control(self.clock.now)
    daemon._update_learning(self.clock.now)

  def test_learning_captures_mapping_and_enables(self):
    daemon = self._daemon()
    self._start_learning(daemon, 3)
    self.assertEqual(3, daemon.learning_slot)

    daemon._handle_key(FakeSource.make(), 42)
    self.assertIsNone(daemon.learning_slot)
    config = store.read_config(self.config_path)
    self.assertTrue(config["enabled"])
    self.assertEqual([{"device_id": "abc123", "slot": 3, "event_code": 42}],
                     [{"device_id": m["device_id"], "slot": m["slot"], "event_code": m["event_code"]}
                      for m in config["mappings"]])
    self.assertEqual(3, daemon.last_learned["slot"])

  def test_learning_times_out(self):
    daemon = self._daemon()
    self._start_learning(daemon, 0)
    self.clock.advance(21.0)
    daemon._update_learning(self.clock.now)
    self.assertIsNone(daemon.learning_slot)
    self.assertEqual([], store.read_config(self.config_path)["mappings"])

  def test_going_onroad_cancels_learning(self):
    daemon = self._daemon(IsOffroad=False)
    store.write_control({"token": "t1", "learn_slot": 2}, self.control_path)
    daemon._update_control(self.clock.now)
    self.assertEqual(1, daemon.learning_slot)  # request accepted...
    daemon._update_learning(self.clock.now)
    self.assertIsNone(daemon.learning_slot)  # ...then cancelled by the offroad gate

  def test_control_token_consumed_once(self):
    daemon = self._daemon()
    store.write_control({"token": "t1", "learn_slot": 2}, self.control_path)
    daemon._update_control(self.clock.now)
    self.assertEqual(1, daemon.learning_slot)
    daemon._update_control(self.clock.now + 1)  # same token: ignored
    self.assertEqual(1, daemon.learning_slot)


class TestDaemonExecution(_TempDirTestCase):
  def setUp(self):
    super().setUp()
    self.clock = FakeClock()
    self.params = FakeParams()
    self.publisher = FakePublisher()
    self.applier_calls = []
    self.daemon = WheelControlsDaemon(
      "/dev/input", "/sys/class/input", config_path=self.config_path, control_path=self.control_path,
      status_path=self.status_path, params=self.params, clock=self.clock,
      publisher=self.publisher, apply_favorite=lambda slot: self.applier_calls.append(slot) or True)

  def _map(self, slot, key=None):
    action_slots = store.default_action_slots()
    if key is not None:
      action_slots[slot - store.FAVORITE_SLOT_COUNT] = {"enabled": True, "key": key, "label": "X"}
    store.write_config({
      "mappings": [{"device_id": "abc123", "device_name": "Pad", "event_code": 42, "slot": slot}],
      "action_slots": action_slots, "enabled": True, "joystick_device": "",
    }, self.config_path)

  def test_favorite_slot_delegates_to_applier(self):
    self._map(0)
    self.daemon._handle_key(FakeSource.make(), 42)
    self.assertEqual([0], self.applier_calls)

  def test_cruise_action_published_to_command_channel(self):
    self._map(3, "accelCruise")
    self.daemon._handle_key(FakeSource.make(), 42)
    self.assertEqual([(store.peer_address("abc123"), "accelCruise", 1000.0)], self.publisher.sent)

  def test_disabled_config_blocks_execution(self):
    self._map(3, "accelCruise")
    store.update_config({"enabled": False}, self.config_path)
    self.daemon._handle_key(FakeSource.make(), 42)
    self.assertEqual([], self.publisher.sent)
    self._map(0)
    store.update_config({"enabled": False}, self.config_path)
    self.daemon._handle_key(FakeSource.make(), 42)
    self.assertEqual([], self.applier_calls)

  def test_joystick_device_is_ignored(self):
    self._map(3, "accelCruise")
    store.update_config({"joystick_device": "abc123"}, self.config_path)
    self.daemon._handle_key(FakeSource.make(), 42)
    self.assertEqual([], self.publisher.sent)

  def test_unknown_mapping_key_ignored(self):
    self._map(4, None)  # disabled action slot
    self.daemon._handle_key(FakeSource.make(), 42)
    self.assertEqual([], self.publisher.sent)
    self.assertEqual([], self.applier_calls)

  def test_personality_action_dispatches(self):
    self._map(3, store.ACTION_CYCLE_PERSONALITY)
    with mock.patch.object(wheel_controlsd, "cycle_driving_personality", return_value=True) as cycle:
      self.daemon._handle_key(FakeSource.make(), 42)
    cycle.assert_called_once_with(self.daemon.params)

  def test_status_file_written(self):
    self.daemon._publish_status(self.clock.now)
    status = store.read_status(self.status_path)
    self.assertTrue(status["offroad"])
    self.assertEqual(1000.0, status["updated_at"])
    self.assertFalse(status["learning"])


class FakeMemoryParams:
  """Minimal stand-in for the tmpfs Params store the SetSpeed / screen-wake writes go to."""

  def __init__(self):
    self.values = {}

  def put_float(self, key, value):
    self.values[key] = float(value)

  def put_int(self, key, value):
    self.values[key] = int(value)


class TestSetSpeedAction(_TempDirTestCase):
  def test_engaged_onroad_metric_writes_mps(self):
    params = FakeParams(IsOnroad=True, IsEngaged=True, IsMetric=True)
    memory = FakeMemoryParams()
    self.assertTrue(wheel_controlsd.set_controller_cruise_speed(60, params, memory))
    from openpilot.common.constants import CV
    self.assertAlmostEqual(memory.values["SLCForceCruiseSpeed"], 60 * CV.KPH_TO_MS)

  def test_engaged_onroad_imperial_writes_mps(self):
    params = FakeParams(IsOnroad=True, IsEngaged=True, IsMetric=False)
    memory = FakeMemoryParams()
    self.assertTrue(wheel_controlsd.set_controller_cruise_speed(30, params, memory))
    from openpilot.common.constants import CV
    self.assertAlmostEqual(memory.values["SLCForceCruiseSpeed"], 30 * CV.MPH_TO_MS)

  def test_refused_when_not_engaged_or_offroad(self):
    memory = FakeMemoryParams()
    self.assertFalse(wheel_controlsd.set_controller_cruise_speed(60, FakeParams(IsOnroad=True, IsEngaged=False, IsMetric=True), memory))
    self.assertFalse(wheel_controlsd.set_controller_cruise_speed(60, FakeParams(IsOnroad=False, IsEngaged=True, IsMetric=True), memory))
    self.assertNotIn("SLCForceCruiseSpeed", memory.values)

  def test_refused_outside_unit_bounds_or_non_finite(self):
    params = FakeParams(IsOnroad=True, IsEngaged=True, IsMetric=True)
    memory = FakeMemoryParams()
    self.assertFalse(wheel_controlsd.set_controller_cruise_speed(7, params, memory))    # below 8 km/h
    self.assertFalse(wheel_controlsd.set_controller_cruise_speed(146, params, memory))  # above 145 km/h
    self.assertFalse(wheel_controlsd.set_controller_cruise_speed(float("nan"), params, memory))
    self.assertFalse(wheel_controlsd.set_controller_cruise_speed("abc", params, memory))
    self.assertNotIn("SLCForceCruiseSpeed", memory.values)

  def test_normalize_action_slots_set_speed_value(self):
    slots = store.normalize_action_slots([
      {"enabled": True, "key": "setSpeed", "label": "60", "value": 60},
      {"enabled": True, "key": "setSpeed", "label": "bad", "value": "abc"},
      {"enabled": True, "key": "setSpeed", "label": "neg", "value": -5},
    ])
    self.assertTrue(slots[0]["enabled"])
    self.assertEqual(60.0, slots[0]["value"])
    self.assertFalse(slots[1]["enabled"])  # unparseable value disables the slot
    self.assertFalse(slots[2]["enabled"])  # non-positive value disables the slot

  def test_daemon_set_speed_dispatch_passes_slot_value(self):
    action_slots = store.default_action_slots()
    action_slots[0] = {"enabled": True, "key": "setSpeed", "label": "60", "value": 60.0}
    store.write_config({
      "mappings": [{"device_id": "abc123", "device_name": "Pad", "event_code": 42, "slot": 3}],
      "action_slots": action_slots, "enabled": True, "joystick_device": "",
    }, self.config_path)
    params = FakeParams(IsOnroad=True, IsEngaged=True, IsMetric=True)
    memory = FakeMemoryParams()
    self.daemon = WheelControlsDaemon(config_path=self.config_path, control_path=self.control_path,
                                      status_path=self.status_path, params=params, params_memory=memory)
    self.daemon._handle_key(FakeSource.make(), 42)
    from openpilot.common.constants import CV
    self.assertAlmostEqual(memory.values["SLCForceCruiseSpeed"], 60 * CV.KPH_TO_MS)


class TestStandbyWakeBroadcast(_TempDirTestCase):
  def _daemon(self, params):
    return WheelControlsDaemon(config_path=self.config_path, control_path=self.control_path,
                               status_path=self.status_path, params=params, params_memory=FakeMemoryParams())

  def test_broadcast_writes_memory_param_when_gated_on(self):
    params = FakeParams(ScreenManagement=True, StandbyMode=True, StandbyWakeButton=True)
    daemon = self._daemon(params)
    daemon._publish_button_press(12345)
    self.assertEqual(12345, daemon.params_memory.values["StandbyButtonPressTime"])

  def test_broadcast_inert_until_screen_params_registered(self):
    daemon = self._daemon(FakeParams())  # default: no screen-management keys
    daemon._publish_button_press(12345)
    self.assertNotIn("StandbyButtonPressTime", daemon.params_memory.values)

  def test_broadcast_never_raises(self):
    class ExplodingParams(FakeParams):
      def get_bool(self, key):
        raise RuntimeError("params backend down")
    daemon = self._daemon(ExplodingParams())
    daemon._publish_button_press(12345)  # must not raise
    self.assertNotIn("StandbyButtonPressTime", daemon.params_memory.values)


if __name__ == "__main__":
  unittest.main()
