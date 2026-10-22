"""Direct contract for the default-OFF moving-red preparation transport.

carrot_functions.py wraps SignalPrepareRuntime() in a bare
``try/except Exception: self._prepare_runtime = None`` — any construction or
transport failure is swallowed and the feature silently vanishes. These tests
are the only alarm for that path, so they must cover the constructor and the
observation writer, not just the happy path.
"""
import json
import sys
import types
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest

from openpilot.sunnypilot.carrot.signal_stop_prepare import PrepareDecision, SignalStopPrepare
from openpilot.sunnypilot.carrot.signal_stop_prepare_runtime import (
  ENABLE_PATH,
  SignalPrepareRuntime,
  publish_prepare_observation,
)

RECORD = {'session': 's', 'frame_id': 1, 'timestamp_eof': 1_000_000_000, 'tracks': []}


@pytest.fixture
def mode_zero():
  with patch('openpilot.sunnypilot.carrot.signal_mode.signal_mode', lambda: 0):
    yield


def test_runtime_constructs_cleanly(mode_zero):
  """The alarm test: carrot_functions swallows construction errors into None."""
  runtime = SignalPrepareRuntime()
  assert isinstance(runtime.prepare, SignalStopPrepare)
  assert runtime.enabled is False  # mode 0 is the shipped default
  assert runtime.mode is None and runtime.mode_since == float('-inf')
  assert runtime.extra is None and runtime.last_prepare_log is None


def test_construction_does_not_touch_the_device_flag_files(mode_zero):
  """Construction is constant-path only; /data must stay untouched."""
  runtime = SignalPrepareRuntime()
  assert runtime.enable_path == ENABLE_PATH
  assert not runtime.enable_path.exists()


def test_mode_zero_publishes_nothing(tmp_path, mode_zero):
  path = tmp_path / 'obs.json'
  publish_prepare_observation(RECORD, path=path)
  assert not path.exists()
  assert not path.with_suffix('.tmp').exists()


@pytest.mark.parametrize('mode', [1, 2], ids=['shadow', 'control'])
def test_active_modes_publish_atomically(tmp_path, mode):
  path = tmp_path / 'obs.json'
  with patch('openpilot.sunnypilot.carrot.signal_mode.signal_mode', lambda: mode):
    publish_prepare_observation(RECORD, path=path)
  data = json.loads(path.read_text())
  assert data['version'] == 1 and data['size'] == [1344, 760]
  assert data['frame_id'] == 1 and data['session'] == 's'
  assert data['timestamp'] == 1.0
  # the tmp hand-off file is gone: readers never observe a partial write
  assert not path.with_suffix('.tmp').exists()


def test_oversized_observation_is_rejected_without_touching_the_last_good_one(tmp_path):
  path = tmp_path / 'obs.json'
  with patch('openpilot.sunnypilot.carrot.signal_mode.signal_mode', lambda: 2):
    publish_prepare_observation(RECORD, path=path)
    good = path.read_text()

    huge = {**RECORD, 'tracks': [{'id': 'x' * 2000} for _ in range(20)]}
    with pytest.raises(ValueError, match='prepare observation too large'):
      publish_prepare_observation(huge, path=path)

  assert path.read_text() == good
  assert not path.with_suffix('.tmp').exists()


def test_nan_tracks_are_rejected_by_allow_nan_false(tmp_path):
  path = tmp_path / 'obs.json'
  with patch('openpilot.sunnypilot.carrot.signal_mode.signal_mode', lambda: 2):
    with pytest.raises(ValueError):
      publish_prepare_observation({**RECORD, 'tracks': [{'distance': float('nan')}]}, path=path)
  assert not path.exists()


def test_observation_is_capped_at_twenty_tracks(tmp_path):
  path = tmp_path / 'obs.json'
  tracks = [{'id': i} for i in range(40)]
  with patch('openpilot.sunnypilot.carrot.signal_mode.signal_mode', lambda: 1):
    publish_prepare_observation({**RECORD, 'tracks': tracks}, path=path)
  assert len(json.loads(path.read_text())['tracks']) == 20


def _cloudlog_calls(monkeypatch, calls):
  fake = types.ModuleType('openpilot.common.swaglog')
  fake.cloudlog = NS(event=lambda *args, **kw: calls.append(kw))
  monkeypatch.setitem(sys.modules, 'openpilot.common.swaglog', fake)


def test_record_prepare_is_silent_while_disabled_and_unlogged(monkeypatch, mode_zero):
  """Disabled + never logged: the early return must not touch swaglog."""
  calls = []
  _cloudlog_calls(monkeypatch, calls)
  SignalPrepareRuntime().record_prepare(PrepareDecision())
  assert calls == []


def test_record_prepare_logs_each_distinct_decision_once(monkeypatch):
  calls = []
  _cloudlog_calls(monkeypatch, calls)
  with patch('openpilot.sunnypilot.carrot.signal_mode.signal_mode', lambda: 2):
    runtime = SignalPrepareRuntime()
  assert runtime.enabled is True
  runtime.mode = 2  # read() records the active mode; record_prepare trusts it

  decision = PrepareDecision(active=True, reason='housing', track_id=7)
  runtime.record_prepare(decision)
  runtime.record_prepare(decision)  # identical: deduplicated
  assert len(calls) == 1
  assert calls[0]['reason'] == 'housing'
  assert calls[0]['control_active'] is True  # active and mode == 2

  runtime.record_prepare(PrepareDecision(active=True, reason='housing', track_id=8))
  assert len(calls) == 2


def test_record_prepare_control_active_requires_control_mode(monkeypatch):
  calls = []
  _cloudlog_calls(monkeypatch, calls)
  with patch('openpilot.sunnypilot.carrot.signal_mode.signal_mode', lambda: 1):
    runtime = SignalPrepareRuntime()
  runtime.mode = 1
  runtime.record_prepare(PrepareDecision(active=True, reason='housing'))
  assert calls[0]['control_active'] is False  # shadow mode never claims control
