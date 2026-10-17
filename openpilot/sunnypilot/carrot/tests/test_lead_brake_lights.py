"""Lead brake-lamp observation port (navipilot d34224b49).

Display/log only. These lock the detector's confirmation discipline, the
runtime's lazy/cheap-when-off behavior and the params-only registration.
"""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from openpilot.sunnypilot.carrot import lead_brake_lights as runtime
from tools.signal_analysis.lead_brake_detector import LeadBrakeDetector


def context():
  lead = {'status': True, 'radar': True, 'radarTrackId': 3, 'dRel': 8., 'yRel': 0.}
  vision = {'prob': .99, 'x': [9.52], 'y': [0.]}
  car = {'yawRate': 0., 'steeringAngleDeg': 0., 'vEgo': 0.}
  calibration = {'calStatus': 'calibrated', 'height': [1.286], 'rpyCalib': [0., 0., 0.]}
  return lead, vision, car, calibration


def lamp_image():
  rgb = np.zeros((760, 1344, 3), np.uint8)
  rgb[342:348, 660:684, 0] = 255
  return rgb


class TestLeadBrakeDetector(unittest.TestCase):
  def test_confirmation_and_missing_lamp_is_unknown_not_off(self):
    detector = LeadBrakeDetector()
    for t in [1., 1.1]:
      self.assertEqual(detector.process(lamp_image(), t, *context())['state'], 'unknown')
    self.assertEqual(detector.process(lamp_image(), 1.2, *context())['state'], 'candidate')
    self.assertEqual(detector.process(np.zeros((760, 1344, 3), np.uint8), 1.25, *context())['state'], 'unknown')

  def test_rejects_unreliable_context(self):
    for kind in ('turn', 'vision', 'lead', 'calibration', 'nan'):
      with self.subTest(kind=kind):
        lead, vision, car, calibration = context()
        if kind == 'turn':
          car['yawRate'] = .2
        if kind == 'vision':
          vision['y'] = [2.]
        if kind == 'lead':
          lead['status'] = False
        if kind == 'calibration':
          calibration['calStatus'] = 'uncalibrated'
        if kind == 'nan':
          lead['dRel'] = float('nan')
        detector = LeadBrakeDetector()
        for t in [1., 1.1, 1.2]:
          self.assertEqual(detector.process(lamp_image(), t, lead, vision, car, calibration)['state'], 'unknown')

  def test_neighbor_and_low_tail_lamps_do_not_confirm(self):
    rgb = np.zeros((760, 1344, 3), np.uint8)
    rgb[342:348, 900:924, 0] = 255
    rgb[410:416, 660:684, 0] = 255
    detector = LeadBrakeDetector()
    for t in [1., 1.1, 1.2]:
      self.assertEqual(detector.process(rgb, t, *context())['state'], 'unknown')

  def test_repeated_frame_and_replacement_lead_do_not_inherit_confirmation(self):
    detector = LeadBrakeDetector()
    for _ in range(10):
      self.assertEqual(detector.process(lamp_image(), 1., *context())['state'], 'unknown')
    for t in [1.1, 1.2]:
      detector.process(lamp_image(), t, *context())
    lead, *rest = context()
    lead['radarTrackId'] = 4
    self.assertEqual(detector.process(lamp_image(), 1.3, lead, *rest)['state'], 'unknown')

  def test_long_gap_requires_new_confirmation(self):
    detector = LeadBrakeDetector()
    for t in [1., 1.1, 1.2]:
      detector.process(lamp_image(), t, *context())
    self.assertEqual(detector.process(lamp_image(), 1.6, *context())['state'], 'unknown')


class TestRequestedAndRuntime(unittest.TestCase):
  def setUp(self):
    self._saved = (runtime._params, runtime._enabled, runtime._next_read)

  def tearDown(self):
    runtime._params, runtime._enabled, runtime._next_read = self._saved

  def test_mode_zero_does_not_read_brake_parameter(self):
    from openpilot.sunnypilot.carrot import signal_mode
    original = signal_mode.signal_mode
    signal_mode.signal_mode = lambda: 0
    try:
      runtime._params = SimpleNamespace(get_bool=lambda key: 1 / 0)  # any read is a failure
      self.assertFalse(runtime.requested())
    finally:
      signal_mode.signal_mode = original

  def test_off_runtime_does_not_create_subscriber_or_write(self):
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / 'result.json'
      original_path = runtime.PATH
      runtime.PATH = path
      original_requested = runtime.requested
      runtime.requested = lambda: False
      try:
        worker = runtime.BrakeRuntime()
        worker.update(None, 1, 1., 's', 1.)
        self.assertIsNone(worker.sm)
        self.assertIsNone(worker.detector)
        self.assertEqual(list(tmp and Path(tmp).iterdir()), [])
      finally:
        runtime.PATH = original_path
        runtime.requested = original_requested

  def test_busy_signal_skips_detector_and_publishes_unknown(self):
    class _FakeTime:
      @staticmethod
      def monotonic():
        return 2.
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / 'result.json'
      original_path, original_requested, original_time = runtime.PATH, runtime.requested, runtime.time
      runtime.PATH, runtime.requested, runtime.time = path, (lambda: True), _FakeTime
      try:
        worker = runtime.BrakeRuntime()
        worker.update(None, 3, 1.99, 's', 1.9)
        result = json.loads(path.read_text())
        self.assertIsNone(worker.sm)
        self.assertEqual(result['state'], 'unknown')
        self.assertEqual(result['reason'], 'signal_budget')
        self.assertFalse(result['control_permission'])
      finally:
        runtime.PATH, runtime.requested, runtime.time = original_path, original_requested, original_time


class TestDisplayAndUi(unittest.TestCase):
  def test_display_stale_and_wrong_camera_never_holds_candidate(self):
    record = {'version': 1, 'frame_id': 20, 'timestamp': 1., 'control_permission': False,
              'state': 'candidate', 'box': [600, 340, 640, 350]}
    self.assertIs(runtime.display_result(record, 1.1, (20, 1.05, 1344, 760, False)), record)
    self.assertIsNone(runtime.display_result(record, 1.4, (27, 1.35, 1344, 760, False)))
    self.assertIsNone(runtime.display_result(record, 1.1, (20, 1.05, 1344, 760, True)))

  def test_ui_candidate_freshness_and_permission(self):
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / 'record.json'
      fresh = {'version': 1, 'timestamp': 10., 'control_permission': False, 'state': 'candidate'}
      stale = dict(fresh, timestamp=9.)
      bad_permission = dict(fresh, control_permission=True)
      for record, expected in ((fresh, fresh), (stale, None), (bad_permission, None)):
        path.write_text(json.dumps(record))
        self.assertIs(runtime.ui_candidate(now=10.05, path=path) is not None, expected is not None)
      path.write_text('not json')
      self.assertIsNone(runtime.ui_candidate(now=10.05, path=path))
      path.write_text('x' * 4097)
      self.assertIsNone(runtime.ui_candidate(now=10.05, path=path))


class TestRegistration(unittest.TestCase):
  def test_parameter_defaults_off_and_is_registered(self):
    root = Path(runtime.__file__).resolve().parents[2]  # .../openpilot
    self.assertIn('{"LeadBrakeLights", {PERSISTENT, BOOL, "0"}}',
                  (root / 'common' / 'params_keys.h').read_text())
    # This fork keeps the whole SignalAssist experiment family out of the
    # settings catalog (params-only), so the JSON must NOT reference it.
    settings = (root / 'sunnypilot' / 'carrot_settings_sp.json').read_text(encoding='utf8')
    self.assertNotIn('LeadBrakeLights', settings)

  def test_detector_uses_this_forks_camera_layout(self):
    # The fork exposes the road camera as narrow_road (not fcam); the detector
    # must keep importing cleanly and agree with the shadow reference size.
    from openpilot.common.transformations.camera import DEVICE_CAMERAS
    from openpilot.selfdrive.modeld.signal_tracking_shadow import REFERENCE_SIZE
    config = DEVICE_CAMERAS[('mici', 'os04c10')].narrow_road
    self.assertEqual(config.size, REFERENCE_SIZE)


if __name__ == '__main__':
  unittest.main()
