"""
Pure layout decisions for the on-road speed-limit source drawer.

Ported verbatim from StarPilot ``source_bubble_layout.py`` (no rendering, no
messaging - only geometry and formatting helpers shared by the drawer).
"""

import math
from collections.abc import Callable, Iterable, Mapping


SOURCE_DISPLAY_ORDER = ("Dashboard", "Map Data", "Vision", "Upcoming")
SOURCE_PRIORITY_NAMES = frozenset(("Dashboard", "Map Data", "Vision"))


def enabled_source_titles(
  primary_priority: str,
  secondary_priority: str,
  *,
  vision_enabled: bool,
  dashboard_available: bool = True,
) -> tuple[str, ...]:
  """Return source rows that are eligible under the current SLC settings.

  ``Highest`` and ``Lowest`` are aggregate priority modes. They consider the
  two non-vision controller inputs directly; Vision is only a controller input
  when it is explicitly selected in one of the priority slots. (StarPilot's
  Mapbox filler has no sunnypilot equivalent - the resolver's Source enum only
  knows car/map - so the Mapbox row is dropped in this port.)
  """
  if primary_priority in ("Highest", "Lowest"):
    enabled = {"Dashboard", "Map Data"}
  else:
    enabled = {
      source
      for source in (primary_priority, secondary_priority)
      if source in SOURCE_PRIORITY_NAMES
    }

  if not dashboard_available:
    enabled.discard("Dashboard")
  if vision_enabled:
    enabled.add("Vision")

  if "Map Data" in enabled:
    enabled.add("Upcoming")

  return tuple(source for source in SOURCE_DISPLAY_ORDER if source in enabled)


def visible_source_rows(
  source_defs: Iterable[tuple[str, str, str, str]],
  values: Mapping[str, float],
  active_source: str,
  enabled_sources: Iterable[str],
  active_only: bool = True,
) -> list[tuple[str, str, float, bool]]:
  """Return enabled source rows that possess a valid positive speed reading."""
  enabled = set(enabled_sources)
  rows = []
  for title, _abbrev, value_key, panel_label in source_defs:
    if title not in enabled:
      continue
    value = values[value_key]
    has_reading = math.isfinite(value) and value > 0 and round(value) > 0
    if not has_reading:
      continue
    rows.append((
      panel_label,
      value,
      active_source == title,
    ))
  return rows


def fit_source_label(
  full_label: str,
  compact_label: str,
  max_width: float,
  measure_width: Callable[[str], float],
) -> str:
  """Choose the longest useful label that leaves room for the value column."""
  for label in (full_label, compact_label):
    if measure_width(label) <= max_width:
      return label

  ellipsis = "…"
  candidate = compact_label or full_label
  while candidate and measure_width(candidate + ellipsis) > max_width:
    candidate = candidate[:-1]
  return f"{candidate}{ellipsis}" if candidate else ellipsis


def source_value_text(value: float) -> str:
  """Format a source speed, keeping missing and non-finite values explicit."""
  if not math.isfinite(value) or value <= 0:
    return "–"
  rounded = int(round(value))
  return "–" if rounded <= 0 else str(rounded)
