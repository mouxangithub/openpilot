"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""The settings catalog the app renders: one source, the carrot parameter defaults.

sunnypilot has no separate settings JSON to keep in sync - `carrot.config` already owns
the defaults for the whole carrot tuning surface and `UnifiedParams` owns the values, so
this module describes what is already there instead of restating it. That is what makes
"unified through sunnypilot" more than a comment: adding a key to the carrot defaults is
what makes it appear here, with nothing to edit in the server.

The catalog is an allow-list for a reason. Params also holds the dongle id, SSH keys and
sunnylink credentials; those are not settings and are never listed or returned.
"""
import logging

logger = logging.getLogger("openpilot.carrot.server.settings")

# Grouping is by key prefix, first match wins. It only affects how the app lays the
# list out - it never changes which keys are visible.
GROUP_PREFIXES = (
  ("navi", ("Auto", "Navi", "Road", "Turn", "Fork", "Map", "Tmc")),
  ("longitudinal", ("Cruise", "TFollow", "Lead", "Stop", "Accel", "Decel")),
  ("lateral", ("Steer", "Lat", "Torque", "Lane", "Blind", "Bsd", "Blinker")),
  ("speed", ("Speed", "Vehicle", "Traffic", "Cam", "Curve")),
  ("display", ("Show", "Display", "Ui", "Sound", "Color")),
)

DEFAULT_GROUP = "general"


def _group_for(name: str) -> str:
  for group, prefixes in GROUP_PREFIXES:
    if name.startswith(prefixes):
      return group
  return DEFAULT_GROUP


def _type_of(default) -> str:
  if isinstance(default, bool):
    return "bool"
  if isinstance(default, int):
    return "int"
  if isinstance(default, float):
    return "float"
  if isinstance(default, str):
    return "string"
  return "string"


def _defaults() -> dict:
  from openpilot.sunnypilot.carrot.config import _DEFAULT_NAV_PARAMS

  return dict(_DEFAULT_NAV_PARAMS)


def carrot_defaults() -> dict:
  """Documented defaults, i.e. what `/api/set_default` restores."""
  return _defaults()


def carrot_catalog() -> dict:
  """`{groups, items_by_group, by_name}` - the shape the app renders."""
  defaults = _defaults()
  by_name = {
    name: {"name": name, "default": default, "type": _type_of(default), "group": _group_for(name)}
    for name, default in defaults.items()
  }
  items_by_group: dict = {}
  for name in sorted(by_name):
    items_by_group.setdefault(by_name[name]["group"], []).append(by_name[name])
  groups = [
    {"name": group, "label": group, "count": len(items)}
    for group, items in sorted(items_by_group.items())
  ]
  return {"groups": groups, "items_by_group": items_by_group, "by_name": by_name, "count": len(by_name)}


def carrot_values(names=None) -> dict:
  """Current values via `UnifiedParams`, so the app and the daemons read the same store."""
  from openpilot.sunnypilot.carrot.config import UnifiedParams

  defaults = _defaults()
  wanted = [name for name in (names if names is not None else sorted(defaults)) if name in defaults]
  params = UnifiedParams()
  values = {}
  for name in wanted:
    default = defaults[name]
    try:
      value = params.get(name, default)
    except Exception as exc:
      logger.warning("carrot_server: cannot read %s: %s", name, exc)
      value = default
    values[name] = _coerce(value, default)
  return values


def _coerce(value, default):
  """Params hands back strings for JSON-backed keys; the app wants a typed value."""
  if isinstance(default, bool):
    try:
      return bool(int(value))
    except (TypeError, ValueError):
      return bool(value)
  if isinstance(default, int) and not isinstance(default, bool):
    try:
      return int(value)
    except (TypeError, ValueError):
      return default
  if isinstance(default, float):
    try:
      return float(value)
    except (TypeError, ValueError):
      return default
  if isinstance(default, str):
    if isinstance(value, bytes):
      return value.decode("utf-8", "replace")
    return str(value) if value is not None else ""
  return value
