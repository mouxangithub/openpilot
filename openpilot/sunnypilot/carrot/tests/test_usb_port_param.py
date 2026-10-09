"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of zoompilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

The 7000 API is the other place AdbEnabled / JetlinkLink can be written from, and
the native UI's USB-port pass does not run where there is no builtin display. A
write to either has to leave the two consistent, or AGNOS's ADB gadget (g1) keeps
the only device controller and jetlink reads as unavailable:

  Jetlink unavailable: USB gadget 'g1' already holds the device controller
  (a600000.dwc3); tear it down first
"""
import unittest
from unittest import mock

from openpilot.sunnypilot.carrot.server.services.params import _USB_PORT_KEYS, _enforce_usb_port


class _FakeParams:
  def __init__(self, adb=False):
    self.store = {"AdbEnabled": adb}

  def get_bool(self, key):
    return bool(self.store.get(key, False))

  def put_bool(self, key, value):
    self.store[key] = value


class _Status:
  def __init__(self, enabled):
    self.enabled = enabled


def _with_jetlink(status):
  """Patch jetlink_adapter.status for the duration of one call."""
  return mock.patch("openpilot.sunnypilot.jetlink_adapter.status", return_value=status)


class TestUsbPortKeys(unittest.TestCase):
  def test_both_keys_are_covered(self):
    # the link setting's name is jetlink's, so assert on it rather than a literal
    self.assertIn("AdbEnabled", _USB_PORT_KEYS)
    self.assertIn("JetlinkLink", _USB_PORT_KEYS)

  def test_the_link_on_turns_adb_off(self):
    p = _FakeParams(adb=True)
    with _with_jetlink(_Status(enabled=True)):
      _enforce_usb_port(p)
    self.assertFalse(p.get_bool("AdbEnabled"))

  def test_the_link_off_leaves_adb_alone(self):
    for enabled in (False,):
      p = _FakeParams(adb=True)
      with _with_jetlink(_Status(enabled=enabled)):
        _enforce_usb_port(p)
      self.assertTrue(p.get_bool("AdbEnabled"))

  def test_no_jetlink_status_leaves_adb_alone(self):
    # no jetlink on this device, or the adapter could not read one
    p = _FakeParams(adb=True)
    with _with_jetlink(None):
      _enforce_usb_port(p)
    self.assertTrue(p.get_bool("AdbEnabled"))

  def test_a_failing_adapter_is_swallowed(self):
    # a good write must not become a 400 because the port pass could not read
    p = _FakeParams(adb=True)
    with mock.patch("openpilot.sunnypilot.jetlink_adapter.status", side_effect=RuntimeError("boom")):
      _enforce_usb_port(p)
    self.assertTrue(p.get_bool("AdbEnabled"))


if __name__ == '__main__':
  unittest.main()
