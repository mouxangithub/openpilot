"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Tiered speed-limit offsets.

A single global offset is a blunt instrument: the same value that feels right
on a country road (a limit posted at 60 km/h) is wrong in a city (posted at
30 km/h) and on a motorway (posted at 120 km/h). The tiered form lets the
driver give a different offset per limit band, so the car can sit a little
over the limit on a fast road and a little under it in town.

The bands are the posted limit, not the current speed, and each band covers
everything from its own value up to the next one. The top band is open-ended.

Pure logic with no openpilot imports, so it stays importable and unit
testable on a PC host.
"""

# The upper edge of each band, in km/h. A posted limit L uses the offset of
# the first band whose edge is >= L. The last band has no edge, so it catches
# everything above the second-to-last edge.
TIER_EDGES_KPH = (30, 50, 60, 80, 100, 120)

# The same bands in mph. The bands are a property of the road, not of the
# unit, but the edges have to be read in the unit the user drives in: a
# 60 km/h sign is 37 mph, and 37 has to land in the band whose lower edge is
# 35 mph - the same road, the same band. Choosing the table by the unit is
# what keeps the band the user sees in the UI the band the resolver uses.
TIER_EDGES_MPH = (25, 35, 45, 55, 65, 75)

# The lowest band: a posted limit of 30 km/h or less.
TIER_LOWEST = 0
# The highest band: everything above TIER_EDGES_KPH[-1].
TIER_HIGHEST = len(TIER_EDGES_KPH)

# How many tiers exist: the lowest band, one per edge, and the highest.
TIER_COUNT = TIER_LOWEST + len(TIER_EDGES_KPH) + 1

# The parameter key suffix for each tier's offset value.
TIER_KEY_SUFFIXES = tuple(f"SpeedLimitTierOffset{i}" for i in range(TIER_COUNT))


# A posted limit that lands exactly on a band edge must not fall into the
# next band because of floating point noise: 60 km/h converts to
# 60.00000000000001 km/h, which would otherwise land in the 60-80 band
# instead of the 50-60 one. The tolerance keeps a limit on an edge in the
# band it names.
TIER_EDGE_TOLERANCE = 1e-6


def tier_edges(is_metric: bool) -> tuple[int, ...]:
  """The band edges in the unit the user drives in."""
  return TIER_EDGES_KPH if is_metric else TIER_EDGES_MPH


def tier_for_limit(limit_kph: float, is_metric: bool = True) -> int:
  """The tier a posted limit belongs to.

    The limit is matched against the band edges, so a limit exactly on an edge
    lands in that band (a 60 km/h sign is the 60 band, not the 80 one).
    """
  edges = tier_edges(is_metric)
  if limit_kph <= edges[0] + TIER_EDGE_TOLERANCE:
    return TIER_LOWEST
  # The first edge is already the upper bound of the lowest band, so the
  # remaining edges index the bands above it: an edge at index i opens the
  # band whose lower bound is that edge.
  for index, edge in enumerate(edges[1:], start=1):
    if limit_kph <= edge + TIER_EDGE_TOLERANCE:
      return index
  return TIER_HIGHEST


def tier_range_kph(tier: int, is_metric: bool = True) -> tuple[float, float]:
  """The (low, high) posted-limit range a tier covers, for the UI.

    The highest tier has no upper edge, so its high is reported as None.
    """
  edges = tier_edges(is_metric)
  if tier <= TIER_LOWEST:
    return (0.0, float(edges[0]))
  if tier >= TIER_HIGHEST:
    return (float(edges[-1]), None)
  return (float(edges[tier - 1]), float(edges[tier]))


def tier_label(tier: int, is_metric: bool = True) -> str:
  """A short label for the tier, used by the settings UI."""
  low, high = tier_range_kph(tier, is_metric)
  if high is None:
    return f">{int(low)}+"
  if low <= 0:
    return f"≤{int(high)}"
  return f"{int(low)}-{int(high)}"


def tiered_offset_ms(speed_limit_ms: float, tier_offsets: list[float], is_metric: bool) -> float:
  """The offset for the band the posted limit falls into, in m/s.

  The band comes from the posted limit, not the current speed: a 60 km/h
  sign is the 60 band whether the car is doing 40 or 70 in it.

  The tier values are in the unit the user chose (km/h or mph), the same
  convention the single fixed offset uses. A missing limit, or a tier index
  outside the table, means no offset.

  Pure logic, no openpilot imports, so it stays importable and unit
  testable on a PC host.
  """
  if speed_limit_ms <= 0. or not tier_offsets:
    return 0.0

  from openpilot.common.constants import CV

  limit_in_unit = speed_limit_ms * (CV.MS_TO_KPH if is_metric else CV.MS_TO_MPH)
  tier = tier_for_limit(limit_in_unit, is_metric)
  if tier < 0 or tier >= len(tier_offsets):
    return 0.0

  unit_factor = CV.KPH_TO_MS if is_metric else CV.MPH_TO_MS
  return float(tier_offsets[tier] * unit_factor)
