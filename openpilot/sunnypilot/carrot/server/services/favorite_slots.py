"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Executable favorite slots: a stored key becomes a one-tap action.

Design notes (kept deliberately narrow):

- Only slots assigned in ``setting_favorites.json`` are executable, and writes
  go through ``services.params.set_param_value`` - so the internal-session
  blocklist, the onroad blocklist and typed writes are inherited, not
  reimplemented here. This module never touches Params directly.
- Value semantics follow the setting's declared shape: a 0/1 setting toggles,
  a settings-with-options entry cycles to the next option (wrap-around), and a
  free numeric/string setting requires an explicit value from the caller.
- All dependencies (catalog, current-value reader, writer) are module-level
  functions so tests can inject fakes without Params, the settings cache or a
  running manager.
"""

from typing import Any

from .params import clamp_numeric, get_param_value, infer_type_from_setting, set_param_value
from .setting_favorites import read_setting_favorites

SlotKind = str  # "toggle" | "cycle" | "value" | "unsupported"


class FavoriteSlotError(Exception):
  """Apply/describe refusal with a machine-readable code for the client."""

  def __init__(self, code: str, message: str):
    super().__init__(message)
    self.code = code
    self.message = message


# --------------------------- dependency seams --------------------------------


def _catalog_by_name():
  # Lazy: services.settings pulls the vehicle-tune import chain (fcntl-bound at
  # module scope) that must not run on PC or at module-import time; the real
  # server resolves it at request time on device.
  from .settings import get_settings_cached
  try:
    return get_settings_cached()[2]
  except Exception:
    return {}


def _read_current(key: str, entry: dict[str, Any]) -> Any:
  return get_param_value(key, entry.get("default"))


# ------------------------------- helpers -------------------------------------


def _assigned_keys() -> list[str]:
  slots = read_setting_favorites().get("slots") or []
  return [str(slot.get("key") or "") for slot in slots if isinstance(slot, dict)]


def _option_labels(entry: dict[str, Any]) -> list[str]:
  options = entry.get("options")
  if not isinstance(options, dict):
    return []
  for locale in ("zh", "en"):
    value = options.get(locale)
    if isinstance(value, list) and value:
      return [str(item) for item in value]
  for value in options.values():
    if isinstance(value, list) and value:
      return [str(item) for item in value]
  return []


def slot_kind(entry: dict[str, Any] | None) -> SlotKind:
  if not entry:
    return "unsupported"
  if _option_labels(entry):
    return "cycle"
  kind = infer_type_from_setting(entry)
  if kind == "bool":
    return "toggle"
  if kind in ("int", "float", "string"):
    return "value"
  return "unsupported"


def _slot_entry(slot: int | None, key: str | None) -> tuple[int, str, dict[str, Any] | None]:
  keys = _assigned_keys()
  if key is not None:
    key = key.strip()
    if key not in keys:
      raise FavoriteSlotError("not_a_slot", f"{key} is not assigned to a favorite slot")
    index = keys.index(key)
  elif slot is not None:
    if not isinstance(slot, int) or isinstance(slot, bool) or not (0 <= slot < len(keys)):
      raise FavoriteSlotError("bad_slot", f"slot index must be 0..{len(keys) - 1}")
    index = slot
  else:
    raise FavoriteSlotError("bad_request", "provide either 'slot' or 'key'")
  name = keys[index]
  if not name:
    raise FavoriteSlotError("empty_slot", "this favorite slot is empty")
  return index, name, _catalog_by_name().get(name)


# -------------------------------- API ----------------------------------------


def describe_favorite_slots() -> list[dict[str, Any]]:
  out: list[dict[str, Any]] = []
  for index, key in enumerate(_assigned_keys()):
    if not key:
      out.append({"slot": index, "key": "", "kind": "empty"})
      continue
    entry = _catalog_by_name().get(key)
    if entry is None:
      out.append({"slot": index, "key": key, "kind": "stale",
                  "note": "setting no longer exists in the catalog"})
      continue
    kind = slot_kind(entry)
    item: dict[str, Any] = {
      "slot": index,
      "key": key,
      "kind": kind,
      "title": entry.get("ctitle") or entry.get("etitle") or entry.get("title") or key,
    }
    if kind == "toggle":
      item["value"] = bool(_read_current(key, entry))
    elif kind == "cycle":
      labels = _option_labels(entry)
      item["options"] = labels
      try:
        item["value"] = int(_read_current(key, entry))
      except (TypeError, ValueError):
        item["value"] = entry.get("default", 0)
    elif kind == "value":
      item["min"] = entry.get("min")
      item["max"] = entry.get("max")
      item["value"] = _read_current(key, entry)
    out.append(item)
  return out


def apply_favorite_slot(slot: int | None = None, key: str | None = None,
                        value: Any = None, *, writer=set_param_value) -> dict[str, Any]:
  """Execute one slot. ``writer`` is injectable for tests; production writes
  go through ``set_param_value`` and inherit all of its guards."""
  index, name, entry = _slot_entry(slot, key)
  kind = slot_kind(entry)
  if kind == "unsupported":
    raise FavoriteSlotError("unsupported", f"{name} cannot be executed as a slot action")

  previous = _read_current(name, entry)

  if kind == "toggle":
    # explicit value = set to that state; no value = flip the current one
    new_value = bool(value) if value is not None else not bool(previous)
  elif kind == "cycle":
    labels = _option_labels(entry)
    try:
      current_index = int(previous)
    except (TypeError, ValueError):
      current_index = int(entry.get("default", 0) or 0)
    if value is not None:
      new_value = int(value)
    else:
      new_value = (current_index + 1) % len(labels)
    if not (0 <= new_value < len(labels)):
      raise FavoriteSlotError("out_of_range", f"{name} option index must be 0..{len(labels) - 1}")
  else:  # "value"
    if value is None:
      raise FavoriteSlotError("value_required", f"{name} requires an explicit 'value'")
    new_value = value
    if infer_type_from_setting(entry) in ("int", "float") and entry.get("min") is not None and entry.get("max") is not None:
      new_value = clamp_numeric(float(value), entry)

  try:
    writer(name, new_value)
  except ValueError as exc:
    # set_param_value raises ValueError for the onroad blocklist, internal
    # session params and (via put_typed) type failures - surface them all.
    raise FavoriteSlotError("rejected", str(exc)) from exc

  return {"slot": index, "key": name, "kind": kind, "previous": previous, "value": new_value}
