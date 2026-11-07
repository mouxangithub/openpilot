"""Signal assistance mode selection and red-light start-guard safety paths.
The full moving-red observation/control pipeline stays off (SignalAssistMode=0);
these lock the pure decision state machine and the default-safe mode read."""
import unittest
from pathlib import Path
from unittest.mock import patch

from openpilot.sunnypilot.carrot.signal_mode import read_mode
from openpilot.sunnypilot.carrot.signal_start_guard import SignalStartGuard


class FakeParams:
  def __init__(self, value=None, raises=False):
    self._v, self._raises = value, raises

  def get_int(self, key):
    if self._raises:
      raise KeyError(key)
    if self._v is None:
      raise KeyError(key)
    return self._v


class TestReadMode(unittest.TestCase):
  def test_valid_modes(self):
    for v in (0, 1, 2):
      self.assertEqual(read_mode(FakeParams(v)), v)

  def test_out_of_range_defaults_off(self):
    self.assertEqual(read_mode(FakeParams(3)), 0)
    self.assertEqual(read_mode(FakeParams(-1)), 0)

  def test_missing_or_errored_key_defaults_off(self):
    # native UnknownKeyName right after a pull must never enable control
    self.assertEqual(read_mode(FakeParams(raises=True)), 0)
    self.assertEqual(read_mode(FakeParams(None)), 0)


class TestStartGuardSafety(unittest.TestCase):
  def setUp(self):
    self.g = SignalStartGuard()

  def test_disabled_never_holds(self):
    d = self.g.update(1.0, None, enabled=False, valid=True, drive=True,
                      gas=False, speed=0.0, departure=True)
    self.assertFalse(d.hold)
    self.assertEqual(d.reason, 'disabled')

  def test_not_in_drive_never_holds(self):
    d = self.g.update(1.0, None, enabled=True, valid=True, drive=False,
                      gas=False, speed=0.0, departure=True)
    self.assertFalse(d.hold)

  def test_driver_gas_releases_and_cools_down(self):
    d = self.g.update(1.0, None, enabled=True, valid=True, drive=True,
                      gas=True, speed=0.0, departure=True)
    self.assertFalse(d.hold)
    self.assertEqual(d.reason, 'driver_gas')
    # cooldown window right after throttle must not re-assert a hold
    d2 = self.g.update(2.0, None, enabled=True, valid=True, drive=True,
                       gas=False, speed=0.0, departure=True)
    self.assertEqual(d2.reason, 'driver_cooldown')

  def test_moving_entry_without_authorization_does_not_hold(self):
    d = self.g.update(1.0, None, enabled=True, valid=True, drive=True,
                      gas=False, speed=10.0, departure=True)
    self.assertFalse(d.hold)
    self.assertEqual(d.reason, 'moving_no_entry')

  def test_invalid_context_is_safe(self):
    d = self.g.update(1.0, None, enabled=True, valid=False, drive=True,
                      gas=False, speed=0.0, departure=True)
    self.assertFalse(d.hold)


class TestRequestedFollowsMode(unittest.TestCase):
  """The signal runtimes' enable flag follows SignalAssistMode for endpoints
  under the signal dir; the retired moving-red file stays off."""

  def _requested(self, name, mode):
    import openpilot.sunnypilot.carrot.signal_assist_runtime as sar
    with patch('openpilot.sunnypilot.carrot.signal_mode.signal_mode', lambda: mode):
      return sar.requested(Path('/data/signal-color-shadow') / name)

  def test_observation_endpoints_follow_mode(self):
    for name in ('enabled', 'tracking_enabled', 'display_enabled',
                 'start_guard_enabled', 'stop_prepare_enabled'):
      self.assertFalse(self._requested(name, 0))
      self.assertTrue(self._requested(name, 1))
      self.assertTrue(self._requested(name, 2))

  def test_retired_assist_file_never_enables(self):
    for mode in (0, 1, 2):
      self.assertFalse(self._requested('assist_enabled', mode))


if __name__ == "__main__":
  unittest.main()
