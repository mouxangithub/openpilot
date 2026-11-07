"""Full settings backup / restore — a web-UI extra beyond BIG UI.

Snapshot scope: every param declared in the settings catalogue (main panels +
subpanels + brand widgets), which is exactly the surface the web UI can edit.
Values are stored with their declared param type so restore can coerce back.

- GET  /api/opui/params/backup          -> {ok, count, snapshot}
- POST /api/opui/params/backup/restore  -> body {snapshot}; offroad only.
  Skips unknown/locked/unavailable keys and reports them instead of failing.
"""

from __future__ import annotations

import time
from typing import Any


def _catalog_param_keys() -> set[str]:
  from webui.server.bridge.panel_catalog import PANELS, SUBPANELS, panel_param_keys

  keys: set[str] = set()
  for panel in PANELS:
    keys.update(panel_param_keys(panel["id"]))
  for sub_id in SUBPANELS:
    keys.update(panel_param_keys(sub_id))
  try:
    from webui.server.bridge.vehicle_brand_catalog import BRAND_WIDGETS
    for widgets in BRAND_WIDGETS.values():
      keys.update(w["param"] for w in widgets if w.get("param"))
  except Exception:
    pass
  return keys


def backup_params() -> dict[str, Any]:
  try:
    from openpilot.common.params import Params
    from webui.server.bridge.params_api import _param_type_name, _serialize_value

    p = Params()
    snapshot: dict[str, Any] = {}
    for key in sorted(_catalog_param_keys()):
      ptype = _param_type_name(p, key)
      if ptype is None:
        continue
      try:
        raw = p.get(key)
      except Exception:
        continue
      if raw is None:
        continue
      snapshot[key] = {"type": ptype, "value": _serialize_value(raw)}
    return {
      "ok": True,
      "count": len(snapshot),
      "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
      "snapshot": snapshot,
    }
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def restore_params(snapshot: Any) -> dict[str, Any]:
  try:
    from webui.server.bridge.lite_util import is_lite_hw
    if is_lite_hw():
      return {"ok": False, "error": "restore unavailable on Lite hardware"}
  except Exception:
    pass

  try:
    from webui.server.bridge.offroad_guard import require_offroad
    blocked = require_offroad()
    if blocked is not None:
      return {"ok": False, "error": blocked.get("error", "restore requires the device to be offroad")}
  except Exception:
    pass

  if not isinstance(snapshot, dict) or not snapshot:
    return {"ok": False, "error": "empty or malformed snapshot"}

  from openpilot.common.params import Params
  from webui.server.bridge.params_api import _op_params, _coerce_write_value, put_param

  _, ParamKeyType, UnknownKeyName = _op_params()
  p = Params()

  restored: list[str] = []
  skipped: dict[str, str] = {}
  for key, entry in snapshot.items():
    if not isinstance(entry, dict) or "value" not in entry:
      skipped[key] = "malformed entry"
      continue
    try:
      ptype_enum = _op_params_type(p, key)
      if ptype_enum is None:
        skipped[key] = "unknown param"
        continue
      try:
        if p.get_bool(key + "Lock"):
          skipped[key] = "locked"
          continue
      except UnknownKeyName:
        pass
      coerced = _coerce_write_value(ptype_enum, str(entry.get("value", "")))
      if ptype_enum == ParamKeyType.BOOL:
        p.put_bool(key, coerced, block=True)
      else:
        p.put(key, coerced, block=True)
      restored.append(key)
    except Exception as exc:
      skipped[key] = str(exc)

  try:
    from webui.server.bridge.param_constraints import enforce_param_constraints
    enforce_param_constraints(p)
  except Exception:
    pass

  return {"ok": True, "restored": len(restored), "skipped": skipped}


def _op_params_type(p, key: str):
  try:
    from webui.server.bridge.params_api import _param_type
    return _param_type(p, key)
  except Exception:
    return None
