"""Radar display: point selection and projection geometry (ported from carrot).

sp has no RadarData.displayPoints / hasDisplayData, so support is established
from the liveTracks subscriber health plus a point freshness gate. Everything
here is dependency-free so it runs off-device as well as on it; the drawing that
consumes it lives in ``sunnypilot.onroad.radar_points``.
"""
import time
import unittest
from types import SimpleNamespace as NS

import numpy as np

from openpilot.selfdrive.ui.radar_display import (
  DISPLAY_MAX_DISTANCE_M, DISPLAY_MAX_LATERAL_M, RADAR_MIN_DRAW_DISTANCE_M, RADAR_MIN_MOVING_SPEED_MS,
  RADAR_POINT_HEIGHT_M, RadarDisplayPoint, combined_speed, path_length_idx, predicted_offset,
  radar_point_z, select_radar_display_points, speed_text,
)
from openpilot.selfdrive.ui.signal_status import (
  POINT_COLOR_LOW_CONFIDENCE, POINT_COLOR_VISION_ONLY, SIGNAL_PALETTE, point_box_color,
)


def _point(track_id=1, dRel=20.0, yRel=0.0, vLead=10.0, yvRel=0.0, measured=True, source="frontRadar"):
  return NS(trackId=track_id, dRel=dRel, yRel=yRel, vRel=0.0, aRel=0.0, yvRel=yvRel, vLead=vLead,
           measured=measured, radarSource=source, aLead=0.0, jLead=0.0)


_ERROR_FIELDS = ("canError", "radarFault", "wrongConfig", "radarUnavailableTemporary")


def _errors(active):
  """Minimal stand-in for the capnp `errors` struct (needs to_dict())."""
  fields = dict.fromkeys(_ERROR_FIELDS, False)
  fields.update(dict.fromkeys(active, True))
  return NS(**fields, to_dict=lambda: dict(fields))


class _SM:
  def __init__(self, points, *, seen=True, alive=True, valid=True, errors=None,
               recv_time=None, log_mono=None, recv_frame=5):
    self._data = NS(points=points, hasDisplayData=bool(points), errors=_errors(errors or []))
    now = time.monotonic()
    self.seen = {"liveTracks": seen}
    self.alive = {"liveTracks": alive}
    self.valid = {"liveTracks": valid}
    self.recv_time = {"liveTracks": now if recv_time is None else recv_time}
    self.recv_frame = {"liveTracks": recv_frame}
    self.logMonoTime = {"liveTracks": (now * 1e9) if log_mono is None else log_mono}

  def __getitem__(self, key):
    return self._data if key == "liveTracks" else None


class TestSelectRadarDisplayPoints(unittest.TestCase):
  def test_disabled_when_show_level_low(self):
    self.assertIsNone(select_radar_display_points(_SM([_point()]), 2))

  def test_none_when_service_not_seen(self):
    self.assertIsNone(select_radar_display_points(_SM([_point()], seen=False), 3))

  def test_empty_when_no_display_data(self):
    self.assertEqual(select_radar_display_points(_SM([]), 3), ())

  def test_returns_measured_front_radar_points(self):
    pts = [_point(1, 20.0, -1.0), _point(2, 40.0, 1.5)]
    out = select_radar_display_points(_SM(pts), 3)
    self.assertEqual(len(out), 2)
    self.assertIsInstance(out[0], RadarDisplayPoint)
    self.assertEqual(out[1].dRel, 40.0)

  def test_predicted_points_dropped(self):
    out = select_radar_display_points(_SM([_point(measured=False)]), 3)
    self.assertEqual(len(out), 0)

  def test_non_front_radar_dropped(self):
    out = select_radar_display_points(_SM([_point(source="rearRadar")]), 3)
    self.assertEqual(len(out), 0)

  def test_out_of_range_dropped(self):
    far = select_radar_display_points(_SM([_point(dRel=DISPLAY_MAX_DISTANCE_M + 5.0)]), 3)
    wide = select_radar_display_points(_SM([_point(yRel=DISPLAY_MAX_LATERAL_M + 1.0)]), 3)
    zero = select_radar_display_points(_SM([_point(dRel=0.0)]), 3)
    self.assertEqual((len(far), len(wide), len(zero)), (0, 0, 0))

  def test_duplicate_track_id_yields_empty(self):
    out = select_radar_display_points(_SM([_point(1), _point(1)]), 3)
    self.assertEqual(out, ())

  def test_stale_frame_yields_empty(self):
    out = select_radar_display_points(_SM([_point()], recv_time=time.monotonic() - 5.0), 3)
    self.assertEqual(out, ())


class TestPathLengthIdx(unittest.TestCase):
  def test_empty_is_zero(self):
    self.assertEqual(path_length_idx(np.empty((0,), dtype=np.float32), 12.0), 0)

  def test_none_is_zero(self):
    self.assertEqual(path_length_idx(None, 12.0), 0)

  def test_last_index_at_or_below_distance(self):
    x = np.array([0.0, 4.0, 8.0, 12.0, 16.0], dtype=np.float32)
    self.assertEqual(path_length_idx(x, 9.5), 2)
    self.assertEqual(path_length_idx(x, 12.0), 3)

  def test_distance_below_first_point(self):
    self.assertEqual(path_length_idx(np.array([4.0, 8.0], dtype=np.float32), 1.0), 0)


class TestRadarPointZ(unittest.TestCase):
  @staticmethod
  def _lane():
    return np.array([[0.0, 0.0, 0.0], [50.0, 0.0, 0.5], [100.0, 0.0, 1.0]], dtype=np.float32)

  def test_none_without_lane(self):
    self.assertIsNone(radar_point_z(None, 20.0))
    self.assertIsNone(radar_point_z(np.empty((0, 3), dtype=np.float32), 20.0))

  def test_samples_lane_height(self):
    # 60 m lands on the second sample (x=50), so the box sits at 0.5 m - height
    self.assertAlmostEqual(radar_point_z(self._lane(), 60.0), 0.5 - RADAR_POINT_HEIGHT_M)
    self.assertAlmostEqual(radar_point_z(self._lane(), 20.0), 0.0 - RADAR_POINT_HEIGHT_M)

  def test_none_when_missing_columns(self):
    lane = np.array([[0.0, 0.0], [10.0, 1.0]], dtype=np.float32)
    self.assertIsNone(radar_point_z(lane, 5.0))


class TestCombinedSpeed(unittest.TestCase):
  def test_positive_stays_positive(self):
    v_abs, v_sum = combined_speed(3.0, 4.0)
    self.assertAlmostEqual(v_abs, 5.0)
    self.assertAlmostEqual(v_sum, 5.0)

  def test_negative_keeps_sign(self):
    v_abs, v_sum = combined_speed(-3.0, 4.0)
    self.assertAlmostEqual(v_abs, 5.0)
    self.assertAlmostEqual(v_sum, -5.0)


class TestSpeedText(unittest.TestCase):
  def test_metric_is_kph(self):
    self.assertEqual(speed_text(10.0, True), "36")

  def test_imperial_is_mph(self):
    self.assertEqual(speed_text(10.0, False), "22")

  def test_negative_keeps_sign(self):
    self.assertEqual(speed_text(-10.0, True), "-36")


class TestPointBoxColor(unittest.TestCase):
  def test_vision_only_is_blue(self):
    self.assertEqual(point_box_color(1.0, False, 0.03), POINT_COLOR_VISION_ONLY)

  def test_low_confidence_match_is_green(self):
    self.assertEqual(point_box_color(1.0, True, 0.01), POINT_COLOR_LOW_CONFIDENCE)

  def test_closing_is_amber_and_opening_is_red(self):
    self.assertEqual(point_box_color(1.0, True, 0.03), SIGNAL_PALETTE[3])
    self.assertEqual(point_box_color(-1.0, True, 0.03), SIGNAL_PALETTE[1])


class TestPredictedOffset(unittest.TestCase):
  def test_moves_forward(self):
    d_rel, y_rel = predicted_offset(20.0, 0.0, 10.0, 1.0)
    self.assertAlmostEqual(d_rel, 25.0)
    self.assertAlmostEqual(y_rel, 0.5)

  def test_never_goes_behind_two_meters(self):
    d_rel, _ = predicted_offset(3.0, 0.0, -20.0, 0.0)
    self.assertEqual(d_rel, 2.0)

  def test_geometry_constants_are_sane(self):
    self.assertGreater(RADAR_MIN_MOVING_SPEED_MS, 0.0)
    self.assertLess(RADAR_MIN_DRAW_DISTANCE_M, 5.0)
    self.assertLess(RADAR_POINT_HEIGHT_M, 1.0)

  def test_malformed_is_safe(self):
    self.assertIsNone(select_radar_display_points(object(), 3))


if __name__ == "__main__":
  unittest.main()
