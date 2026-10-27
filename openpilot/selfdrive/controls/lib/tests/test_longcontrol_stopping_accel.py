"""Unit tests for the CP-4 user-tunable stopping deceleration (StoppingAccel).

Covers the clamp/fallback pure function and the 1 Hz param refresh wiring on
LongControl, including default equivalence (unset param == stock CP.stopAccel).
"""
import math
import sys
import types
from types import SimpleNamespace
import unittest

# PC stubs (see test_conditional_experimental_mode.py): fcntl only *used* by
# hardware functions we never call; common.params loads libparams_c via ctypes
# and has no Windows build. LongControl reads Params lazily, so a stub class is
# enough and tests inject their own fake params objects.
try:
  import fcntl  # noqa: F401
except ImportError:
  sys.modules.setdefault('fcntl', types.ModuleType('fcntl'))
try:
  from openpilot.common.params import Params  # noqa: F401
except (OSError, FileNotFoundError):
  _params_mod = types.ModuleType('openpilot.common.params')

  class _ParamsStub:
    def __init__(self, *args, **kwargs):
      raise RuntimeError("real Params is unavailable on PC; inject a fake in tests")

  _params_mod.Params = _ParamsStub
  sys.modules['openpilot.common.params'] = _params_mod

import openpilot.selfdrive.controls.lib.longcontrol as longcontrol_module
from openpilot.selfdrive.controls.lib.longcontrol import (
  STOPPING_ACCEL_MAX,
  STOPPING_ACCEL_MIN,
  STOPPING_ACCEL_PARAM_KEY,
  LongCtrlState,
  LongControl,
  clamp_stopping_accel,
)


class DictParams:
  """Dict-backed params with the get/get_float/get_bool surface LongControl uses."""

  def __init__(self, values=None):
    self.values = dict(values or {})

  def get(self, key, **kwargs):
    if key not in self.values:
      raise KeyError(key)
    return self.values[key]

  def get_float(self, key, default=0.0):
    if key not in self.values:
      return default
    try:
      return float(self.values[key])
    except (TypeError, ValueError):
      return default

  def get_bool(self, key):
    return bool(self.values.get(key, False))


def make_cp(stop_accel=-0.6):
  return SimpleNamespace(
    stopAccel=stop_accel,
    enableGasInterceptor=False,
    longitudinalTuning=SimpleNamespace(kiBP=[0.0, 1.0], kiV=[0.1, 0.2]),
  )


def make_long_control(stop_accel=-0.6, params=None):
  lc = LongControl(make_cp(stop_accel), SimpleNamespace(enableGasInterceptor=False))
  lc._params = params
  return lc


class TestClampStoppingAccel(unittest.TestCase):
  def test_default(self):
    self.assertEqual(clamp_stopping_accel(None, -0.6), -0.6)

  def test_in_range_passthrough(self):
    self.assertEqual(clamp_stopping_accel(-1.5, -0.6), -1.5)
    self.assertEqual(clamp_stopping_accel(STOPPING_ACCEL_MIN, -0.6), STOPPING_ACCEL_MIN)
    self.assertEqual(clamp_stopping_accel(STOPPING_ACCEL_MAX, -0.6), STOPPING_ACCEL_MAX)

  def test_out_of_range_falls_back_to_default(self):
    # 越界回默认: out-of-bounds falls back to default, not to the nearest bound.
    self.assertEqual(clamp_stopping_accel(-5.0, -0.6), -0.6)
    self.assertEqual(clamp_stopping_accel(-0.1, -0.6), -0.6)
    self.assertEqual(clamp_stopping_accel(0.0, -0.6), -0.6)
    self.assertEqual(clamp_stopping_accel(1.0, -0.6), -0.6)

  def test_unparseable_falls_back_to_default(self):
    self.assertEqual(clamp_stopping_accel("abc", -0.6), -0.6)
    self.assertEqual(clamp_stopping_accel(b"", -0.6), -0.6)

  def test_non_finite_falls_back_to_default(self):
    self.assertEqual(clamp_stopping_accel(float("nan"), -0.6), -0.6)
    self.assertEqual(clamp_stopping_accel(float("inf"), -0.6), -0.6)


class TestStoppingAccelRefresh(unittest.TestCase):
  def test_default_unset_param_is_stock_stop_accel(self):
    # Default equivalence: no param value -> stopping_accel == CP.stopAccel.
    lc = make_long_control(stop_accel=-0.55, params=DictParams({}))
    lc._stopping_accel_frame = 99  # next refresh tick is the 100th frame
    lc._refresh_stopping_accel()
    self.assertEqual(lc.stopping_accel, -0.55)

  def test_refresh_reads_param(self):
    lc = make_long_control(stop_accel=-0.55, params=DictParams({STOPPING_ACCEL_PARAM_KEY: -2.0}))
    lc._stopping_accel_frame = 99
    lc._refresh_stopping_accel()
    self.assertEqual(lc.stopping_accel, -2.0)

  def test_refresh_rejects_out_of_range(self):
    lc = make_long_control(stop_accel=-0.55, params=DictParams({STOPPING_ACCEL_PARAM_KEY: -9.9}))
    lc._stopping_accel_frame = 99
    lc._refresh_stopping_accel()
    self.assertEqual(lc.stopping_accel, -0.55)

  def test_refresh_handles_raising_params(self):
    class RaisingParams:
      def get_float(self, key, default=0.0):
        raise KeyError(key)

    lc = make_long_control(stop_accel=-0.55, params=RaisingParams())
    lc._stopping_accel_frame = 99
    lc._refresh_stopping_accel()
    self.assertEqual(lc.stopping_accel, -0.55)

  def test_refresh_is_rate_limited(self):
    lc = make_long_control(stop_accel=-0.55, params=DictParams({STOPPING_ACCEL_PARAM_KEY: -2.0}))
    lc._refresh_stopping_accel()  # frame 1: no read yet
    self.assertEqual(lc.stopping_accel, -0.55)
    lc._stopping_accel_frame = 99
    lc._refresh_stopping_accel()  # frame 100: read applies
    self.assertEqual(lc.stopping_accel, -2.0)


class TestStoppingBehaviorIntegration(unittest.TestCase):
  @staticmethod
  def fake_cs(v_ego=0.0, a_ego=0.0):
    return SimpleNamespace(
      vEgo=v_ego, aEgo=a_ego, brakePressed=False, cruiseState=SimpleNamespace(standstill=True),
    )

  def run_stopping_frames(self, lc, n, cs):
    out = None
    for _ in range(n):
      out = lc.update(True, cs, a_target=lc.stopping_accel - 0.5, should_stop=True,
                      accel_limits=(-4.0, 2.0))
    return out

  def test_default_ramp_matches_stock_stop_accel(self):
    lc = make_long_control(stop_accel=-0.6, params=DictParams({}))
    lc._stopping_accel_frame = 99
    lc._refresh_stopping_accel()
    # vEgo >= 1.5 keeps stopping_decel_rate at the full 0.3 m/s^2/s.
    cs = self.fake_cs(v_ego=1.5)
    # Ramp down (0.003/frame) until the hold accel, then hold at the default.
    out = self.run_stopping_frames(lc, 250, cs)
    self.assertEqual(lc.long_control_state, LongCtrlState.stopping)
    # Holds at the first frame-level at/below the hold accel (one step wide).
    self.assertAlmostEqual(out, -0.6, delta=0.004)

  def test_param_extends_ramp(self):
    lc = make_long_control(stop_accel=-0.6, params=DictParams({STOPPING_ACCEL_PARAM_KEY: -2.0}))
    lc._stopping_accel_frame = 99
    lc._refresh_stopping_accel()
    cs = self.fake_cs(v_ego=1.5)
    out = self.run_stopping_frames(lc, 750, cs)
    self.assertAlmostEqual(out, -2.0, delta=0.004)
    self.assertTrue(math.isfinite(out))


if __name__ == "__main__":
  unittest.main()
