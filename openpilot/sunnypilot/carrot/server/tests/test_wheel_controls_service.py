"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Tests for the wheel_controls web service layer. Store paths are redirected into a
tmp dir and the engaged reader is patched, so no Params and no real daemon is needed."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openpilot.sunnypilot.carrot.server.services import wheel_controls as service
from openpilot.sunnypilot.system.wheel_controls import store


class WheelControlsServiceTest(unittest.TestCase):
  def setUp(self):
    tmp = tempfile.TemporaryDirectory()
    self.addCleanup(tmp.cleanup)
    self.tmp = tmp.name
    patchers = [
      mock.patch.object(store, "default_config_path", lambda: f"{self.tmp}/wheel_controls.json"),
      mock.patch.object(store, "CONTROL_PATH", Path(f"{self.tmp}/control.json")),
      mock.patch.object(store, "STATUS_PATH", Path(f"{self.tmp}/status.json")),
    ]
    for patcher in patchers:
      patcher.start()
      self.addCleanup(patcher.stop)

  # ------------------------------- config --------------------------------------

  def test_update_config_roundtrip(self):
    config = service.update_config({"enabled": True, "joystick_device": "abc"})
    self.assertTrue(config["enabled"])
    self.assertEqual("abc", config["joystick_device"])
    self.assertEqual(config, service.get_config())

  def test_empty_config_forced_back_to_disabled(self):
    service.update_config({"enabled": True, "joystick_device": "abc"})
    config = service.update_config({"joystick_device": ""})
    self.assertFalse(config["enabled"])

  def test_action_slot_validates_key_and_index(self):
    config = service.set_action_slot(0, "accelCruise", "Resume")
    self.assertEqual("accelCruise", config["action_slots"][0]["key"])
    with self.assertRaises(service.WheelControlsError) as ctx:
      service.set_action_slot(0, "__nope__", "X")
    self.assertEqual("unknown_action", ctx.exception.code)
    with self.assertRaises(service.WheelControlsError) as ctx:
      service.set_action_slot(99, "cancel", "X")
    self.assertEqual("bad_slot", ctx.exception.code)
    # clearing a slot
    config = service.set_action_slot(0, None, "")
    self.assertFalse(config["action_slots"][0]["enabled"])

  def test_delete_mapping(self):
    service.update_config({"mappings": [{"device_id": "a", "event_code": 1, "slot": 0}]})
    mapping_id = service.get_config()["mappings"][0]["id"]
    config = service.delete_mapping(mapping_id)
    self.assertEqual([], config["mappings"])
    with self.assertRaises(service.WheelControlsError) as ctx:
      service.delete_mapping(mapping_id)
    self.assertEqual("not_found", ctx.exception.code)

  def test_clear_mappings_disables(self):
    service.update_config({"mappings": [{"device_id": "a", "event_code": 1, "slot": 0}], "enabled": True})
    config = service.clear_mappings()
    self.assertEqual([], config["mappings"])
    self.assertFalse(config["enabled"])

  # ------------------------------- engaged gate ---------------------------------

  def test_refuses_while_engaged(self):
    with mock.patch.object(service, "_engaged_reader", return_value=True):
      for call in (lambda: service.update_config({"enabled": True}),
                   service.clear_mappings,
                   lambda: service.start_learning(0),
                   service.cancel_learning,
                   lambda: service.set_testing(True)):
        with self.assertRaises(service.WheelControlsError) as ctx:
          call()
        self.assertEqual("engaged", ctx.exception.code)

  # ------------------------------- control requests -----------------------------

  def test_learn_request_writes_control_with_token(self):
    control = service.start_learning(4)
    self.assertEqual(5, control["learn_slot"])  # slot + 1, 1-based
    self.assertTrue(control["token"])
    self.assertEqual(control, store.read_control())

  def test_learn_request_rejects_bad_slot(self):
    for slot in (-1, store.MAPPING_SLOT_COUNT, "x", True):
      with self.assertRaises(service.WheelControlsError) as ctx:
        service.start_learning(slot)
      self.assertEqual("bad_slot", ctx.exception.code)

  def test_cancel_and_test_requests(self):
    control = service.cancel_learning()
    self.assertIsNone(control["learn_slot"])
    control = service.set_testing(True)
    self.assertTrue(control["test_active"])
    with self.assertRaises(service.WheelControlsError):
      service.set_testing("yes")

  # ------------------------------- status ---------------------------------------

  def test_public_status_merges_config_and_freshness(self):
    service.update_config({"enabled": True, "joystick_device": "abc"})
    fresh = {"updated_at": 999.0, "devices": [{"device_id": "abc", "name": "Pad"}]}
    with mock.patch.object(store, "read_status", return_value=fresh), \
         mock.patch.object(store, "connected_input_sources", return_value=[]):
      status = service.public_status(now=1000.0)
    self.assertTrue(status["available"])
    self.assertTrue(status["config"]["enabled"])
    self.assertTrue(status["devices"][0]["joystick_enabled"])

  def test_public_status_scans_devices_when_daemon_stale(self):
    source = store.InputSource("/dev/input/event5", "xyz", "Pad", 3, 1, 2)
    with mock.patch.object(store, "read_status", return_value={}), \
         mock.patch.object(store, "connected_input_sources", return_value=[source]):
      status = service.public_status(now=1000.0)
    self.assertFalse(status["available"])
    self.assertEqual([{**source.serialize(), "joystick_enabled": False}], status["devices"])


if __name__ == "__main__":
  unittest.main()
