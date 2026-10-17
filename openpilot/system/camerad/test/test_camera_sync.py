"""Synthetic camera phase-sync regression around TestCamerad.test_frame_sync.

Adapted from navipilot's tici-restore commit 36fc3858b. That fork restores
in-phase cabin capture for AR0231; this fork keeps the stock staggered cabin
contract, so the fixture pins the stock relationship instead: narrow/wide road
frames in phase, cabin staggered ~25 ms, for every supported road sensor.
"""
import unittest

import numpy as np

from openpilot.system.camerad.test import test_camerad

CABIN_STAGGER_NS = 25_000_000


class TestCameraSync(unittest.TestCase):
  @staticmethod
  def camera_logs(sensor, cabin_offset_ns):
    frames = np.arange(30)
    timestamps = 1_000_000_000 + frames * 50_000_000
    return {
      camera: {
        "t": timestamps / 1e9,
        "frameId": frames.copy(),
        "timestampSof": timestamps + (cabin_offset_ns if camera == "cabinCameraState" else 0),
        "imageSensor": np.full(len(frames), sensor),
      }
      for camera in test_camerad.CAMERAS
    }

  @staticmethod
  def check_logs(logs):
    checker = test_camerad.TestCamerad("test_frame_sync")
    checker.logs = logs
    checker.test_frame_sync()

  def test_expected_stagger_is_accepted(self):
    for sensor in ("ar0231", "ox03c10", "os04c10"):
      with self.subTest(sensor=sensor):
        self.check_logs(self.camera_logs(sensor, CABIN_STAGGER_NS))

  def test_wrong_cabin_stagger_is_rejected(self):
    for sensor in ("ar0231", "os04c10"):
      for offset in (0, 10_000_000, 50_000_000):
        with self.subTest(sensor=sensor, offset_ns=offset), self.assertRaises(AssertionError):
          self.check_logs(self.camera_logs(sensor, offset))

  def test_frame_ids_must_remain_aligned(self):
    logs = self.camera_logs("ar0231", CABIN_STAGGER_NS)
    logs["cabinCameraState"]["frameId"] += 1
    with self.assertRaisesRegex(AssertionError, "frame IDs not aligned"):
      self.check_logs(logs)

  def test_road_phase_tolerance_is_preserved(self):
    logs = self.camera_logs("ar0231", CABIN_STAGGER_NS)
    logs["wideRoadCameraState"]["timestampSof"] += 1100001
    with self.assertRaisesRegex(AssertionError, "Frames not synced properly"):
      self.check_logs(logs)


if __name__ == "__main__":
  unittest.main()
