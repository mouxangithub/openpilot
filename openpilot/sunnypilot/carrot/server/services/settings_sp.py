"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""The carrot tuning surface's defaults and values, as the settings server reads them.

`carrot.config` owns the defaults for the whole carrot tuning surface and `UnifiedParams`
owns the values, so this module describes what is already there instead of restating it.
Adding a key to the carrot defaults is what makes it appear here, with nothing to edit in
the server.

It also owns the one place the build-time tuning metadata is read (`_declared_metadata`)
and the one place it is stamped onto a catalog (`attach_tuning_metadata`), which is what
`services.settings.get_settings_cached` calls. There used to be a second, parallel
`carrot_catalog()` in this module that rendered its own view of the same data; it had no
production reader and drifted from the served one, so it is gone.

These are allow-lists for a reason. Params also holds the dongle id, SSH keys and
sunnylink credentials; those are not settings and are never listed or returned.
"""
import logging

logger = logging.getLogger("openpilot.carrot.server.settings")


def _defaults() -> dict:
  from openpilot.sunnypilot.carrot.config import _DEFAULT_NAV_PARAMS

  return dict(_DEFAULT_NAV_PARAMS)


def carrot_defaults() -> dict:
  """Documented defaults, i.e. what `/api/set_default` restores."""
  return _defaults()


def _metadata_params():
  """A raw Params handle for the metadata reads, or None when unavailable.

  Raw rather than ``UnifiedParams``: the tuning metadata lives in the compiled
  key table, not in any of the JSON tables ``UnifiedParams`` merges, so the
  wrapper would only add a cache between the question and the answer.
  """
  try:
    from openpilot.common.params import Params
    return Params()
  except Exception:
    return None


def _declared_metadata(names, params=None) -> tuple[dict[str, int], dict[str, int]]:
  """`(tuning_level, settings_tier)` per key, as declared in params_keys.h.

  This is the consumer that keeps the metadata from being write-only: the app
  groups and orders its knobs from these two numbers instead of from a list
  somebody has to remember to update. A device whose libparams_c.so predates
  the metadata reports nothing, and every key falls back to "not a knob,
  advanced" - the pre-metadata behaviour.

  ``params`` is injectable so the fallbacks can be tested without a store.
  """
  levels: dict[str, int] = {}
  tiers: dict[str, int] = {}
  if params is None:
    params = _metadata_params()
  if params is None:
    return levels, tiers

  from openpilot.sunnypilot.common.param_read import read_settings_tier, read_tuning_level

  for name in names:
    level = read_tuning_level(params, name, 0)
    if level:
      levels[name] = level
    tiers[name] = read_settings_tier(params, name, 1)
  return levels, tiers


def attach_tuning_metadata(by_name: dict, params=None) -> dict:
  """Stamp `tuningLevel` / `settingsTier` onto every entry of a catalog `by_name` map.

  This is what turns the declarations in `common/params_keys.h` from write-only metadata
  into something a renderer can act on: the panel asks each entry how deep its knob sits
  and which settings tier owns it, instead of carrying a second, hand-maintained table
  that has to be kept in step with the C++ header. Entries are mutated in place - the
  catalog hands the same dict object out through `data["params"]`, `groups` and
  `by_name`, and stamping one copy keeps them from disagreeing.

  Runs once per catalog load (it is behind the mtime cache in `services.settings`), so
  the cost is one C++ call per key per reload. A store that predates the metadata answers
  with the defaults - "not a knob, advanced" - which is exactly the pre-metadata
  behaviour, so this is safe to land before the device's `libparams_c.so` is rebuilt.
  """
  if not by_name:
    return by_name
  levels, tiers = _declared_metadata(list(by_name), params)
  for name, entry in by_name.items():
    if isinstance(entry, dict):
      entry["tuningLevel"] = levels.get(name, 0)
      entry["settingsTier"] = tiers.get(name, 1)
  return by_name


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
