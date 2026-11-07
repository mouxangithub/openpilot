"""Tests for state_api._road_model (road-lite scene data)."""

from types import SimpleNamespace

from webui.server.bridge.state_api import _road_model, _carrot_lane_blocked


def _line(xs, ys):
  return SimpleNamespace(x=xs, y=ys)


def _make_sm(path_x, path_y, path_std=None):
  class _Model:
    pass

  class _SM(dict):
    pass

  model = _Model()
  model.roadEdges = [_line([0, 200], [-5.5, -11.0]), _line([0, 200], [5.5, 11.0])]
  model.laneLines = [
    _line([0, 200], [-5.5, -11.0]),
    _line([0, 200], [-1.85, -3.7]),
    _line([0, 200], [1.85, 3.7]),
    _line([0, 200], [5.5, 11.0]),
  ]
  model.laneLineProbs = [0.9, 0.95, 0.95, 0.9]
  model.leadsV3 = []
  path = _Model()
  path.x = path_x
  path.y = path_y
  if path_std is not None:
    path.std = path_std
  model.path = path
  sm = _SM()
  sm.valid = {"modelV2": True}
  sm["modelV2"] = model
  return sm


def test_road_model_samples_planned_path():
  sm = _make_sm(
    path_x=[2.0, 50.0, 190.0],
    path_y=[0.0, 1.0, -1.0],
    path_std=[0.05, 0.3, 0.6],
  )
  rm = _road_model(sm)
  assert rm is not None
  assert rm["path"] is not None
  assert len(rm["path"]) == len(rm["dists"])
  # interpolated first point (5m between 2m and 50m), exact middle, interpolated end
  assert abs(rm["path"][0] - 0.06) < 0.01
  assert rm["path"][3] == 1.0          # 50m → exact
  assert abs(rm["path"][-1] - (-0.57)) < 0.01  # 160m between 50m and 190m
  assert rm["path_std"] is not None
  assert abs(rm["path_std"][3] - 0.3) < 0.01
  # both road edges present → all lane lines are dashed dividers
  assert rm["line_types"] == [0, 0, 0, 0]


def test_road_model_missing_edge_makes_solid_outer_lines():
  sm = _make_sm(path_x=[2.0, 50.0, 190.0], path_y=[0.0, 1.0, -1.0])
  sm["modelV2"].roadEdges = [None, None]  # type: ignore[attr-defined]
  rm = _road_model(sm)
  assert rm is not None
  assert rm["line_types"] == [1, 0, 0, 1]


def test_road_model_path_missing_is_none():
  sm = _make_sm(path_x=[0.0], path_y=[0.0])
  rm = _road_model(sm)
  assert rm is not None
  assert rm["path"] is None
  assert rm["path_std"] is None


def test_road_model_invalid_model_returns_none():
  sm = SimpleNamespace(valid={"modelV2": False})
  assert _road_model(sm) is None


class _FakeSM:
  def __init__(self, valid, data=None):
    self.valid = valid
    self._data = data or {}

  def __getitem__(self, key):
    return self._data[key]


def test_carrot_lane_blocked_reads_carrot_fields():
  cssp = SimpleNamespace(carrotLaneValid=True, carrotLeftLineBlocked=True, carrotRightLineBlocked=False)
  sm = _FakeSM({"carStateSP": True}, {"carStateSP": cssp})
  assert _carrot_lane_blocked(sm) == (True, False)


def test_carrot_lane_blocked_returns_false_when_invalid():
  cssp = SimpleNamespace(carrotLaneValid=False, carrotLeftLineBlocked=True, carrotRightLineBlocked=True)
  sm = _FakeSM({"carStateSP": True}, {"carStateSP": cssp})
  assert _carrot_lane_blocked(sm) == (False, False)


def test_carrot_lane_blocked_returns_false_when_service_dead():
  sm = _FakeSM({"carStateSP": False})
  assert _carrot_lane_blocked(sm) == (False, False)
