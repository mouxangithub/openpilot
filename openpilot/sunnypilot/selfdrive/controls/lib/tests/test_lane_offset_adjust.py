"""CP-2 lane-geometry offset (carrot adjustLaneOffset port) unit tests (PC-safe, run with pytest --noconftest).

Covers:
- the pure compute_lane_offset decision table (roomy / tight / asymmetric lanes,
  lane-width ramp, KeepMinDistanceFromLane clearance cap, ADJUST_OFFSET_LIMIT)
- LaneOffsetAdjust convergence on fake modelV2 data + inactive/disabled resets
- default-off equivalence of LaneCenteringController (identical output stream
  with and without the offset handle)
"""
import sys
import types

try:
  import fcntl  # noqa: F401
except ImportError:
  sys.modules.setdefault('fcntl', types.ModuleType('fcntl'))

# common.params loads libparams_c.so via ctypes at import time; no Windows build
# exists. Same stub pattern as test_conditional_experimental_mode.py. Production
# code treats an unavailable Params backend as "defaults" (feature off).
try:
  from openpilot.common.params import Params  # noqa: F401
except (OSError, FileNotFoundError):
  _params_mod = types.ModuleType('openpilot.common.params')

  class _ParamsStub:
    def __init__(self, *args, **kwargs):
      raise RuntimeError("real Params is unavailable on PC; inject a fake in tests")

  _params_mod.Params = _ParamsStub
  sys.modules['openpilot.common.params'] = _params_mod

from types import SimpleNamespace

import pytest
import numpy as np

from openpilot.selfdrive.controls.lib.lane_centering import LaneCenteringController
from openpilot.sunnypilot.selfdrive.controls.lib.lane_offset_adjust import (
  ADJUST_OFFSET_LIMIT,
  KEEP_MIN_DISTANCE_FROM_LANE,
  LaneOffsetAdjust,
  compute_lane_offset,
)

X = np.arange(0.0, 50.0, 0.5)  # covers lookahead up to 35 m
V_EGO = 15.0                    # 15 m/s -> 54 km/h, above the shift speed ramp


def fake_model(left_y=-1.6, right_y=1.6, path_y=0.0, prob=0.9,
               lane_width_left=0.0, lane_width_right=0.0):
  """Fake modelV2: lane lines 0-based, meta.laneWidthLeft/Right in meters."""
  left = SimpleNamespace(x=X.copy(), y=np.full_like(X, left_y))
  right = SimpleNamespace(x=X.copy(), y=np.full_like(X, right_y))
  return SimpleNamespace(
    laneLines=[SimpleNamespace(x=X.copy(), y=np.full_like(X, 0.0)), left, right],
    laneLineProbs=np.array([0.0, prob, prob]),
    laneLineStds=np.array([1.0, 0.1, 0.1]),
    position=SimpleNamespace(x=X.copy(), y=np.full_like(X, path_y), yStd=np.full_like(X, 0.05)),
    meta=SimpleNamespace(laneChangeState=0, laneWidthLeft=lane_width_left, laneWidthRight=lane_width_right),
  )


class FakeParams:
  """Dict-backed Params double: get(key) -> value or None."""

  def __init__(self, data=None):
    self._data = dict(data or {})

  def get(self, key, **kwargs):
    return self._data.get(key)


class TestComputeLaneOffsetPure:
  def test_zero_when_adjust_offset_off(self):
    assert compute_lane_offset(3.2, 3.0, 2.0, 0.0) == 0.0
    assert compute_lane_offset(3.2, 3.0, 2.0, -0.1) == 0.0

  def test_zero_when_both_adjacent_lanes_roomy(self):
    assert compute_lane_offset(3.2, 3.0, 2.5, 0.2) == 0.0

  def test_zero_when_both_adjacent_lanes_tight(self):
    assert compute_lane_offset(3.2, 1.9, 1.5, 0.2) == 0.0

  def test_zero_when_adjacent_widths_equal(self):
    assert compute_lane_offset(3.2, 2.1, 2.1, 0.2) == 0.0

  def test_wide_left_adjacent_lane_shifts_right(self):
    # lane 3.2 m: ramp full (>= 2.9), keep-min cap non-binding (1.6 + 2.0 - 1.35 = 2.25)
    assert compute_lane_offset(3.2, 3.0, 2.0, 0.2) == 0.2

  def test_wide_right_adjacent_lane_shifts_left(self):
    assert compute_lane_offset(3.2, 2.0, 3.0, 0.2) == -0.2

  def test_lane_width_ramp(self):
    # 2.7 m ego lane: ramp = (2.7 - 2.5) / (2.9 - 2.5) = 0.5 -> half of the shift
    assert compute_lane_offset(2.7, 3.0, 1.5, 0.2) == pytest.approx(0.1)
    # 2.5 m ego lane: ramp zero, no shift even on an asymmetric road
    assert compute_lane_offset(2.5, 3.0, 1.5, 0.2) == 0.0

  def test_keep_min_distance_cap_with_unknown_shift_side_width(self):
    # shift-side adjacent width unknown (0): only the shared line counts
    # cap = 1.6 - 1.35 = 0.25 -> the full 0.2 shift still fits
    assert compute_lane_offset(3.2, 3.0, 0.0, 0.2) == pytest.approx(0.2)
    # narrower lane: cap = 1.4 - 1.35 = 0.05 -> shift clamped to 0.05
    assert compute_lane_offset(2.8, 3.0, 0.0, 0.2) == pytest.approx(0.05)

  def test_keep_min_distance_cap_with_narrow_edge_side(self):
    # shift toward a near-edge side (adjacent width 0.3 m):
    # cap = 1.6 + 0.3 - 1.35 = 0.55 -> the 0.3 shift fits
    assert compute_lane_offset(3.2, 3.0, 0.3, 0.3) == pytest.approx(0.3)
    # full shift 2.0 m request: clamped by the keep-min cap, then by the hard limit
    assert compute_lane_offset(3.2, 3.0, 0.3, 2.0) == ADJUST_OFFSET_LIMIT

  def test_adjust_offset_limit(self):
    # wide room for the shift but the hard 0.4 m cap applies
    assert compute_lane_offset(3.2, 3.0, 2.0, 2.0) == ADJUST_OFFSET_LIMIT

  def test_custom_keep_min_distance(self):
    # keep 0.0 m: no keep-min constraint, only the hard limit applies
    assert compute_lane_offset(3.2, 3.0, 2.0, 2.0, keep_min_distance=0.0) == ADJUST_OFFSET_LIMIT
    # keep 1.6 m with an unknown shift-side width: cap = 1.6 - 1.6 = 0.0 -> no shift
    assert compute_lane_offset(3.2, 3.0, 0.0, 0.2, keep_min_distance=1.6) == 0.0

  def test_default_keep_min_distance_value(self):
    assert KEEP_MIN_DISTANCE_FROM_LANE == 1.35


class TestLaneOffsetAdjust:
  def test_disabled_by_default_returns_zero(self):
    adjust = LaneOffsetAdjust(params=FakeParams())
    for _ in range(20):
      assert adjust.update(fake_model(lane_width_left=3.0, lane_width_right=2.0), V_EGO, active=True) == 0.0

  def test_inactive_resets_and_returns_zero(self):
    adjust = LaneOffsetAdjust(params=FakeParams({"AdjustLaneOffsetEnabled": "1",
                                                 "AdjustLaneOffset": "0.2"}))
    for _ in range(100):
      adjust.update(fake_model(lane_width_left=3.0, lane_width_right=2.0), V_EGO, active=True)
    assert adjust.offset_filtered.x > 0.0
    # inactive frame: reset + zero
    assert adjust.update(fake_model(lane_width_left=3.0, lane_width_right=2.0), V_EGO, active=False) == 0.0
    assert adjust.offset_filtered.x == 0.0

  def test_converges_to_cp_shift_away_from_wide_side(self):
    adjust = LaneOffsetAdjust(params=FakeParams({"AdjustLaneOffsetEnabled": "1",
                                                 "AdjustLaneOffset": "0.2"}))
    model = fake_model(lane_width_left=3.0, lane_width_right=2.0)
    out = 0.0
    for _ in range(400):
      out = adjust.update(model, V_EGO, active=True)
    # wide LEFT adjacent lane -> shift right (positive), full 0.2 m after convergence
    assert 0.19 < out <= 0.2 + 1e-9

  def test_speed_ramp_suppresses_shift_at_standstill(self):
    adjust = LaneOffsetAdjust(params=FakeParams({"AdjustLaneOffsetEnabled": "1"}))
    model = fake_model(lane_width_left=3.0, lane_width_right=2.0)
    out = 0.0
    for _ in range(200):
      out = adjust.update(model, 1.0, active=True)  # 3.6 km/h < 5 km/h ramp start
    assert out == 0.0

  def test_bad_lane_data_returns_zero(self):
    adjust = LaneOffsetAdjust(params=FakeParams({"AdjustLaneOffsetEnabled": "1"}))
    # missing lane lines / zero-prob lines: filtered lane width stays at init,
    # adjacent widths unknown -> no shift
    broken = SimpleNamespace(laneLines=[], laneLineProbs=np.array([]),
                             meta=SimpleNamespace(laneWidthLeft=0.0, laneWidthRight=0.0))
    for _ in range(50):
      out = adjust.update(broken, V_EGO, active=True)
    assert out == 0.0

  def test_param_change_is_picked_up_periodically(self):
    params = FakeParams({"AdjustLaneOffsetEnabled": "1", "AdjustLaneOffset": "0.2"})
    adjust = LaneOffsetAdjust(params=params)
    assert adjust.enabled
    params._data["AdjustLaneOffsetEnabled"] = "0"
    adjust.read_params()
    assert not adjust.enabled


class TestLaneCenteringDefaultOffEquivalence:
  def _run_stream(self, controller, frames=60, path_y=0.4, **model_kwargs):
    outputs = []
    model = fake_model(path_y=path_y, **model_kwargs)
    for _ in range(frames):
      outputs.append(controller.update(0.01, model, 15.0, True, 0.0, 0.0, True, True))
    return outputs

  def test_default_off_matches_no_handle(self):
    with_handle = LaneCenteringController()
    without_handle = LaneCenteringController()
    # simulate the "SP module unavailable" branch
    from openpilot.selfdrive.controls.lib.lane_centering import _OFFSET_ADJUST_UNAVAILABLE
    without_handle._offset_adjust_checked = True
    without_handle._offset_adjust = _OFFSET_ADJUST_UNAVAILABLE

    stream_with = self._run_stream(with_handle)
    stream_without = self._run_stream(without_handle)
    assert stream_with == stream_without
    # the default handle exists; it is either unavailable on this host or disabled
    adjust = with_handle._offset_adjust
    if adjust is not _OFFSET_ADJUST_UNAVAILABLE:
      assert not adjust.enabled

  def test_enabled_offset_changes_output(self):
    controller = LaneCenteringController()
    controller._offset_adjust = LaneOffsetAdjust(params=FakeParams({
      "AdjustLaneOffsetEnabled": "1", "AdjustLaneOffset": "0.2"}))
    controller._offset_adjust_checked = True

    stream_with = self._run_stream(controller, frames=300, lane_width_left=3.0, lane_width_right=2.0)
    baseline = self._run_stream(LaneCenteringController(), frames=300, lane_width_left=3.0, lane_width_right=2.0)
    # after convergence the CP-2 shift (+0.2 m right) must pull the correction right (less negative)
    assert stream_with[-1] > baseline[-1]

  def test_reset_clears_offset_filters(self):
    controller = LaneCenteringController()
    controller._offset_adjust = LaneOffsetAdjust(params=FakeParams({
      "AdjustLaneOffsetEnabled": "1", "AdjustLaneOffset": "0.2"}))
    controller._offset_adjust_checked = True
    model = fake_model(lane_width_left=3.0, lane_width_right=2.0)
    for _ in range(100):
      controller.update(0.01, model, 15.0, True, 0.0, 0.0, True, True)
    assert controller._offset_adjust.offset_filtered.x > 0.0
    controller.reset()
    assert controller._offset_adjust.offset_filtered.x == 0.0
    assert controller._correction == 0.0
