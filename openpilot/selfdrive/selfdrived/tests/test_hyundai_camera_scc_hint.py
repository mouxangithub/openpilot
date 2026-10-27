"""
Copyright (c) 2026-, sunnypilot and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

CP-3: cp's Hyundai camera-SCC hint ported onto canError's PERMANENT alert.
Only Hyundai cars without the CAMERA_SCC flag, with the HyundaiCameraSCC toggle
off and the HyundaiCameraSccHint param (default off) on, get the hint; every
other car keeps the plain CAN error text.
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
# The alert callback needs a *working* Params (it reads HyundaiCameraSCC/Hint), so the stub
# is dict-backed instead of raising. can_error_alert constructs Params() itself.
try:
  from openpilot.common.params import Params  # noqa: F401
except (OSError, FileNotFoundError):
  _PARAM_STORE: dict = {}
  _params_mod = types.ModuleType('openpilot.common.params')

  class _FakeParams:
    def __init__(self, *args, **kwargs):
      pass

    def get_int(self, key, **kwargs):
      return int(_PARAM_STORE.get(key, 0) or 0)

    def get_bool(self, key, **kwargs):
      return bool(_PARAM_STORE.get(key, False))

  _params_mod.Params = _FakeParams
  _params_mod._PARAM_STORE = _PARAM_STORE
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

from opendbc.car.hyundai.values import HyundaiFlags
from openpilot.cereal import log
from openpilot.selfdrive.selfdrived.events import EVENTS, can_error_alert

PLAIN_TEXT_1 = "CAN总线错误：请检查连接"
HINT_TEXT_1 = "CAN错误：请开启 CameraSCC"

_HYUNDAI_FLAGS_WITHOUT_CAMERA_SCC = 0


def alert(brand: str, flags: int = _HYUNDAI_FLAGS_WITHOUT_CAMERA_SCC):
  CP = type('CP', (), {'brand': brand, 'flags': flags})()
  return can_error_alert(CP, None, None, False, 0, None)


def set_params(**values):
  # the dict backing the PC Params stub above; on-device tests write real params instead
  store = sys.modules['openpilot.common.params']._PARAM_STORE if hasattr(sys.modules['openpilot.common.params'], '_PARAM_STORE') else None
  if store is None:
    return  # real Params available: nothing to fake
  store.clear()
  store.update(values)


class TestCanErrorAlert:
  def test_can_error_event_uses_the_callback(self):
    # the port replaces the static PERMANENT alert with the hint-aware callback
    entry = EVENTS[log.OnroadEvent.EventName.canError]
    assert entry['permanent'] is can_error_alert

  def test_non_hyundai_keeps_the_plain_text(self):
    # this repo's Toyota must be untouched, hint param or not
    set_params(HyundaiCameraSccHint=True)
    assert alert("toyota").alert_text_1 == PLAIN_TEXT_1

  def test_default_is_the_plain_text(self):
    # HyundaiCameraSccHint defaults to off: nothing changes for anyone
    set_params()
    assert alert("hyundai").alert_text_1 == PLAIN_TEXT_1

  def test_hint_needs_the_param(self):
    set_params(HyundaiCameraSCC=0, HyundaiCameraSccHint=False)
    assert alert("hyundai").alert_text_1 == PLAIN_TEXT_1

  def test_hint_fires_for_flagless_hyundai(self):
    set_params(HyundaiCameraSCC=0, HyundaiCameraSccHint=True)
    hint = alert("hyundai")
    assert hint.alert_text_1 == HINT_TEXT_1
    assert hint.alert_text_2 == "摄像头总线检测到 SCC"

  def test_camera_scc_flag_suppresses_the_hint(self):
    set_params(HyundaiCameraSCC=0, HyundaiCameraSccHint=True)
    assert alert("hyundai", int(HyundaiFlags.CAMERA_SCC)).alert_text_1 == PLAIN_TEXT_1

  def test_hyundai_camera_scc_toggle_on_suppresses_the_hint(self):
    set_params(HyundaiCameraSCC=1, HyundaiCameraSccHint=True)
    assert alert("hyundai").alert_text_1 == PLAIN_TEXT_1
