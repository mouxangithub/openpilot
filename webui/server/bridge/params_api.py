"""Read/write openpilot Params for settings panels."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from webui.server.bridge.model_overlay import OVERLAY_PARAM_KEYS, invalidate_overlay_params_cache
from webui.server.bridge.panel_catalog import PANELS, get_panel, panel_schema

if TYPE_CHECKING:
  from openpilot.common.params import ParamKeyType, Params, UnknownKeyName


def _op_params():
  import sys
  if os.environ.get("WEBUI_DEV_PC") == "1":
    mod = sys.modules.get("openpilot.common.params")
    if mod is not None:
      return mod.Params, mod.ParamKeyType, mod.UnknownKeyName
    from webui.dev.mock_runtime import MockParams, ParamKeyType, UnknownKeyName
    return MockParams, ParamKeyType, UnknownKeyName
  from openpilot.common.params import ParamKeyType, Params, UnknownKeyName
  return Params, ParamKeyType, UnknownKeyName

# Custom panels with no widget params still need these keys in panel snapshots.
_CUSTOM_PANEL_PARAMS: dict[str, list[str]] = {
  "sunnylink": [
    "SunnylinkEnabled",
    "EnableSunnylinkUploader",
    "SunnylinkDongleId",
    "CompletedSunnylinkConsentVersion",
  ],
  "osm": [
    "MapdVersion",
    "OsmLocationName",
    "OsmLocationTitle",
    "OsmStateName",
    "OsmStateTitle",
    "OsmDownloadedDate",
  ],
}

def _param_type_names() -> dict[Any, str]:
  _, ParamKeyType, _ = _op_params()
  return {
    ParamKeyType.STRING: "STRING",
    ParamKeyType.BOOL: "BOOL",
    ParamKeyType.INT: "INT",
    ParamKeyType.FLOAT: "FLOAT",
    ParamKeyType.TIME: "TIME",
    ParamKeyType.JSON: "JSON",
    ParamKeyType.BYTES: "BYTES",
  }


def _params():
  Params, _, _ = _op_params()
  return Params()


def _param_type(p, key: str):
  _, _, UnknownKeyName = _op_params()
  try:
    return p.get_type(key)
  except UnknownKeyName:
    return None


def _param_type_name(p, key: str) -> str | None:
  t = _param_type(p, key)
  if t is None:
    return None
  name = getattr(t, "name", None)
  if name:
    return name
  return _param_type_names().get(t)


def _infer_param_type_from_widget(wtype: str | None) -> str | None:
  if wtype == "bool":
    return "BOOL"
  if wtype in ("option", "int", "choice"):
    return "INT"
  return None


def _default_param_value(ptype: str) -> str:
  return {"BOOL": "0", "INT": "0", "FLOAT": "0"}.get(ptype, "")


def _read_param_value_with_fallback(p, key: str, ptype: str) -> str:
  known = _param_type_name(p, key)
  if known is not None:
    return _read_param_value(p, key, known)
  try:
    raw = p.get(key)
    if raw is not None:
      return _read_param_value(p, key, ptype)
  except Exception:
    pass
  return _default_param_value(ptype)


def _serialize_value(val: Any) -> str:
  if val is None:
    return ""
  if isinstance(val, bytes):
    try:
      return val.decode("utf-8", errors="replace")
    except Exception:
      return val.hex()
  if isinstance(val, bool):
    return "1" if val else "0"
  return str(val)


def _read_param_value(p, key: str, ptype: str | None) -> str:
  if ptype == "BOOL":
    try:
      return "1" if p.get_bool(key) else "0"
    except Exception:
      return "0"
  return _serialize_value(p.get(key))


def get_param(key: str) -> dict[str, Any]:
  try:
    p = _params()
    ptype = _param_type_name(p, key)
    if ptype is None:
      return {"ok": False, "error": f"unknown param: {key}"}
    val = p.get(key)
    locked = False
    try:
      locked = p.get_bool(key + "Lock")
    except Exception as exc:
      _, _, UnknownKeyName = _op_params()
      if not isinstance(exc, UnknownKeyName):
        raise
    return {
      "ok": True,
      "key": key,
      "value": _read_param_value(p, key, ptype),
      "type": ptype,
      "locked": locked,
    }
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def _coerce_write_value(ptype_enum, value: str) -> Any:
  _, ParamKeyType, _ = _op_params()
  if ptype_enum == ParamKeyType.BOOL:
    return value in ("1", "true", "True", True)
  if ptype_enum == ParamKeyType.INT:
    return int(value)
  if ptype_enum == ParamKeyType.FLOAT:
    return float(value)
  if ptype_enum == ParamKeyType.JSON:
    import json
    return json.loads(value) if isinstance(value, str) else value
  return value


def _prebuilt_path() -> str:
  try:
    from openpilot.common.hardware import PC
    from openpilot.common.hardware.hw import Paths
    import os
    return os.path.join(Paths.comma_home(), "prebuilt") if PC else "/data/openpilot/prebuilt"
  except Exception:
    return "/data/openpilot/prebuilt"


def sync_quickboot_param() -> None:
  """Mirror developer.py — keep QuickBootToggle in sync with prebuilt file."""
  try:
    import os
    from openpilot.common.params import Params
    p = Params()
    prebuilt = os.path.exists(_prebuilt_path())
    if prebuilt != p.get_bool("QuickBootToggle"):
      p.put_bool("QuickBootToggle", prebuilt, block=True)
  except Exception:
    pass


def _apply_quickboot_file(enabled: bool) -> None:
  import os
  path = _prebuilt_path()
  if enabled:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Path(path).touch(exist_ok=True)
  elif os.path.exists(path):
    os.remove(path)


def remove_param(key: str) -> dict[str, Any]:
  try:
    p = _params()
    p.remove(key)
    from webui.server.bridge.param_constraints import enforce_param_constraints
    enforce_param_constraints(p)
    return {"ok": True, "key": key}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def put_param(key: str, value: str, *, needs_cycle: bool = False) -> dict[str, Any]:
  try:
    from webui.server.bridge.lite_util import LITE_UNAVAILABLE_PARAMS, is_lite_hw
    if is_lite_hw() and key in LITE_UNAVAILABLE_PARAMS:
      return {"ok": False, "error": f"param unavailable on Lite hardware: {key}"}

    _, ParamKeyType, _ = _op_params()
    p = _params()
    ptype_enum = _param_type(p, key)
    ptype = _param_type_name(p, key)
    if ptype_enum is None or ptype is None:
      return {"ok": False, "error": f"unknown param: {key}"}

    try:
      if p.get_bool(key + "Lock"):
        return {"ok": False, "error": f"param locked: {key}"}
    except Exception as exc:
      _, _, UnknownKeyName = _op_params()
      if not isinstance(exc, UnknownKeyName):
        raise

    if ptype_enum == ParamKeyType.BOOL:
      coerced = _coerce_write_value(ptype_enum, value)
      if key == "QuickBootToggle":
        _apply_quickboot_file(bool(coerced))
      p.put_bool(key, coerced, block=True)
    else:
      p.put(key, _coerce_write_value(ptype_enum, value), block=True)

    if needs_cycle:
      p.put_bool("OnroadCycleRequested", True, block=True)

    if key in OVERLAY_PARAM_KEYS:
      invalidate_overlay_params_cache()

    from webui.server.bridge.param_constraints import enforce_param_constraints
    enforce_param_constraints(p)

    return {"ok": True, "key": key, "value": _read_param_value(p, key, ptype)}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def list_toggle_params() -> dict[str, Any]:
  panel = get_panel("toggles")
  if not panel:
    return {"ok": False, "error": "toggles panel missing", "params": []}
  return panel_values("toggles")


def panel_values(panel_id: str) -> dict[str, Any]:
  if panel_id == "developer":
    sync_quickboot_param()
  panel = get_panel(panel_id)
  if not panel:
    return {"ok": False, "error": f"unknown panel: {panel_id}"}

  p = _params()
  values: dict[str, Any] = {}
  widgets_out: list[dict[str, Any]] = []

  def _ensure_param(key: str) -> None:
    if not key or key in values:
      return
    ptype = _param_type_name(p, key)
    if ptype is not None:
      values[key] = _read_param_value(p, key, ptype)
      return
    try:
      raw = p.get(key)
      if raw is not None:
        values[key] = _serialize_value(raw)
    except Exception:
      pass

  for w in panel.get("widgets", []):
    if w.get("custom") == "webui_update":
      continue
    from webui.server.bridge.lite_util import should_hide_widget
    if should_hide_widget(w):
      continue
    for dep_key in ("visible_if", "advanced_if"):
      dep = w.get(dep_key)
      if isinstance(dep, dict) and dep.get("param"):
        _ensure_param(dep["param"])
    wtype = w.get("type")
    if wtype in ("section", "separator", "html", "action", "subpanel"):
      widgets_out.append({**w, "available": True})
      continue
    if wtype == "custom":
      widgets_out.append({**w, "available": True})
      continue
    if wtype == "dual_button":
      entry = {**w, "available": True}
      for side in ("left", "right"):
        side_w = dict(w.get(side) or {})
        sk = side_w.get("param")
        if sk:
          ptype = _param_type_name(p, sk)
          if ptype is not None:
            val = _read_param_value(p, sk, ptype)
            values[sk] = val
            side_w["value"] = val
            side_w["param_type"] = ptype
        entry[side] = side_w
      widgets_out.append(entry)
      continue

    key = w.get("param")
    if not key:
      widgets_out.append({**w, "available": False})
      continue

    ptype = _param_type_name(p, key)
    if ptype is None:
      ptype = _infer_param_type_from_widget(wtype)
      if ptype is None:
        widgets_out.append({**w, "available": False, "missing": True})
        continue

    val = _read_param_value_with_fallback(p, key, ptype)
    values[key] = val
    locked = False
    try:
      locked = p.get_bool(key + "Lock")
    except Exception as exc:
      _, _, UnknownKeyName = _op_params()
      if not isinstance(exc, UnknownKeyName):
        raise
    widgets_out.append({
      **w,
      "available": True,
      "value": val,
      "param_type": ptype,
      "locked": locked,
    })

  for key in _CUSTOM_PANEL_PARAMS.get(panel_id, []):
    _ensure_param(key)

  return {
    "ok": True,
    "panel": panel_id,
    "title": panel.get("title", panel_id),
    "parent": panel.get("parent"),
    "custom": panel.get("custom"),
    "values": values,
    "widgets": widgets_out,
  }


def batch_get(keys: list[str]) -> dict[str, Any]:
  out: dict[str, Any] = {}
  for key in keys:
    r = get_param(key)
    if r.get("ok"):
      out[key] = r
  return {"ok": True, "params": out}
