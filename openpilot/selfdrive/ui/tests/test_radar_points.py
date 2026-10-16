"""Radar point overlay drawing loop (ported from carrot).

Needs a raylib context (``ui_state`` pulls in cereal/opendbc), so this suite runs
on device. The geometry it projects with is covered dependency-free in
``test_radar_display.py``.
"""
import time
import unittest
from types import SimpleNamespace as NS

import numpy as np

from openpilot.selfdrive.ui.sunnypilot.onroad import radar_points
from openpilot.selfdrive.ui.sunnypilot.onroad.radar_points import RadarPointsRenderer
from openpilot.selfdrive.ui.ui_state import ui_state

_RECT = NS(x=0.0, y=0.0, width=2160.0, height=1080.0)


def _point(d_rel=20.0, y_rel=0.0, v_lead=10.0, v_lat=0.0, measured=True, source="frontRadar"):
  return NS(trackId=1, dRel=d_rel, yRel=y_rel, vLeadK=v_lead, vLat=v_lat, radar=True, modelProb=0.03,
            measured=measured, radarSource=source)


def _project(d_rel, y_rel, z):
  return (100.0 + d_rel, 200.0 + y_rel)


def _lane():
  return np.array([[0.0, 0.0, 0.0], [50.0, 0.0, 0.5], [100.0, 0.0, 1.0]], dtype=np.float32)


class _SM:
  """Minimal SubMaster stand-in: only what select_radar_display_points reads."""

  def __init__(self, points, *, seen=True, alive=True, valid=True):
    self._data = NS(points=points, errors=NS(canError=False, radarFault=False, wrongConfig=False,
                                          radarUnavailableTemporary=False, to_dict=dict))
    now = time.monotonic()
    self.seen = {"liveTracks": seen, "modelV2": valid}
    self.alive = {"liveTracks": alive, "modelV2": valid}
    self.valid = {"liveTracks": alive and valid, "modelV2": valid}
    self.recv_time = {"liveTracks": now, "modelV2": now}
    self.recv_frame = {"liveTracks": 5, "modelV2": 5}
    self.logMonoTime = {"liveTracks": now * 1e9, "modelV2": now * 1e9}

  def __getitem__(self, key):
    return self._data if key == "liveTracks" else None


class TestRenderLoop(unittest.TestCase):
  def setUp(self):
    self._orig_flag = ui_state.carrot_radar_points
    ui_state.carrot_radar_points = True
    self._orig_rl = radar_points.rl
    self._orig_measure = radar_points.measure_text_cached
    self.calls = []
    self._fake = NS(
      Color=lambda *a: ('color',) + a,
      Rectangle=lambda *a: ('rect',) + a,
      Vector2=lambda *a: ('vec',) + a,
      WHITE=('white',),
      draw_text_ex=lambda *a: self.calls.append('text'),
      draw_line_ex=lambda *a: self.calls.append('line'),
      draw_circle=lambda *a: self.calls.append('circle'),
      draw_circle_lines=lambda *a: self.calls.append('ring'),
      draw_rectangle_rounded=lambda *a: self.calls.append('box'),
    )
    radar_points.rl = self._fake
    radar_points.measure_text_cached = lambda font, text, size, spacing=0: NS(x=float(len(text)) * size * 0.5)
    self.renderer = RadarPointsRenderer.__new__(RadarPointsRenderer)
    self.renderer._font = None

  def tearDown(self):
    ui_state.carrot_radar_points = self._orig_flag
    radar_points.rl = self._orig_rl
    radar_points.measure_text_cached = self._orig_measure

  def test_disabled_draws_nothing(self):
    ui_state.carrot_radar_points = False
    self.renderer.render(_SM([_point()]), _RECT, _lane(), _project)
    self.assertEqual(self.calls, [])

  def test_invalid_model_draws_nothing(self):
    sm = _SM([_point()])
    sm.valid["modelV2"] = False
    self.renderer.render(sm, _RECT, _lane(), _project)
    self.assertEqual(self.calls, [])

  def test_moving_point_draws_vector_then_box(self):
    self.renderer.render(_SM([_point(20.0, -1.0, 10.0, 0.5)]), _RECT, _lane(), _project)
    self.assertEqual(self.calls, ['line', 'circle', 'box', 'text', 'text', 'text'])

  def test_slow_point_is_a_star(self):
    self.renderer.render(_SM([_point(20.0, 0.0, 0.0, 0.0)]), _RECT, _lane(), _project)
    self.assertEqual(self.calls, ['text'])

  def test_near_point_is_skipped(self):
    self.renderer.render(_SM([_point(1.0, 0.0, 0.0, 0.0)]), _RECT, _lane(), _project)
    self.assertEqual(self.calls, [])

  def test_unprojectable_point_is_skipped(self):
    self.renderer.render(_SM([_point(20.0, 0.0, 10.0, 0.0)]), _RECT, _lane(), lambda *a: None)
    self.assertEqual(self.calls, [])

  def test_empty_frame_draws_nothing(self):
    self.renderer.render(_SM([]), _RECT, _lane(), _project)
    self.assertEqual(self.calls, [])

  def test_missing_lane_draws_nothing(self):
    self.renderer.render(_SM([_point()]), _RECT, None, _project)
    self.assertEqual(self.calls, [])


if __name__ == "__main__":
  unittest.main()
