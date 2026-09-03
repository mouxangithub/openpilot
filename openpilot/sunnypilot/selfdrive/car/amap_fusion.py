#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from opendbc.car.structs import car


# Amap phone/app lane-line type codes.  These values are a best-effort mapping
# of the integer codes sent by the Amap sender; they may need adjustment once
# the exact wire protocol is known.
class AmapLineType:
  UNKNOWN = 0
  SOLID_WHITE = 1
  DASHED_WHITE = 2
  SOLID_YELLOW = 3
  DOUBLE_YELLOW = 4
  BOTTS_DOTS = 5
  ROAD_EDGE = 6


# Lane-line types that legally/physically block a lane change.
BLOCKING_LINE_TYPES = {
  AmapLineType.SOLID_WHITE,
  AmapLineType.SOLID_YELLOW,
  AmapLineType.DOUBLE_YELLOW,
  AmapLineType.ROAD_EDGE,
}


def _is_line_blocked(line_type: int) -> bool:
  return line_type in BLOCKING_LINE_TYPES


def merge_amap_blindspot(CS: car.CarState, amap_navi) -> None:
  """Merge Amap navigation blind spot data into carState.

  The Amap phone/app sender publishes positive integers for side blind spot
  detections.  We OR those detections with the vehicle's own blind spot
  sensors so that either source can block a lane change.

  Args:
    CS: Mutable carState struct returned by the car interface.
    amap_navi: ``amapNaviSP`` struct (``Custom.AmapNaviSP``).
  """
  if amap_navi.leftBlind:
    CS.leftBlindspot = True
  if amap_navi.rightBlind:
    CS.rightBlindspot = True


def merge_amap_lane_lines(CS_SP, amap_navi) -> None:
  """Merge Amap navigation lane-line data into carStateSP.

  The Amap sender publishes ``lineValid`` together with integer codes for the
  left/right lane-line types.  We copy the raw codes and also derive a
  ``blocked`` flag for each side so downstream planners can treat solid or
  double lines as lane-change barriers.

  Args:
    CS_SP: Mutable carStateSP struct (``Custom.CarStateSP``).
    amap_navi: ``amapNaviSP`` struct (``Custom.AmapNaviSP``).
  """
  CS_SP.amapLineValid = bool(amap_navi.lineValid)
  CS_SP.amapLeftLineType = int(amap_navi.leftLine)
  CS_SP.amapRightLineType = int(amap_navi.rightLine)

  if amap_navi.lineValid:
    CS_SP.amapLeftLineBlocked = _is_line_blocked(int(amap_navi.leftLine))
    CS_SP.amapRightLineBlocked = _is_line_blocked(int(amap_navi.rightLine))
  else:
    CS_SP.amapLeftLineBlocked = False
    CS_SP.amapRightLineBlocked = False
