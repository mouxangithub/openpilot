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


  def test_identical_bytes_decoded_once(self):
    class SM(dict):
      def __init__(self):
        super().__init__(carState=NS(canValid=True, gearShifter='drive'), selfdriveState=NS(enabled=True),
                         carControl=NS(longActive=True))
        names = ['carState', 'modelV2', 'radarState', 'carControl']
        self.seen = dict.fromkeys(names, True)
        self.valid = dict.fromkeys(names, True)
        self.alive = dict.fromkeys(names, True)
        self.recv_time = dict.fromkeys(names, 10.)

    with tempfile.TemporaryDirectory() as d:
      d = Path(d)
      flag, path = d / 'enable', d / 'obs'
      flag.write_text('1')
      runtime = SignalAssistRuntime(flag, path)
      publish_observation({'tracks': []}, 1, 10., 'worker', path)
      obs1, _ = runtime.read(SM(), 10.1)
      self.assertIsNotNone(obs1)
      self.assertEqual(runtime._observation_bytes, path.read_bytes())
      # Same file content again: the cached object is reused, not re-parsed.
      # The patch stays up for both reads so the re-decode after new bytes is
      # also counted through the same spy.
      parsed_calls = []
      original_loads = json.loads
      json.loads = lambda *a, **k: (parsed_calls.append(1), original_loads(*a, **k))[1]
      try:
        obs2, _ = runtime.read(SM(), 10.2)
        self.assertEqual(parsed_calls, [])
        self.assertEqual(obs2, obs1)
        # Changed bytes re-decode exactly once.
        publish_observation({'tracks': []}, 2, 10.15, 'worker', path)
        obs3, _ = runtime.read(SM(), 10.3)
        self.assertIsNotNone(obs3)
        self.assertEqual(parsed_calls, [1])
      finally:
        json.loads = original_loads

  def test_disabled_cache_cannot_leak_across_disable(self):
    class SM(dict):
      def __init__(self):
        super().__init__(carState=NS(canValid=True, gearShifter='drive'), selfdriveState=NS(enabled=True),
                         carControl=NS(longActive=True))
        names = ['carState', 'modelV2', 'radarState', 'carControl']
        self.seen = dict.fromkeys(names, True)
        self.valid = dict.fromkeys(names, True)
        self.alive = dict.fromkeys(names, True)
        self.recv_time = dict.fromkeys(names, 10.)

    with tempfile.TemporaryDirectory() as d:
      d = Path(d)
      flag, path = d / 'enable', d / 'obs'
      flag.write_text('1')
      runtime = SignalAssistRuntime(flag, path)
      publish_observation({'tracks': []}, 1, 10., 'worker', path)
      obs, _ = runtime.read(SM(), 10.1)
      self.assertIsNotNone(obs)
      # Disable: nothing is read and no cached payload is served.
      flag.write_text('0')
      obs2, context = runtime.read(SM(), 10.7)
      self.assertIsNone(obs2)
      self.assertFalse(context['enabled'])


if __name__ == "__main__":
  unittest.main()
