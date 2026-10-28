"""UI read of the YOLO traffic-light observer: bounded, permission-checked, stale-clearing.

The reader may only surface a record the producer stamped as comparison-only,
within a freshness window, and only when the observer's own opt-in file asks
for it. Anything missing, oversized, forged or stale must return None rather
than freeze a colour on screen.
"""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from openpilot.sunnypilot.carrot import signal_yolo_display as display


def _record(**overrides):
  record = {'version': 1, 'stream': 'road', 'size': [1344, 760], 'frame_id': 7,
            'timestamp': time.monotonic() - .1, 'session': 's', 'tracks': [],
            'mode': 'camera_comparison_only', 'model_sha256': 'x', 'prediction': 'red',
            'fresh': True, 'control_permission': False}
  record.update(overrides)
  return record


class TestUiObservation(unittest.TestCase):
  def test_fresh_record_is_returned(self):
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / 'obs.json'
      path.write_text(json.dumps(_record()))
      record = display.ui_observation(path=path)
      self.assertIsNotNone(record)
      self.assertEqual(record['prediction'], 'red')

  def test_control_permission_is_refused(self):
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / 'obs.json'
      path.write_text(json.dumps(_record(control_permission=True)))
      self.assertIsNone(display.ui_observation(path=path))

  def test_control_mode_is_refused(self):
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / 'obs.json'
      path.write_text(json.dumps(_record(mode='control')))
      self.assertIsNone(display.ui_observation(path=path))

  def test_stale_record_is_refused(self):
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / 'obs.json'
      path.write_text(json.dumps(_record(timestamp=time.monotonic() - 5.)))
      self.assertIsNone(display.ui_observation(path=path))

  def test_future_timestamp_is_refused(self):
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / 'obs.json'
      path.write_text(json.dumps(_record(timestamp=time.monotonic() + 1.)))
      self.assertIsNone(display.ui_observation(path=path))

  def test_oversized_file_is_refused(self):
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / 'obs.json'
      path.write_text('x' * (display.MAX_OBSERVATION_BYTES + 1))
      self.assertIsNone(display.ui_observation(path=path))

  def test_missing_or_corrupt_file_is_refused(self):
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / 'obs.json'
      self.assertIsNone(display.ui_observation(path=path))
      path.write_text('{not json')
      self.assertIsNone(display.ui_observation(path=path))

  def test_missing_required_field_is_refused(self):
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / 'obs.json'
      record = _record()
      del record['session']
      path.write_text(json.dumps(record))
      self.assertIsNone(display.ui_observation(path=path))


class TestObserverRequested(unittest.TestCase):
  def setUp(self):
    display._observer_requested_cache = (0., False)

  def tearDown(self):
    display._observer_requested_cache = (0., False)

  def test_absent_file_is_off(self):
    with tempfile.TemporaryDirectory() as directory:
      self.assertFalse(display.observer_requested(path=Path(directory) / 'enabled'))

  def test_enabled_file_is_on(self):
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / 'enabled'
      path.write_text('1')
      now = time.monotonic()
      self.assertTrue(display.observer_requested(now, path))
      path.write_text('0')
      self.assertFalse(display.observer_requested(now + .6, path))
      path.write_text('yes')
      self.assertFalse(display.observer_requested(now + 1.2, path))

  def test_result_is_cached_for_half_a_second(self):
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / 'enabled'
      path.write_text('1')
      now = time.monotonic()
      self.assertTrue(display.observer_requested(now, path))
      path.write_text('0')
      self.assertTrue(display.observer_requested(now + .1, path))
      self.assertFalse(display.observer_requested(now + .6, path))


class TestYoloObservationReader(unittest.TestCase):
  def setUp(self):
    display._observer_requested_cache = (0., False)

  def tearDown(self):
    display._observer_requested_cache = (0., False)

  def test_unrequested_observer_reads_nothing(self):
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / 'obs.json'
      path.write_text(json.dumps(_record()))
      # Point the opt-in flag into the temp dir: on a device where the real
      # observer is enabled, the unpatched flag would read 'on' and the test
      # would pass for the wrong reason (or fail outright).
      with mock.patch.object(display, 'ENABLE_PATH', Path(directory) / 'enabled'):
        reader = display.YoloObservationReader(path)
        self.assertIsNone(reader.read())

  def test_requested_reader_returns_the_record(self):
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / 'obs.json'
      path.write_text(json.dumps(_record()))
      with mock.patch.object(display, 'ENABLE_PATH', Path(directory) / 'enabled'):
        (Path(directory) / 'enabled').write_text('1')
        reader = display.YoloObservationReader(path)
        record = reader.read()
        self.assertIsNotNone(record)
        self.assertEqual(record['prediction'], 'red')

  def test_reads_are_throttled(self):
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / 'obs.json'
      path.write_text(json.dumps(_record(prediction='red')))
      with mock.patch.object(display, 'ENABLE_PATH', Path(directory) / 'enabled'):
        (Path(directory) / 'enabled').write_text('1')
        reader = display.YoloObservationReader(path)
        now = time.monotonic()
        self.assertEqual(reader.read(now)['prediction'], 'red')
        path.write_text(json.dumps(_record(prediction='green')))
        # Before the next throttle window the old record stands.
        self.assertEqual(reader.read(now + .1)['prediction'], 'red')
        self.assertEqual(reader.read(now + .3)['prediction'], 'green')


if __name__ == '__main__':
  unittest.main()
