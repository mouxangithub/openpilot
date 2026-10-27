"""
Copyright (c) 2026-, sunnypilot and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

Lateral-only experimental mode (ST-11): StarPilot's stock-ACC allow-list wired into
selfdrived_zp. Non-whitelist cars must behave exactly as before; the whitelist only
opens Experimental Mode for stock-ACC cars that StarPilot explicitly allows.
"""
import sys
import types

# common.params → swaglog → common.hardware → gpio imports fcntl at module load. It is only
# *used* from hardware functions never called here, so on PC a bare module keeps the import
# chain alive. Must run before the imports below.
try:
  import fcntl  # noqa: F401
except ImportError:
  sys.modules.setdefault('fcntl', types.ModuleType('fcntl'))

# common.params loads libparams_c.so via ctypes at import time; no Windows build exists.
# The ZP only needs the Params *class symbol* for typing/defaults - tests inject FakeParams.
try:
  from openpilot.common.params import Params  # noqa: F401
except (OSError, FileNotFoundError):
  _params_mod = types.ModuleType('openpilot.common.params')

  class _ParamsStub:
    def __init__(self, *args, **kwargs):
      raise RuntimeError("real Params is unavailable on PC; inject a fake in tests")

  _params_mod.Params = _ParamsStub
  sys.modules['openpilot.common.params'] = _params_mod

# The PC msgq shim is Python-2 syntax (octal literals), so anything importing
# openpilot.cereal.messaging transitively must be stubbed, not imported.
_msgq = types.ModuleType('msgq')
for _n in ('fake_event_handle', 'drain_sock_raw', 'MultiplePublishersError', 'IpcError',
           'Context', 'Poller', 'SubSocket', 'PubSocket', 'SocketEventHandle',
           'toggle_fake_events', 'set_fake_prefix', 'get_fake_prefix',
           'delete_fake_prefix', 'wait_for_one_event'):
  setattr(_msgq, _n, type(_n, (Exception,), {}) if 'Error' in _n else (lambda *a, **k: None))
sys.modules['msgq'] = _msgq

_messaging = types.ModuleType('openpilot.cereal.messaging')
for _n in ('SubMaster', 'PubMaster', 'new_message', 'log_from_bytes', 'drain_sock_raw',
           'sub_sock', 'pub_sock'):
  setattr(_messaging, _n, lambda *a, **k: None)
sys.modules['openpilot.cereal.messaging'] = _messaging

from opendbc.car import structs
from opendbc.car.hyundai.values import CAR as HYUNDAI_CAR
from openpilot.cereal import custom
from openpilot.sunnypilot.selfdrive.car.tests.fakes import FakeParams
from openpilot.sunnypilot.selfdrive.selfdrived.selfdrived_zp import (
  LATERAL_ONLY_EXPERIMENTAL_CARS,
  SelfdrivedZP,
  lateral_only_experimental_available,
)

WHITELIST_FINGERPRINT = "HYUNDAI_PALISADE_2023"  # StarPilot CAR.HYUNDAI_PALISADE_2023


def make_zp(fingerprint: str, op_long: bool, **params):
  CP = structs.CarParams.new_message()
  CP.carFingerprint = fingerprint
  CP.openpilotLongitudinalControl = op_long
  return SelfdrivedZP(CP, FakeParams(**{"ExperimentalMode": True, **params}))


class TestAllowList:
  def test_matches_starpilot_verbatim(self):
    # StarPilot: {CAR.HYUNDAI_PALISADE_2023} - the 2023+ Palisade platform
    # (which also identifies Kia Telluride routes). One car, no more.
    assert LATERAL_ONLY_EXPERIMENTAL_CARS == frozenset({WHITELIST_FINGERPRINT})

  def test_whitelist_car_without_op_long_is_available(self):
    assert lateral_only_experimental_available(make_zp(WHITELIST_FINGERPRINT, op_long=False).CP)

  def test_whitelist_car_with_op_long_uses_the_normal_path(self):
    # the allow-list only opens stock-ACC cars; with op long the normal rule applies
    assert not lateral_only_experimental_available(make_zp(WHITELIST_FINGERPRINT, op_long=True).CP)

  def test_non_whitelist_stock_acc_car_is_never_available(self):
    # e.g. this repo's Toyota: stock ACC, not on the allow-list
    assert not lateral_only_experimental_available(make_zp("TOYOTA_RAV4_TSS2", op_long=False).CP)


class TestExperimentalModeGating:
  def test_op_long_car_unchanged(self):
    # with op long the mode follows the param exactly as before
    assert make_zp("TOYOTA_RAV4_TSS2", op_long=True).experimental_mode is True
    assert make_zp("TOYOTA_RAV4_TSS2", op_long=True, ExperimentalMode=False).experimental_mode is False

  def test_non_whitelist_stock_acc_car_stays_off(self):
    # the old behaviour: no op long means no experimental mode, param or not
    zp = make_zp("TOYOTA_RAV4_TSS2", op_long=False)
    assert zp.experimental_mode is False
    assert zp.experimental_mode_available is False

  def test_whitelist_stock_acc_car_honours_the_param(self):
    zp = make_zp(WHITELIST_FINGERPRINT, op_long=False)
    assert zp.experimental_mode is True
    assert make_zp(WHITELIST_FINGERPRINT, op_long=False, ExperimentalMode=False).experimental_mode is False


class _FakeEvents:
  def __init__(self):
    self.names = []

  def add(self, name):
    self.names.append(name)


class _FakeIcbm:
  def update_activation(self, CS_SP):
    pass


def run_update(zp, CS, CS_SP, events=None, events_sp=None, personality=1):
  return zp.update(CS, CS_SP, events or _FakeEvents(), events_sp or _FakeEvents(), _FakeIcbm(), personality)


def car_state(cruise_available=True):
  CS = structs.CarState.new_message()
  CS.cruiseState.available = cruise_available
  return CS


class TestUpdatePath:
  def test_whitelist_car_without_op_long_toggles_via_long_press(self):
    zp = make_zp(WHITELIST_FINGERPRINT, op_long=False, ExperimentalMode=False)
    CS = car_state()
    # no button events: the long-press path must simply not fire
    personality = run_update(zp, CS, custom.CarStateSP.new_message())
    assert personality == 1
    assert zp.experimental_mode is False

  def test_non_whitelist_stock_acc_car_skips_the_button_path(self):
    zp = make_zp("TOYOTA_RAV4_TSS2", op_long=False, ExperimentalMode=False)
    personality = run_update(zp, car_state(), custom.CarStateSP.new_message())
    assert personality == 1

  def test_op_long_car_personality_step_unchanged(self):
    # the farther button still steps the personality up on op-long cars
    zp = make_zp("TOYOTA_RAV4_TSS2", op_long=True, ExperimentalMode=False)
    CS_SP = custom.CarStateSP.new_message()
    CS_SP.zoompilot.distanceFarther = True  # pressed this frame
    events = _FakeEvents()
    run_update(zp, car_state(), CS_SP, events=events)
    # release next frame: the step happens on the release edge
    CS_SP2 = custom.CarStateSP.new_message()
    personality = run_update(zp, car_state(), CS_SP2, events=events)
    assert personality == 2
