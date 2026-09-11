#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from opendbc.car.structs import car


# Index offsets relative to the 1-based currentLane index reported by the
# phone app.  laneCurrent.available is a 0-based List(Int16); a positive value
# means the lane at that index is drivable.
_LEFT_ADJACENT_OFFSET = -1
_RIGHT_ADJACENT_OFFSET = 1


def _adjacent_lane_available(lane, offset: int) -> bool:
  """Return True if the adjacent lane (relative to currentLane) is available.

  The semantics match CarrotPilot's HUD renderer:
    * currentLane is 1-based.
    * available is a 0-based List(Int16).
    * available[index] > 0 means that lane index is drivable.

  If the message is malformed or the adjacent index is out of range, we
  conservatively report False (treat it as blocked).
  """
  if lane is None:
    return False

  count = int(getattr(lane, "count", 0))
  current_lane = int(getattr(lane, "currentLane", 0))
  available = getattr(lane, "available", None)

  if count <= 0 or current_lane <= 0 or available is None:
    return False

  adjacent_index = current_lane - 1 + offset
  if adjacent_index < 0 or adjacent_index >= count:
    return False
  if adjacent_index >= len(available):
    return False

  return int(available[adjacent_index]) > 0


def merge_carrot_navi_lanes(CS_SP, carrot_navi) -> None:
  """Merge Carrot 7714 lane-availability hints into carStateSP.

  Derives left/right lane-change block flags from laneCurrent.available.  A
  blocked adjacent lane means we should not initiate a lane change toward that
  side based on navigation data alone.

  Args:
    CS_SP: Mutable carStateSP struct (``Custom.CarStateSP``).
    carrot_navi: ``carrotNaviSP`` struct (``Custom.CarrotNaviStateSP``).
  """
  if carrot_navi is None:
    CS_SP.carrotLaneValid = False
    CS_SP.carrotLeftLineBlocked = False
    CS_SP.carrotRightLineBlocked = False
    return

  lane = getattr(carrot_navi, "laneCurrent", None)
  meta = getattr(lane, "meta", None)
  present = bool(getattr(meta, "present", False)) if meta is not None else False
  count = int(getattr(lane, "count", 0)) if lane is not None else 0
  current_lane = int(getattr(lane, "currentLane", 0)) if lane is not None else 0

  valid = present and count > 0 and current_lane > 0
  CS_SP.carrotLaneValid = valid

  if valid:
    left_available = _adjacent_lane_available(lane, _LEFT_ADJACENT_OFFSET)
    right_available = _adjacent_lane_available(lane, _RIGHT_ADJACENT_OFFSET)
    CS_SP.carrotLeftLineBlocked = not left_available
    CS_SP.carrotRightLineBlocked = not right_available
  else:
    CS_SP.carrotLeftLineBlocked = False
    CS_SP.carrotRightLineBlocked = False

