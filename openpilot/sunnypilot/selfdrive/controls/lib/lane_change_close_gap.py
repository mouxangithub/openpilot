"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""

"""Absolute lane-change headway shortening.

Ported from StarPilot ``starpilot/controls/lib/starpilot_following.py``
(``update_lane_change_gap`` / ``lane_change_gap_safe``). While the driver is
signalling out of the lane, hold a shorter follow distance so the car merges
out smoothly and can accelerate through the maneuver instead of braking behind
a lead it is about to leave.

Three guarantees the previous ratio-scaling behaviour lacked:
1. only ever shortens the gap, never lengthens it (``min`` of the base and the
   requested absolute headway, re-applied after the ramp);
2. an occupied blindspot on the lane-change side vetoes the shortening;
3. a braking lead aborts the reduction.

Pure logic over primitives (no cereal imports) so it unit-tests on any host;
the caller maps cereal enums to the ints defined here.
"""

# LaneChangeState ordinals in cereal log.capnp.
LC_STATE_PRE = 1
LC_STATE_STARTING = 2
LC_STATE_FINISHING = 3
LANE_CHANGE_ACTIVE_STATES = (LC_STATE_PRE, LC_STATE_STARTING, LC_STATE_FINISHING)

LANE_CHANGE_MIN_T_FOLLOW = 0.25     # hard floor on the reduced gap (s)
LANE_CHANGE_GAP_RAMP_IN_RATE = 0.6  # s of headway per s, toward the shorter gap
LANE_CHANGE_GAP_RAMP_OUT_RATE = 4.0  # s of headway per s, back to the normal gap
LANE_CHANGE_ABORT_LEAD_BRAKE = 0.8  # lead decel that aborts the reduction (m/s^2)
MIN_LANE_CHANGE_SPEED = 8.94        # do not close the gap below this ego speed (m/s, ~20 mph)

TARGET_SECONDS_DEFAULT = 0.6        # StarPilot's LaneChangeCloseGapSeconds default
TARGET_SECONDS_MIN, TARGET_SECONDS_MAX = 0.25, 1.0

DIRECTION_LEFT, DIRECTION_RIGHT = 1, 2  # LaneChangeDirection ordinals

DT_DEFAULT = 0.05  # planner step; caller passes the real DT_MDL


class LaneChangeCloseGap:
  """Ramps ``t_follow`` toward an absolute lane-change headway, safely."""

  def __init__(self, enabled: bool = False,
               requested_seconds: float = TARGET_SECONDS_DEFAULT,
               dt: float = DT_DEFAULT):
    self._enabled = enabled
    self._requested = float(min(max(requested_seconds, TARGET_SECONDS_MIN), TARGET_SECONDS_MAX))
    self._dt = float(dt)
    self._ramp: float | None = None

  @property
  def enabled(self) -> bool:
    return self._enabled

  def reset(self) -> None:
    self._ramp = None

  def update(self, long_enabled: bool, v_ego: float, standstill: bool,
             lane_change_state: int, direction: int,
             blindspot_left: bool, blindspot_right: bool,
             lead_status: bool, lead_accel: float,
             base_t_follow: float) -> float:
    """Return the t_follow to use this frame; ``base_t_follow`` is never exceeded."""
    if not self._enabled or not long_enabled:
      self.reset()
      return base_t_follow

    target = base_t_follow
    active = lane_change_state in LANE_CHANGE_ACTIVE_STATES
    if active and self._gap_safe(v_ego, standstill, direction,
                                 blindspot_left, blindspot_right,
                                 lead_status, lead_accel):
      # Absolute cap: only apply when it is actually shorter than the normal gap.
      target = min(base_t_follow, self._requested)

    if self._ramp is None:
      self._ramp = base_t_follow

    rate = LANE_CHANGE_GAP_RAMP_IN_RATE if target < self._ramp else LANE_CHANGE_GAP_RAMP_OUT_RATE
    step = rate * self._dt
    self._ramp = float(min(max(target, self._ramp - step), self._ramp + step))

    # Never let the ramp raise the gap above what the rest of the stack asked for.
    return min(base_t_follow, max(self._ramp, LANE_CHANGE_MIN_T_FOLLOW))

  def _gap_safe(self, v_ego: float, standstill: bool, direction: int,
                blindspot_left: bool, blindspot_right: bool,
                lead_status: bool, lead_accel: float) -> bool:
    if standstill or v_ego < MIN_LANE_CHANGE_SPEED:
      return False

    # Do not close the gap toward an occupied blindspot on the lane-change side.
    if direction == DIRECTION_LEFT and blindspot_left:
      return False
    if direction == DIRECTION_RIGHT and blindspot_right:
      return False

    # A braking lead aborts the reduction.
    if lead_status and -min(0.0, float(lead_accel)) >= LANE_CHANGE_ABORT_LEAD_BRAKE:
      return False

    return True
