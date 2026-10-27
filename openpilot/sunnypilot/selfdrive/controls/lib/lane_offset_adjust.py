"""Lane-geometry lateral offset (CarrotPilot port, CP-2 / adjustLaneOffset).

Ported from carrot: selfdrive/controls/lib/lane_planner_2.py::get_d_path
(the self.adjustLaneOffset chain, LANE_WIDTH_RAMP behavior) and the file-header
constants MIN_LANE_DISTANCE=2.6 / KEEP_MIN_DISTANCE_FROM_LANE=1.35 semantics.

Semantics (narrow-lane / truck avoidance): when the ego lane narrows, shift the
path away from the adjacent lane that offers room for traffic (a wide adjacent
lane means vehicles travel close to the shared line) toward the narrow side
(shoulder / narrow adjacent lane), ramping with the ego lane width. The shift
is capped so the shifted path keeps at least KeepMinDistanceFromLane meters
from the outer lane line (or road edge) on the side it shifts toward.

Data flow on SP (differs from carrot, which offsets path_xyz inside the lateral
planner): modelV2 (laneLines + meta.laneWidthLeft/Right, filled by modeld's
lane_width.py) -> LaneOffsetAdjust (meters, first-order smoothed) ->
LaneCenteringController (selfdrive/controls/lib/lane_centering.py) adds it to
the driver's LaneCenterOffset; the existing lane-centering chain converts the
target offset into a bounded curvature correction (kappa ~= 2*dy/L^2) that
feeds desiredCurvature -> latcontrol. Gated by AdjustLaneOffsetEnabled
(default off), so with stock params every output is unchanged.
"""
import numpy as np

from openpilot.common.filter_simple import FirstOrderFilter

try:
  from openpilot.common.params import Params
except (OSError, FileNotFoundError, ImportError):  # PC host without libparams
  Params = None

# modeld/control period. Hardcoded instead of importing common.realtime to keep
# this module importable on PC hosts (see lane_centering.py for the same trick).
_DT_MDL = 0.05

KEEP_MIN_DISTANCE_FROM_LANE = 1.35  # m, min clearance from the shifted path to the shift-side outer line
ADJUST_OFFSET_DEFAULT = 0.20        # m, full-shift magnitude once the ego lane is narrow enough
ADJUST_OFFSET_LIMIT = 0.4           # m, hard cap on the raw shift (carrot ADJUST_OFFSET_LIMIT)
MIN_ADJACENT_WIDTH = 2.0            # m, both adjacent lanes below: too tight overall, no shift
MAX_ADJACENT_WIDTH = 2.2            # m, both adjacent lanes above: roomy, no shift
LANE_WIDTH_RAMP = (2.5, 2.9)        # m, ego lane width ramp: below no shift, above full shift
SHIFT_SPEED_MIN_KPH = 5.0           # kph, speed ramp in (carrot: np.interp(v*3.6, [5., 10.], [0, 1]))
SHIFT_SPEED_MAX_KPH = 10.0
_LANE_PROB_MIN = 0.5                # carrot: l_prob/r_prob > 0.5 for the lane width estimate
_LANE_WIDTH_INIT = 3.2              # carrot lane_width_estimate init
PARAM_READ_INTERVAL = 100           # frames between Params re-reads


def _finite(value) -> float:
  """float(value) with non-finite / non-numeric collapse to 0.0."""
  try:
    value = float(value)
  except (TypeError, ValueError):
    return 0.0
  return value if np.isfinite(value) else 0.0


def _to_bool(value) -> bool:
  if isinstance(value, bool):
    return value
  return str(value).strip().lower() in ("1", "true", "yes", "on")


def compute_lane_offset(lane_width: float, lane_width_left: float, lane_width_right: float,
                        adjust_offset: float, keep_min_distance: float = KEEP_MIN_DISTANCE_FROM_LANE) -> float:
  """Raw lateral offset (m, positive right) for the current lane geometry.

  - no shift when the feature magnitude is off (adjust_offset <= 0)
  - no shift when both adjacent-lane widths are roomy (> MAX_ADJACENT_WIDTH) or
    both are too tight (< MIN_ADJACENT_WIDTH)  (carrot: the two symmetric cases)
  - shift away from the wider adjacent lane (carrot: left width > right width ->
    positive/right), magnitude ramping with the ego lane width over LANE_WIDTH_RAMP
  - capped by KeepMinDistanceFromLane: the shifted path must keep at least
    keep_min_distance m from the outer lane line on the side it shifts toward
    (lane half width + shift-side adjacent width - shift >= keep_min_distance).
    With the shift-side width unknown (0) only the shared line is counted, which
    suppresses shifting toward an unknown/edge side.
  - hard-capped by ADJUST_OFFSET_LIMIT
  """
  if not (adjust_offset > 0.0):
    return 0.0
  if lane_width_left > MAX_ADJACENT_WIDTH and lane_width_right > MAX_ADJACENT_WIDTH:
    return 0.0  # roomy on both sides
  if lane_width_left < MIN_ADJACENT_WIDTH and lane_width_right < MIN_ADJACENT_WIDTH:
    return 0.0  # too tight on both sides
  if lane_width_left > lane_width_right:
    direction, shift_side_width = 1.0, lane_width_right   # wide adjacent lane on the left -> shift right
  elif lane_width_right > lane_width_left:
    direction, shift_side_width = -1.0, lane_width_left   # wide adjacent lane on the right -> shift left
  else:
    return 0.0  # symmetric adjacent lanes: nothing to avoid

  magnitude = float(np.interp(lane_width, LANE_WIDTH_RAMP, [0.0, adjust_offset]))
  outer_distance = 0.5 * lane_width + max(shift_side_width, 0.0)
  magnitude = min(magnitude, max(0.0, outer_distance - keep_min_distance), ADJUST_OFFSET_LIMIT)
  return direction * magnitude


class LaneOffsetAdjust:
  """Params-gated, smoothed lane-geometry offset consumed by the lane-centering chain."""

  def __init__(self, params=None):
    if params is not None:
      self._params = params
    else:
      try:
        self._params = Params() if Params is not None else None
      except Exception:  # PC host: real Params backend unavailable
        self._params = None
    self.enabled = False
    self.adjust_offset = ADJUST_OFFSET_DEFAULT
    self.keep_min_distance = KEEP_MIN_DISTANCE_FROM_LANE
    self.lane_width_left_filtered = FirstOrderFilter(1.0, 1.0, _DT_MDL)
    self.lane_width_right_filtered = FirstOrderFilter(1.0, 1.0, _DT_MDL)
    self._lane_width_filter = FirstOrderFilter(_LANE_WIDTH_INIT, 3.0, _DT_MDL)
    self.offset_filtered = FirstOrderFilter(0.0, 2.0, _DT_MDL)
    self._frame = 0
    self.read_params()

  def _read_param(self, key: str, default, cast=float):
    """Robust read: unregistered keys (UnknownKeyName) / unset (None) / bad values -> default."""
    if self._params is None:
      return default
    try:
      value = self._params.get(key)
    except Exception:
      return default
    if value is None:
      return default
    try:
      return cast(value)
    except (TypeError, ValueError):
      return default

  def read_params(self) -> None:
    self.enabled = self._read_param("AdjustLaneOffsetEnabled", False, cast=_to_bool)
    self.adjust_offset = self._read_param("AdjustLaneOffset", ADJUST_OFFSET_DEFAULT)
    self.keep_min_distance = self._read_param("KeepMinDistanceFromLane", KEEP_MIN_DISTANCE_FROM_LANE)

  def reset(self) -> None:
    self.lane_width_left_filtered = FirstOrderFilter(1.0, 1.0, _DT_MDL)
    self.lane_width_right_filtered = FirstOrderFilter(1.0, 1.0, _DT_MDL)
    self._lane_width_filter = FirstOrderFilter(_LANE_WIDTH_INIT, 3.0, _DT_MDL)
    self.offset_filtered = FirstOrderFilter(0.0, 2.0, _DT_MDL)

  def _update_lane_width(self, model_v2) -> float:
    """Ego lane width at the model frame origin (carrot lane_width_estimate), filtered.

    Only folds in frames where both current lane lines are confident
    (prob > _LANE_PROB_MIN); otherwise the filtered estimate holds.
    """
    try:
      lines = model_v2.laneLines
      probs = np.asarray(model_v2.laneLineProbs, dtype=float)
      if len(lines) < 3 or probs.size < 3:
        return float(self._lane_width_filter.x)
      if probs[1] < _LANE_PROB_MIN or probs[2] < _LANE_PROB_MIN:
        return float(self._lane_width_filter.x)
      left_y = _finite(np.asarray(lines[1].y, dtype=float)[0])
      right_y = _finite(np.asarray(lines[2].y, dtype=float)[0])
      width = abs(right_y - left_y)
      if 0.0 < width < 6.0:
        self._lane_width_filter.update(width)
    except (AttributeError, IndexError, TypeError, ValueError):
      pass
    return float(self._lane_width_filter.x)

  def update(self, model_v2, v_ego: float, active: bool) -> float:
    """Smoothed lateral offset (m, positive right). 0.0 unless enabled and active.

    Called every lane-centering frame; inactive frames (lane centering gated off,
    lane change in progress, signal pause, driver override) reset the filters so
    re-entry starts from zero, exactly like the surrounding controller.
    """
    self._frame += 1
    if self._frame % PARAM_READ_INTERVAL == 1:
      self.read_params()
    if not self.enabled or not active:
      self.reset()
      return 0.0

    v_ego = _finite(v_ego)
    meta = getattr(model_v2, "meta", None)
    left_width = _finite(getattr(meta, "laneWidthLeft", 0.0))
    right_width = _finite(getattr(meta, "laneWidthRight", 0.0))
    # carrot: only fold in widths that exist; the filtered estimate holds otherwise.
    if left_width > 0.0:
      self.lane_width_left_filtered.update(left_width)
    if right_width > 0.0:
      self.lane_width_right_filtered.update(right_width)

    lane_width = self._update_lane_width(model_v2)
    raw = compute_lane_offset(lane_width, self.lane_width_left_filtered.x,
                              self.lane_width_right_filtered.x, self.adjust_offset,
                              self.keep_min_distance)
    # carrot: ramp the shift in with speed, nothing while nearly stopped.
    raw *= float(np.interp(v_ego * 3.6, [SHIFT_SPEED_MIN_KPH, SHIFT_SPEED_MAX_KPH], [0.0, 1.0]))
    return float(self.offset_filtered.update(raw))
