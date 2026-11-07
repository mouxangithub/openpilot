"""
Copyright (c) 2026-, sunnypilot and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

Speed limit change announcement (ST-6a): the sustained-jump detector and the
event's alert mapping. All inputs are plain numbers; no messaging is needed
for the tracker itself.
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
# Only the Params class symbol is needed for typing here - the tracker takes raw floats.
try:
  from openpilot.common.params import Params  # noqa: F401
except (OSError, FileNotFoundError):
  _params_mod = types.ModuleType('openpilot.common.params')

  class _ParamsStub:
    def __init__(self, *args, **kwargs):
      raise RuntimeError("real Params is unavailable on PC")

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

from openpilot.common.constants import CV
from openpilot.cereal import custom
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.speed_limit_resolver import (
  SPEED_LIMIT_CHANGED_ALERT_HOLD_S,
  SPEED_LIMIT_CHANGED_ALERT_MIN_DELTA_KPH,
  SPEED_LIMIT_CHANGED_ALERT_STABLE_KPH,
  SpeedLimitChangedAlertTracker,
)
from openpilot.sunnypilot.selfdrive.selfdrived.events import EVENTS_SP
from openpilot.sunnypilot.selfdrive.selfdrived.events_base import ET, AlertSize, AudibleAlert

EventNameSP = custom.OnroadEventSP.EventName
DT_CTRL = 0.01
HOLD_FRAMES = int(SPEED_LIMIT_CHANGED_ALERT_HOLD_S / DT_CTRL)


def kph(v):
  return v * CV.KPH_TO_MS


def hold(tracker, limit_kph, frames=HOLD_FRAMES + 2):
  """Feed one stable limit for `frames`; return True if the alert fired at any point.

  Two spare frames: the first update only arms the candidate, so a jump that should
  announce needs the hold time plus one frame of margin."""
  return any(tracker.update(kph(limit_kph), DT_CTRL) for _ in range(frames))


class TestSpeedLimitChangedAlertTracker:
  def test_debounce_constants(self):
    # the reported spec: a jump of >= 5 kph holding > 2 s
    assert SPEED_LIMIT_CHANGED_ALERT_MIN_DELTA_KPH == 5.0
    assert SPEED_LIMIT_CHANGED_ALERT_HOLD_S == 2.0
    assert 0.0 < SPEED_LIMIT_CHANGED_ALERT_STABLE_KPH < SPEED_LIMIT_CHANGED_ALERT_MIN_DELTA_KPH

  def test_first_limit_never_alerts(self):
    tracker = SpeedLimitChangedAlertTracker()
    assert not hold(tracker, 50)

  def test_jump_fires_exactly_once_after_the_hold(self):
    tracker = SpeedLimitChangedAlertTracker()
    assert not hold(tracker, 50)
    # not yet: the hold timer is still running
    assert not any(tracker.update(kph(56), DT_CTRL) for _ in range(HOLD_FRAMES - 2))
    # hold time reached: exactly one alert
    fired = [tracker.update(kph(56), DT_CTRL) for _ in range(4)]
    assert fired.count(True) == 1
    # and the new value becomes the baseline: no repeat
    assert not hold(tracker, 56, HOLD_FRAMES)

  def test_jump_that_snaps_back_within_the_hold_never_fires(self):
    tracker = SpeedLimitChangedAlertTracker()
    assert not hold(tracker, 50)
    for _ in range(HOLD_FRAMES - 5):
      assert not tracker.update(kph(58), DT_CTRL)
    assert not hold(tracker, 50, HOLD_FRAMES)  # back inside the threshold: re-armed, no alert

  def test_still_moving_value_resets_the_timer(self):
    tracker = SpeedLimitChangedAlertTracker()
    assert not hold(tracker, 50)
    # wobble wider than the stability tolerance: the hold timer keeps restarting
    for step in range(HOLD_FRAMES + 5):
      limit = 57 if step % 2 == 0 else 60
      assert not tracker.update(kph(limit), DT_CTRL)

  def test_creep_below_the_threshold_never_alerts(self):
    tracker = SpeedLimitChangedAlertTracker()
    assert not hold(tracker, 50)
    for step in range(20):
      assert not tracker.update(kph(50 + step), DT_CTRL)  # 1 kph at a time: no jump

  def test_boundary_exactly_five_kph_counts(self):
    tracker = SpeedLimitChangedAlertTracker()
    assert not hold(tracker, 50)
    assert hold(tracker, 55)

  def test_invalid_limit_resets_everything(self):
    tracker = SpeedLimitChangedAlertTracker()
    assert not hold(tracker, 50)
    for _ in range(HOLD_FRAMES - 5):
      tracker.update(kph(58), DT_CTRL)
    assert not hold(tracker, 0, HOLD_FRAMES)  # limit drops out
    # the re-appearing limit is a fresh baseline, not a change
    assert not any(tracker.update(kph(58), DT_CTRL) for _ in range(HOLD_FRAMES))
    # ... but a jump from it still announces
    assert hold(tracker, 70)

  def test_downward_jump_announces_too(self):
    tracker = SpeedLimitChangedAlertTracker()
    assert not hold(tracker, 80)
    assert hold(tracker, 70)

  def test_reset_clears_state(self):
    tracker = SpeedLimitChangedAlertTracker()
    assert not hold(tracker, 50)
    for _ in range(HOLD_FRAMES - 5):
      tracker.update(kph(58), DT_CTRL)
    tracker.reset()
    assert not any(tracker.update(kph(58), DT_CTRL) for _ in range(HOLD_FRAMES))


class TestEventWiring:
  def test_event_is_mapped_as_a_standing_alert(self):
    # StarPilot's shape: a PERMANENT alert that shows and chimes while the
    # change stands, opt-in via the SpeedLimitChangedAlert param
    entry = EVENTS_SP[EventNameSP.speedLimitChangedAlert]
    assert ET.PERMANENT in entry

  def test_alert_is_visible_and_audible(self):
    entry = EVENTS_SP[EventNameSP.speedLimitChangedAlert]
    alert = entry[ET.PERMANENT](None, None, None, False, 0, None)
    assert alert.alert_text_1 == "限速已变化"
    assert alert.alert_size != AlertSize.none  # visible: the alert occupies the screen
    assert alert.audible_alert != AudibleAlert.none  # audible: a chime plays
    assert alert.duration == int(3.0 / DT_CTRL)  # 3 s standing window, same as StarPilot
