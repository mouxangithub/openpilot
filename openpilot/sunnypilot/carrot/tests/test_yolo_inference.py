"""YOLO obstacle head: tracking, geometry and load lifecycle.

PC-runnable without OpenCV or the ONNX file: the detector's net path is only
exercised through load()/unload(), everything else here is pure python/numpy.
"""
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openpilot.sunnypilot.carrot.xiaoge.yolo_inference import (
  DEFAULT_INPUT_SIZE,
  REAL_HEIGHT_M,
  Track,
  Tracker,
  YoloInference,
  estimate_distance,
  estimate_lateral,
)


def _det(cid=0, cx=0.5, cy=0.5, w=0.1, h=0.2, conf=0.9):
  return {"cid": cid, "conf": conf, "cx": cx, "cy": cy, "w": w, "h": h, "d": None, "y": None}


class TestGeometry(unittest.TestCase):
  def test_distance_range_and_none(self):
    # person at 1/10 of frame height on the road camera: ~35 m away
    d = estimate_distance(0, 0.1, 2648.0, 1208)
    self.assertIsNotNone(d)
    self.assertTrue(20.0 < d < 60.0)
    # a class without a height model never gets a distance
    self.assertIsNone(estimate_distance(9, 0.1, 2648.0, 1208))
    self.assertIsNone(estimate_distance(0, 0.0, 2648.0, 1208))
    # nonsense distance (>200 m) is suppressed: a 1%-of-frame person is too far
    self.assertIsNone(estimate_distance(0, 0.01, 2648.0, 1208))
    # a person filling the frame is plausibly a few metres away
    self.assertAlmostEqual(estimate_distance(0, 0.99, 2648.0, 1208), 3.8, places=1)

  def test_lateral_sign(self):
    centre = estimate_lateral(0.5, 1.0, 2648.0, 1928, 20.0)
    self.assertEqual(centre, 0.0)
    right = estimate_lateral(0.75, 1.0, 2648.0, 1928, 20.0)
    left = estimate_lateral(0.25, 1.0, 2648.0, 1928, 20.0)
    self.assertGreater(right, 0.0)
    self.assertLess(left, 0.0)
    self.assertAlmostEqual(abs(right), abs(left), places=2)


class TestTracker(unittest.TestCase):
  def test_same_object_keeps_id(self):
    tracker = Tracker()
    now = 10.0
    tracks = tracker.update([_det(cx=0.50, cy=0.50)], now)
    tid = next(iter(tracks))
    tracks = tracker.update([_det(cx=0.52, cy=0.50)], now + 0.1)
    self.assertIn(tid, tracks)
    self.assertEqual(len(tracks), 1)
    self.assertEqual(tracks[tid].age, 1)

  def test_miss_aging_deletes_track(self):
    tracker = Tracker()
    tracker.update([_det()], 10.0)
    # Z6 semantics: deleted when miss exceeds MAX_MISS, i.e. on miss #5.
    for i in range(1, Tracker.MAX_MISS + 2):
      tracker.update([], 10.0 + i * 0.1)
    self.assertEqual(len(tracker.tracks), 0)

  def test_class_change_gets_new_id(self):
    tracker = Tracker()
    tracks = tracker.update([_det(cid=0)], 10.0)
    old_tid = next(iter(tracks))
    tracks = tracker.update([_det(cid=2, w=0.1, h=0.2)], 10.1)
    # the person track is unmatched (not matched across classes) and a new
    # vehicle track appears alongside it
    self.assertIn(old_tid, tracks)
    self.assertEqual(tracks[old_tid].miss, 1)
    self.assertEqual(len(tracks), 2)
    # after the miss budget the person track is gone
    for i in range(2, Tracker.MAX_MISS + 2):
      tracks = tracker.update([_det(cid=2, w=0.1, h=0.2)], 10.0 + i * 0.1)
    self.assertNotIn(old_tid, tracks)
    self.assertEqual(len(tracks), 1)

  def test_prediction_extrapolates_along_velocity(self):
    tr = Track(1, _det(cx=0.5, cy=0.5), 10.0)
    tr.vx, tr.vy = 0.1, -0.2
    pts = Tracker().predict(tr, horizon=0.8, steps=4)
    self.assertEqual(len(pts), 4)
    self.assertAlmostEqual(pts[-1][0], 0.5 + 0.1 * 0.8)
    self.assertAlmostEqual(pts[-1][1], 0.5 - 0.2 * 0.8)

  def test_reset_clears_everything(self):
    tracker = Tracker()
    tracker.update([_det()], 10.0)
    tracker.reset()
    self.assertEqual(tracker.tracks, {})


class TestLetterbox(unittest.TestCase):
  def test_geometry_and_canvas_reset(self):
    inf = YoloInference(input_size=DEFAULT_INPUT_SIZE)
    nh, nw = inf._letterbox_params(1208, 1928)
    self.assertEqual((nh, nw), (120, 192))
    self.assertEqual((inf._top, inf._left), (36, 0))
    # canvas is grey outside the visible region
    self.assertEqual(int(inf._canvas[0, 0]), 114)
    # a different input size must fully reset the canvas (Z6 ghost-frame bug)
    inf._canvas[:nh, :nw] = 7
    nh2, nw2 = inf._letterbox_params(608, 1928)
    self.assertEqual(int(inf._canvas[0, 0]), 114)


class TestLifecycle(unittest.TestCase):
  def test_missing_model_and_unload(self):
    with TemporaryDirectory() as d:
      inf = YoloInference(Path(d) / "missing.onnx")
      self.assertFalse(inf.load())
      self.assertFalse(inf.valid)
      inf.unload()
      self.assertIsNone(inf.net)
      self.assertFalse(inf.valid)

  def test_missing_cv2_reports_error(self):
    with TemporaryDirectory() as d:
      (Path(d) / "model.onnx").write_bytes(b"fake")
      original = sys.modules.get("cv2")
      sys.modules.pop("cv2", None)
      try:
        import openpilot.sunnypilot.carrot.xiaoge.yolo_inference as mod
        mod.cv2 = None
        inf = YoloInference(Path(d) / "model.onnx")
        self.assertFalse(inf.load())
        self.assertIn("OpenCV", inf.error)
      finally:
        mod.cv2 = original
        if original is None:
          sys.modules.pop("cv2", None)


class TestRealHeights(unittest.TestCase):
  def test_high_risk_classes_have_heights(self):
    for cid in (0, 1, 3, 16, 17):
      self.assertIn(cid, REAL_HEIGHT_M)


if __name__ == "__main__":
  unittest.main()
