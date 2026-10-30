"""Opt-in traffic-light observer: gating, artifact checks and the record it writes.

The observer must never take over the vehicle's behaviour. These tests pin the
parts of that promise that are testable without a car: it stays off unless its
own opt-in file exists, it refuses a model whose checksum does not match the
manifest, it never writes a control permission, and it rejects a camera
geometry it has no agreed mapping for.
"""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

try:
  import cv2  # noqa: F401
  HAS_CV2 = True
except ImportError:
  HAS_CV2 = False

from openpilot.selfdrive.modeld.signal_yolo_shadow import (
  MAX_OBSERVATION_BYTES, MODEL_CLASSES, MODEL_SHA256, REFERENCE_SIZE, SUPPORTED_SIZES,
  TARGET_HZ, _overall_state, control_requested, copy_nv12_rgb, install, next_delay,
  publish_observation, reference_control_record, requested, validate_artifact,
)
from openpilot.sunnypilot.carrot.signal_yolo_detector import HousingObservation

REPO_MODEL = (Path(__file__).resolve().parents[3] / 'sunnypilot/assets/vision_models/signal_light_detector.onnx')


def _manifest(**overrides):
  meta = {'version': 1, 'mode': 'camera_comparison_only', 'model_sha256': MODEL_SHA256,
          'classes': MODEL_CLASSES, 'input_size': 416, 'control_permission': False}
  meta.update(overrides)
  return meta


class TestOptIn(unittest.TestCase):
  def test_absent_file_means_off(self):
    with tempfile.TemporaryDirectory() as directory:
      self.assertFalse(requested(Path(directory)))

  def test_enabled_only_for_exactly_one(self):
    with tempfile.TemporaryDirectory() as directory:
      (Path(directory) / 'enabled').write_text('1')
      self.assertTrue(requested(Path(directory)))
      (Path(directory) / 'enabled').write_text('0')
      self.assertFalse(requested(Path(directory)))
      (Path(directory) / 'enabled').write_text('yes')
      self.assertFalse(requested(Path(directory)))


class TestValidateArtifact(unittest.TestCase):
  def test_matching_manifest_and_checksum_is_accepted(self):
    with tempfile.TemporaryDirectory() as directory:
      directory = Path(directory)
      (directory / 'installed.json').write_text(json.dumps(_manifest()))
      path, meta = validate_artifact(directory, REPO_MODEL)
      self.assertEqual(path, REPO_MODEL)
      self.assertEqual(meta['mode'], 'camera_comparison_only')

  def test_the_committed_model_matches_the_pinned_checksum(self):
    # The observer is installed from the repository asset, so the bytes that
    # ship must be the bytes the manifest pins.
    import hashlib
    self.assertTrue(REPO_MODEL.is_file())
    self.assertEqual(hashlib.sha256(REPO_MODEL.read_bytes()).hexdigest(), MODEL_SHA256)

  def test_checksum_mismatch_is_rejected(self):
    with tempfile.TemporaryDirectory() as directory:
      directory = Path(directory)
      (directory / 'signal_light_detector.onnx').write_bytes(b'wrong')
      (directory / 'installed.json').write_text(json.dumps(_manifest()))
      with self.assertRaises(ValueError):
        validate_artifact(directory, directory / 'signal_light_detector.onnx')

  def test_control_manifest_is_rejected(self):
    # A manifest that claims control permission must never be accepted by a
    # comparison-only observer.
    with tempfile.TemporaryDirectory() as directory:
      directory = Path(directory)
      (directory / 'signal_light_detector.onnx').write_bytes(b'x')
      (directory / 'installed.json').write_text(json.dumps(_manifest(mode='control')))
      with self.assertRaises(ValueError):
        validate_artifact(directory, directory / 'signal_light_detector.onnx')

  def test_class_list_mismatch_is_rejected(self):
    with tempfile.TemporaryDirectory() as directory:
      directory = Path(directory)
      (directory / 'signal_light_detector.onnx').write_bytes(b'x')
      (directory / 'installed.json').write_text(json.dumps(_manifest(classes=['background'])))
      with self.assertRaises(ValueError):
        validate_artifact(directory, directory / 'signal_light_detector.onnx')

  def test_missing_manifest_is_rejected(self):
    with tempfile.TemporaryDirectory() as directory:
      directory = Path(directory)
      with self.assertRaises(OSError):
        validate_artifact(directory, directory / 'signal_light_detector.onnx')


class TestInstall(unittest.TestCase):
  def test_install_writes_the_model_and_a_comparison_only_manifest(self):
    with tempfile.TemporaryDirectory() as directory:
      directory = Path(directory)
      model = directory / 'signal_light_detector.onnx'
      manifest = install(directory, model)
      self.assertTrue(model.is_file())
      self.assertEqual(manifest['mode'], 'camera_comparison_only')
      self.assertFalse(manifest['control_permission'])
      self.assertEqual(manifest['model_sha256'], MODEL_SHA256)
      # Installing must not enable the observer.
      self.assertFalse(requested(directory))

  def test_installed_artifact_validates(self):
    with tempfile.TemporaryDirectory() as directory:
      directory = Path(directory)
      model = directory / 'signal_light_detector.onnx'
      install(directory, model)
      path, meta = validate_artifact(directory, model)
      self.assertEqual(path, model)
      self.assertEqual(meta['mode'], 'camera_comparison_only')

  def test_manifest_claiming_control_is_rejected(self):
    with tempfile.TemporaryDirectory() as directory:
      directory = Path(directory)
      model = directory / 'signal_light_detector.onnx'
      install(directory, model)
      manifest = json.loads((directory / 'installed.json').read_text())
      manifest['control_permission'] = True
      (directory / 'installed.json').write_text(json.dumps(manifest))
      with self.assertRaises(ValueError):
        validate_artifact(directory, model)

  def test_install_rejects_a_model_with_the_wrong_checksum(self):
    with tempfile.TemporaryDirectory() as directory:
      directory = Path(directory)
      source = directory / 'wrong.onnx'
      source.write_bytes(b'not the model')
      with self.assertRaises(ValueError):
        install(directory, directory / 'signal_light_detector.onnx', source)

  def test_install_rejects_a_missing_source_model(self):
    with tempfile.TemporaryDirectory() as directory:
      directory = Path(directory)
      with self.assertRaises(FileNotFoundError):
        install(directory, directory / 'signal_light_detector.onnx', directory / 'missing.onnx')


class TestScheduling(unittest.TestCase):
  def test_rate_is_bounded(self):
    self.assertGreaterEqual(next_delay(0.), 1.0 / TARGET_HZ - .01)

  def test_cpu_duty_is_bounded(self):
    # A slow frame must not be followed immediately by another one; the floor
    # is measured against wall time (the forward runs two cv2 threads).
    self.assertGreaterEqual(next_delay(.1), 3 * .1)

  def test_delay_never_goes_negative(self):
    self.assertGreaterEqual(next_delay(10.), .05)


class TestNv12Copy(unittest.TestCase):
  @unittest.skipUnless(HAS_CV2, 'needs cv2')
  def test_padded_buffer_is_copied_without_mutation(self):
    raw = np.full(60, 77, np.uint8)
    raw[:8] = raw[12:20] = [16, 16, 235, 235, 81, 81, 145, 145]
    before = raw.copy()
    rgb = copy_nv12_rgb(type('F', (), {'width': 8, 'height': 2, 'stride': 12, 'uv_offset': 36,
                                       'data': raw.tobytes()})())
    np.testing.assert_array_equal(raw, before)
    self.assertEqual(rgb.shape, (2, 8, 3))

  @unittest.skipUnless(HAS_CV2, 'needs cv2')
  def test_invalid_layout_is_rejected(self):
    frame = type('F', (), {'width': 3, 'height': 2, 'stride': 4, 'uv_offset': 8,
                           'data': bytes(12)})()
    with self.assertRaises(ValueError):
      copy_nv12_rgb(frame)

  @unittest.skipUnless(HAS_CV2, 'needs cv2')
  def test_truncated_buffer_is_rejected(self):
    frame = type('F', (), {'width': 4, 'height': 2, 'stride': 4, 'uv_offset': 8,
                           'data': bytes(10)})()
    with self.assertRaises(ValueError):
      copy_nv12_rgb(frame)


class TestPublish(unittest.TestCase):
  def test_record_is_written_atomically(self):
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / 'obs.json'
      publish_observation({'version': 1}, path)
      self.assertEqual(json.loads(path.read_text()), {'version': 1})
      self.assertFalse(path.with_suffix('.tmp').exists())

  def test_oversized_record_is_rejected(self):
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / 'obs.json'
      with self.assertRaises(ValueError):
        publish_observation({'blob': 'x' * (MAX_OBSERVATION_BYTES + 1)}, path)

  def test_non_finite_values_are_rejected(self):
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / 'obs.json'
      with self.assertRaises(ValueError):
        publish_observation({'x': float('nan')}, path)


class TestOverallState(unittest.TestCase):
  def test_single_agreed_colour_is_reported(self):
    obs = [HousingObservation(state='red'), HousingObservation(state='red')]
    self.assertEqual(_overall_state(obs), 'red')

  def test_disagreeing_colours_are_unknown(self):
    obs = [HousingObservation(state='red'), HousingObservation(state='green')]
    self.assertEqual(_overall_state(obs), 'unknown')

  def test_unknown_does_not_dilute_a_known_colour(self):
    obs = [HousingObservation(state='green'), HousingObservation(state='unknown')]
    self.assertEqual(_overall_state(obs), 'green')


class TestReferenceGeometry(unittest.TestCase):
  def test_both_fork_camera_geometries_are_supported(self):
    # comma 3X (mici, OS04C10) and comma 3 (tici, OX03C10) road frames must
    # both publish; anything else is refused by the caller.
    self.assertIn((1344, 760), SUPPORTED_SIZES)
    self.assertIn((1928, 1208), SUPPORTED_SIZES)

  def test_reference_size_still_names_the_mici_road_camera(self):
    self.assertEqual(REFERENCE_SIZE, (1344, 760))


class TestControlOptIn(unittest.TestCase):
  def test_control_flag_requires_the_observer_to_be_enabled(self):
    with tempfile.TemporaryDirectory() as directory:
      directory = Path(directory)
      (directory / 'control_enabled').write_text('1')
      # The control flag alone never publishes.
      self.assertFalse(control_requested(directory))
      (directory / 'enabled').write_text('1')
      self.assertTrue(control_requested(directory))

  def test_control_flag_off_by_default_even_when_observer_runs(self):
    with tempfile.TemporaryDirectory() as directory:
      directory = Path(directory)
      (directory / 'enabled').write_text('1')
      self.assertFalse(control_requested(directory))
      (directory / 'control_enabled').write_text('0')
      self.assertFalse(control_requested(directory))


class TestReferenceControlRecord(unittest.TestCase):
  def _record(self, size, box):
    return {'version': 1, 'stream': 'road', 'size': list(size), 'frame_id': 3,
            'timestamp': 10.0, 'timestamp_eof': 10_000_000_000, 'session': 's',
            'tracks': [{'id': 1, 'box': list(box), 'state': 'red',
                        'evidence': {'raw': 'red'}}]}

  def test_c3_frame_is_mapped_into_the_reference_frame(self):
    box = [964. - 100., 604. - 50., 964. + 100., 604. + 50.]
    result = reference_control_record(self._record((1928, 1208), box))
    self.assertIsNotNone(result)
    self.assertEqual(result['size'], [1344, 760])
    self.assertEqual(result['producer'], 'yolo')
    self.assertEqual(result['timestamp_eof'], 10_000_000_000)
    mapped = result['tracks'][0]['box']
    self.assertAlmostEqual((mapped[0] + mapped[2]) / 2., 672.)
    self.assertAlmostEqual((mapped[1] + mapped[3]) / 2., 380.)
    # The angular scale shrinks the C3 box into reference pixels.
    self.assertLess(mapped[2] - mapped[0], 200.)

  def test_reference_frame_is_passed_through_but_still_tagged(self):
    box = [300., 200., 400., 260.]
    result = reference_control_record(self._record((1344, 760), box))
    self.assertIsNotNone(result)
    self.assertEqual(result['size'], [1344, 760])
    self.assertEqual(result['producer'], 'yolo')
    self.assertEqual(result['tracks'][0]['box'], box)

  def test_unknown_frame_size_is_refused_not_guessed(self):
    self.assertIsNone(reference_control_record(self._record((800, 600), [0., 0., 10., 10.])))


if __name__ == '__main__':
  unittest.main()
