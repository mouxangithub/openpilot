"""SignalShadowObserver: modeld tmpfs observations -> observation-only
shadow state. Stage 1 must never actuate; these tests pin that contract."""
import json
import tempfile
import unittest
from pathlib import Path

from openpilot.sunnypilot.carrot.signal_shadow import (
  SignalShadowObserver, SignalShadowState, _red_track_present,
)


def _write(path: Path, tracks):
  obj = {'version': 1, 'stream': 'road', 'size': [1344, 760], 'session': 's',
         'frame_id': 1, 'timestamp': 1.0, 'tracks': tracks}
  path.write_text(json.dumps(obj))


class TestRedDetection(unittest.TestCase):
  def test_raw_red_and_seen_red(self):
    self.assertTrue(_red_track_present({'tracks': [{'raw': 'red_lamp_core'}]}))
    self.assertTrue(_red_track_present({'tracks': [{'raw': 'green', 'seen_red': True}]}))

  def test_green_only_is_false(self):
    self.assertFalse(_red_track_present({'tracks': [{'raw': 'green'}]}))
    self.assertFalse(_red_track_present({'tracks': []}))
    self.assertFalse(_red_track_present(None))

  def test_unknown_payload_safe(self):
    self.assertFalse(_red_track_present({}))
    self.assertFalse(_red_track_present("not a dict"))


class TestShadowObserver(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    d = Path(self.tmp.name)
    self.prep, self.start = d / 'p.json', d / 's.json'
    self.obs = SignalShadowObserver(self.prep, self.start)

  def tearDown(self):
    self.tmp.cleanup()

  def _force_mode(self, mode):
    # bypass the Params read for deterministic tests
    self.obs.mode = mode
    self.obs._read_mode = lambda: mode

  def test_mode_zero_reads_nothing(self):
    _write(self.prep, [{'raw': 'red'}])
    self._force_mode(0)
    state = self.obs.update(now=10.0)
    self.assertIsInstance(state, SignalShadowState)
    self.assertEqual(state.mode, 0)
    self.assertFalse(state.prepare_seen)
    self.assertFalse(state.fresh)
    self.assertEqual(self.obs.prepare_count, 0)

  def test_shadow_mode_detects_but_never_actuates(self):
    _write(self.prep, [{'raw': 'red_lamp'}])
    _write(self.start, [{'raw': 'green'}])
    self._force_mode(1)
    state = self.obs.update(now=10.0)
    self.assertEqual(state.mode, 1)
    self.assertTrue(state.prepare_seen)
    self.assertFalse(state.start_seen)
    self.assertTrue(state.fresh)
    # the safety contract: even in shadow the actuation surface is off
    self.assertFalse(self.obs.control_enabled)

  def test_control_surface_is_off_in_all_current_modes(self):
    for m in (0, 1, 2):
      self._force_mode(m)
      self.assertFalse(self.obs.control_enabled, m)

  def test_missing_files_are_fresh_false(self):
    self._force_mode(1)
    state = self.obs.update(now=11.0)
    self.assertFalse(state.fresh)
    self.assertFalse(state.prepare_seen)


if __name__ == "__main__":
  unittest.main()
