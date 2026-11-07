"""Adjacent-lane width estimation, ported from CarrotPilot (cp).

Sources (cp):
  selfdrive/controls/lib/desire_lib/lane_math.py::calculate_lane_width
  selfdrive/controls/lib/desire_lib/side_state.py::update_lane_geometry (1 s running mean)

Width of the lane left/right of the ego lane, measured 1.0 s ahead of the ego
frame, clamped by the distance to the standard road edge, then smoothed with a
1 s running mean at modeld rate. modeld fills ModelDataV2.meta.laneWidthLeft /
laneWidthRight from these estimates and the xiaoge BSD gate consumes them
(sunnypilot/carrot/xiaoge/v_asm_server.py::VASM_MIN_LANE_WIDTH_METERS).
"""
from collections import deque

import numpy as np

from openpilot.selfdrive.modeld.constants import ModelConstants

# cp: deque(maxlen=int(1.0 / DT_MDL)) - one second of modeld frames at DT_MDL = 0.05.
# Hardcoded instead of importing realtime to keep this module dependency-light.
SMOOTHING_WINDOW = 20
LOOKAHEAD_S = 1.0
OUTER_LINE_PROB_MIN = 0.5


def _interp_y(lane, t: float) -> float:
  return float(np.interp(t, ModelConstants.T_IDXS, lane.y))


def calculate_lane_width(lane_outer, lane_current, road_edge) -> float:
  """Raw (unsmoothed) adjacent-lane width at LOOKAHEAD_S, exactly as cp's
  calculate_lane_width: min of the gap to the outer lane line and the gap to
  the road edge. Validity of the outer line is reported separately."""
  current_y = _interp_y(lane_current, LOOKAHEAD_S)
  outer_y = _interp_y(lane_outer, LOOKAHEAD_S)
  distance_to_lane = abs(current_y - outer_y)
  distance_to_road_edge = abs(current_y - _interp_y(road_edge, LOOKAHEAD_S))
  return min(distance_to_lane, distance_to_road_edge)


def outer_line_valid(lane_outer_prob: float) -> bool:
  return float(lane_outer_prob) > OUTER_LINE_PROB_MIN


class LaneWidthEstimator:
  """1 s running mean over the raw width, mirroring cp's SideState queue."""

  def __init__(self):
    self._queue: deque[float] = deque(maxlen=SMOOTHING_WINDOW)

  def update(self, lane_outer, lane_outer_prob: float, lane_current, road_edge) -> float:
    width = calculate_lane_width(lane_outer, lane_current, road_edge)
    self._queue.append(width)
    return sum(self._queue) / len(self._queue)
