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

# Arrow codes used by the App's 7706 `navLaneGuide` array (App field list §2.2).
# Only the left/right family matters for lane blocking: a guide that steers you
# left/right means the opposite adjacent lane is not part of the maneuver.
NAV_LANE_GUIDE_LEFT = frozenset(("L", "SL", "LL"))
NAV_LANE_GUIDE_RIGHT = frozenset(("R", "SR", "RL"))


def _parse_nav_lane_guide(raw) -> list[str]:
  """Decode the 7706 ``navLaneGuide`` payload into arrow codes.

  Accepts a JSON array string (``'["L","SL"]'``) or a comma separated string
  (``"L,SL"``). Anything unparseable yields an empty list, which callers treat
  as "no guidance" (i.e. no blocking) rather than "block everything".
  """
  if raw is None:
    return []
  if isinstance(raw, (bytes, bytearray)):
    try:
      raw = raw.decode("utf-8", errors="ignore")
    except Exception:
      return []
  if isinstance(raw, (list, tuple)):
    items = raw
  else:
    text = str(raw).strip()
    if not text:
      return []
    items = None
    if text[0] == "[":
      try:
        import json
        items = json.loads(text)
      except (TypeError, ValueError):
        items = None
    if items is None:
      items = text.split(",")
  out: list[str] = []
  for item in items:
    code = str(item).strip().strip('"').strip("'").upper()
    if code:
      out.append(code)
  return out


def nav_lane_guide_blocks(nav_lane_guide, declared_count: int = 0) -> tuple[bool, bool]:
  """Derive (left_blocked, right_blocked) from the 7706 ``navLaneGuide`` array.

  Semantics: the array lists the directions the guided lanes allow. When the
  guidance is left-only the right adjacent lane is *not* part of the maneuver,
  and vice versa — so we block the non-guided side. This only ever *adds*
  blocking (a more conservative stance); it never clears a block that the 7714
  lane-availability path already set.

  Returns ``(False, False)`` when there is no usable guidance, so an absent or
  malformed array is a no-op.

  ``declared_count`` is the app's ``navLaneGuideCnt``. A mismatch against the
  decoded length means a truncated payload, which is discarded.
  """
  codes = _parse_nav_lane_guide(nav_lane_guide)
  if not codes:
    return False, False
  if declared_count > 0 and declared_count != len(codes):
    # Truncated / inconsistent payload: trust nothing.
    return False, False

  wants_left = any(c in NAV_LANE_GUIDE_LEFT for c in codes)
  wants_right = any(c in NAV_LANE_GUIDE_RIGHT for c in codes)

  # Straight-only guidance constrains neither side.
  if wants_left == wants_right:
    return False, False

  return (not wants_left, not wants_right)


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


def merge_carrot_navi_lanes(CS_SP, carrot_navi, nav_lane_guide=None, nav_lane_guide_cnt: int = 0,
                            use_nav_lane_guide: bool = False) -> None:
  """Merge Carrot navigation lane hints into carStateSP.

  Two Carrot sources feed the SAME pair of flags, so there is only one lane
  blocking decision in the tree:

    * **7714** ``carrotNaviSP.laneCurrent.available`` — per-lane availability.
    * **7706** ``navLaneGuide`` / ``navLaneGuideCnt`` — the guided-lane arrow
      codes (App field list §2.2), folded in only when
      ``CarrotNavLaneGuideBlockEnabled`` is on.

  A blocked adjacent lane means we should not initiate a lane change toward that
  side based on navigation data alone.

  Both sources may only *add* blocking. The 7706 guidance is OR-ed on top of the
  7714 result, so it can never clear a block the 7714 stream reported.

  Args:
    CS_SP: Mutable carStateSP struct (``Custom.CarStateSP``).
    carrot_navi: ``carrotNaviSP`` struct (``Custom.CarrotNaviStateSP``), or None.
    nav_lane_guide: raw 7706 ``navLaneGuide`` payload (JSON array or CSV string).
    nav_lane_guide_cnt: 7706 ``navLaneGuideCnt``; used to reject truncated arrays.
    use_nav_lane_guide: gate for the 7706 contribution (killswitch, default off).
  """
  guide_left = guide_right = False
  if use_nav_lane_guide:
    guide_left, guide_right = nav_lane_guide_blocks(nav_lane_guide, nav_lane_guide_cnt)

  if carrot_navi is None:
    CS_SP.carrotLaneValid = guide_left or guide_right
    CS_SP.carrotLeftLineBlocked = guide_left
    CS_SP.carrotRightLineBlocked = guide_right
    return

  lane = getattr(carrot_navi, "laneCurrent", None)
  meta = getattr(lane, "meta", None)
  present = bool(getattr(meta, "present", False)) if meta is not None else False
  count = int(getattr(lane, "count", 0)) if lane is not None else 0
  current_lane = int(getattr(lane, "currentLane", 0)) if lane is not None else 0

  valid = present and count > 0 and current_lane > 0
  # The guide path has no lane-count data, so it counts as valid on its own when
  # it produced a block; otherwise consumers would ignore the flags entirely.
  CS_SP.carrotLaneValid = valid or guide_left or guide_right

  left_blocked = False
  right_blocked = False
  if valid:
    left_blocked = not _adjacent_lane_available(lane, _LEFT_ADJACENT_OFFSET)
    right_blocked = not _adjacent_lane_available(lane, _RIGHT_ADJACENT_OFFSET)

  CS_SP.carrotLeftLineBlocked = left_blocked or guide_left
  CS_SP.carrotRightLineBlocked = right_blocked or guide_right

