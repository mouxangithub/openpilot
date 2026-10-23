"""A stale observation from before the current enable window must be rejected.

Enabling signal assist used to act on whatever tmpfs file the model happened to
have written last, including a frame produced before the switch was on. That
makes the first moment after enabling look like an active red light even
though no current frame supports it. The runtime now records the off->on
transition time and drops observations older than it.
"""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from openpilot.sunnypilot.carrot.signal_assist_runtime import SignalAssistRuntime, publish_observation


class _SM(dict):
  def __init__(self):
    super().__init__(carState=NS(canValid=True, gearShifter='drive'),
                     selfdriveState=NS(enabled=True), carControl=NS(longActive=True))
    names = ['carState', 'modelV2', 'radarState', 'selfdriveState', 'carControl']
    self.seen = dict.fromkeys(names, True)
    self.valid = dict.fromkeys(names, True)
    self.alive = dict.fromkeys(names, True)
    self.recv_time = dict.fromkeys(names, 1000.0)


def _write_observation(path, timestamp):
  record = {'version': 1, 'stream': 'road', 'size': [1344, 760],
            'frame_id': 1, 'timestamp': timestamp, 'session': 's', 'tracks': []}
  text = json.dumps(record)
  path.write_text(text)


class TestEnabledSinceGate(unittest.TestCase):
  def test_observation_written_while_enabled_is_accepted(self):
    with tempfile.TemporaryDirectory() as d:
      d = Path(d)
      flag, obs_path = d / 'enable', d / 'obs'
      flag.write_text('1')
      runtime = SignalAssistRuntime(flag, obs_path)
      # enable happens at 100.0 on the first mode check; a frame at 100.5 is fresh.
      _write_observation(obs_path, 100.5)
      obs, _ = runtime.read(_SM(), 100.6)
      self.assertIsNotNone(obs)

  def test_stale_observation_from_before_enable_is_rejected_then_fresh_accepted(self):
    with tempfile.TemporaryDirectory() as d:
      d = Path(d)
      flag, obs_path = d / 'enable', d / 'obs'
      # Start disabled.
      flag.write_text('0')
      runtime = SignalAssistRuntime(flag, obs_path)
      # Force the initial mode poll so enabled_since reflects the off state.
      runtime.read(_SM(), 0.0)
      # A stale frame left over from a previous session sits in tmpfs.
      _write_observation(obs_path, 50.0)
      # User enables at t=100.
      flag.write_text('1')
      obs, context = runtime.read(_SM(), 100.0)
      self.assertTrue(context['enabled'])
      self.assertIsNone(obs, "an observation older than enabled_since must be rejected")
      # Once the model writes a frame from the current window, it is accepted.
      _write_observation(obs_path, 100.2)
      obs, _ = runtime.read(_SM(), 100.3)
      self.assertIsNotNone(obs)
      self.assertEqual(obs['timestamp'], 100.2)

  def test_missing_timestamp_is_treated_as_stale(self):
    with tempfile.TemporaryDirectory() as d:
      d = Path(d)
      flag, obs_path = d / 'enable', d / 'obs'
      flag.write_text('0')
      runtime = SignalAssistRuntime(flag, obs_path)
      runtime.read(_SM(), 0.0)
      flag.write_text('1')
      # Record without a timestamp: -inf default must not satisfy >= enabled_since.
      obs_path.write_text(json.dumps({'version': 1, 'stream': 'road', 'size': [1344, 760], 'tracks': []}))
      obs, _ = runtime.read(_SM(), 100.0)
      self.assertIsNone(obs)


if __name__ == "__main__":
  unittest.main()
