"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""

"""Lane-change merge assist: brake floor + accel bias while merging out.

Ported from StarPilot ``longitudinal_planner.py::get_lane_change_merge_accel_floor``
(+ the ``LC_MERGE_*`` constants). While the car merges around a lead it is
about to leave, a hard brake for that lead is wasted comfort: this module
returns a floor acceleration the planner applies as ``max(output_a_target,
floor)`` for the merge, and — when there is ample time-to-collision and
cruise headroom — a mild acceleration bias so the merge completes promptly.

Guarantees:
1. never active while stopped, braking, below the minimum lane-change speed,
   outside the active lane-change states, or with an occupied blindspot on
   the merge side;
2. a close lead (small gap or short time-to-reach) keeps full braking
   authority;
3. the accel bias is capped by the remaining cruise headroom, so it can
   never push the car past its set speed.

Pure logic over primitives (no cereal imports) so it unit-tests on any host;
the caller maps cereal enums to the ints defined in ``lane_change_close_gap``.
"""

import math

from openpilot.sunnypilot.selfdrive.controls.lib.lane_change_close_gap import (
  DIRECTION_LEFT,
  DIRECTION_RIGHT,
  LANE_CHANGE_ACTIVE_STATES,
  MIN_LANE_CHANGE_SPEED,
)

# StarPilot LC_MERGE_* constants (verbatim).
LC_MERGE_CLOSING_MIN = 0.5    # m/s; below this closing speed TTC is treated as infinite
LC_MERGE_TTC_MIN = 4.0        # s; a lead reachable sooner keeps full braking authority
LC_MERGE_MIN_DIST = 30.0      # m; a closer lead keeps full braking authority
LC_MERGE_BRAKE_FLOOR = -0.4   # m/s^2; brake floor while merging out
LC_MERGE_TTC_ACCEL = 6.0      # s; TTC above which the accel bias may engage
LC_MERGE_ACCEL_MIN_DIST = 30.0  # m; lead distance required for the accel bias
LC_MERGE_HEADROOM_MIN = 2.0   # m/s; cruise headroom required for the accel bias
LC_MERGE_ACCEL_BIAS = 0.55    # m/s^2; accel bias ceiling while merging out


def get_lane_change_merge_accel_floor(v_ego: float, standstill: bool, brake_pressed: bool,
                                      blindspot_left: bool, blindspot_right: bool,
                                      lane_change_state: int, direction: int,
                                      lead_status: bool, lead_d_rel: float, lead_v_lead: float,
                                      allow_throttle: bool, v_cruise: float,
                                      action_t: float, dt: float) -> float | None:
  """Floor acceleration (m/s^2) to apply as ``max(a_target, floor)`` while
  merging out, or ``None`` when the planner must keep full authority."""
  if standstill or brake_pressed or v_ego < MIN_LANE_CHANGE_SPEED:
    return None
  if lane_change_state not in LANE_CHANGE_ACTIVE_STATES:
    return None
  if (direction == DIRECTION_LEFT and blindspot_left) or \
     (direction == DIRECTION_RIGHT and blindspot_right):
    return None

  # Only intervene when there is a lead we are merging around; leave
  # curve/open-road braking alone.
  if not lead_status:
    return None

  d_rel = float(lead_d_rel)
  closing = v_ego - float(lead_v_lead)
  ttc = d_rel / closing if closing > LC_MERGE_CLOSING_MIN else float('inf')
  # A close lead (small gap or short time-to-reach) keeps full braking authority.
  if ttc < LC_MERGE_TTC_MIN or d_rel < LC_MERGE_MIN_DIST:
    return None

  floor = LC_MERGE_BRAKE_FLOOR
  if (allow_throttle and ttc >= LC_MERGE_TTC_ACCEL and d_rel >= LC_MERGE_ACCEL_MIN_DIST and
      math.isfinite(v_cruise) and (v_cruise - v_ego) >= LC_MERGE_HEADROOM_MIN):
    cruise_cap = max(0.0, (v_cruise - v_ego) / max(action_t, dt))
    floor = min(LC_MERGE_ACCEL_BIAS, cruise_cap)
  return floor
