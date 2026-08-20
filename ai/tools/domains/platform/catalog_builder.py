"""Merge static params_catalog.json with fork UI discovery (openpilot + optional dp_*)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from ai.common.sp_param_aliases import DP_TO_SP_PARAM_ALIASES
from ai.system.paths import find_repo_file, source_path

_OP_ROOT = Path(__file__).resolve().parents[2]
_STATIC = Path(__file__).resolve().parent.parent / "skills" / "params_catalog.json"
_SP_UI_ROOTS = (
  source_path("selfdrive", "ui", "sunnypilot"),
  source_path("system", "ui", "sunnypilot"),
)
_PARAMS_KEYS_H = find_repo_file("openpilot/common/params_keys.h", "common/params_keys.h") or source_path("common", "params_keys.h")

_FORBIDDEN_KEYS = frozenset({
  "AdbEnabled", "SshEnabled", "SecOCKey", "AlphaLongitudinalEnabled",
  "JoystickDebugMode", "LongitudinalManeuverMode",
})
_REDACTED_KEYS = frozenset({
  "ai_api_key", "DongleId", "GithubSshKeys", "ApiCache_Device",
})

_SP_SECTION_HINTS: dict[str, str] = {
  "Mads": "MADS", "Lagd": "Lateral", "LaneTurn": "Lateral", "Blinker": "Lateral",
  "Torque": "Lateral", "LiveTorque": "Lateral", "NeuralNetwork": "Lateral",
  "EnforceTorque": "Lateral", "AutoLaneChange": "Lateral", "CameraOffset": "Models",
  "Planplus": "Models",
  "SpeedLimit": "Longitudinal", "SmartCruise": "Longitudinal", "DynamicExperimental": "Longitudinal",
  "CustomAcc": "Longitudinal", "IntelligentCruise": "Longitudinal", "PlanplusControl": "Models",
  "Toyota": "Toyota", "Subaru": "Subaru", "Hyundai": "Hyundai", "Tesla": "Tesla",
  "Osm": "OSM", "ModelManager": "Models", "Mapd": "OSM", "Map": "OSM",
  "Sunnylink": "Sunnylink", "BackupManager": "Sunnylink",
  "Chevron": "Visuals", "DevUI": "Visuals", "Rainbow": "Visuals", "TorqueBar": "Visuals",
  "OnroadScreen": "Display", "Interactivity": "Display", "Brightness": "Display",
  "QuickBoot": "Developer", "EnableGithub": "Developer", "EnableCopyparty": "Developer",
  "ShowAdvanced": "Developer", "MaxTime": "Device", "DeviceBoot": "Device", "QuietMode": "Device",
  "SpDevBeep": "Device",
}

_PATH_SECTION_HINTS: tuple[tuple[str, str], ...] = (
  ("steering_sub_layouts/mads", "MADS"),
  ("steering_sub_layouts/lane_change", "Lateral"),
  ("steering_sub_layouts/torque", "Lateral"),
  ("steering", "Lateral"),
  ("cruise_sub_layouts/speed_limit", "Longitudinal"),
  ("cruise", "Longitudinal"),
  ("visuals", "Visuals"),
  ("display", "Display"),
  ("device", "Device"),
  ("developer", "Developer"),
  ("osm", "OSM"),
  ("models", "Models"),
  ("sunnylink", "Sunnylink"),
  ("vehicle", "Vehicle"),
  ("navigation", "Navigation"),
  ("network", "Network"),
)

_STATIC_FALLBACK: dict[str, dict[str, str]] = {
  "CameraOffset": {
    "title": "Camera Lateral Offset",
    "summary": "Lateral camera offset (m) for custom NN bundles; affects model path and onroad rendering.",
    "section": "Models",
  },
  "PlanplusControl": {
    "title": "Plan+ Control Gain",
    "summary": "Plan+ longitudinal control multiplier used by modeld_v2 (default 1.0).",
    "section": "Models",
  },
  "LagdValueCache": {
    "title": "Lagd learned delay cache",
    "summary": "Cached learned steer delay (read-only runtime).",
    "section": "Lateral",
  },
  "MapSpeedLimit": {"title": "Map speed limit", "summary": "Current map-derived speed limit (runtime).", "section": "OSM"},
  "MapAdvisorySpeedLimit": {"title": "Advisory speed limit", "summary": "Advisory map speed (runtime).", "section": "OSM"},
}

_PARAM_RE = re.compile(r'param\s*=\s*["\']([A-Za-z][A-Za-z0-9_]+)["\']')
_TR_RE = re.compile(r'(?:tr|tr_noop)\(\s*["\']((?:\\.|[^"\'\\])*)["\']')
_TOGGLE_DEF_KEY_RE = re.compile(
  r'["\']([A-Za-z][A-Za-z0-9_]+)["\']\s*:\s*\(\s*(?:lambda:\s*)?(?:tr|tr_noop)\(',
)


def _infer_tier(key: str) -> str:
  if key in _FORBIDDEN_KEYS:
    return "write_forbidden"
  if key in _REDACTED_KEYS:
    return "read_redacted"
  if key.startswith("dp_ui_") or key in ("IsMetric", "dp_dev_audible_alert_mode", "dp_dev_beep", "dp_dev_opview"):
    return "write_offroad_ui"
  if key == "dp_dev_last_log":
    return "read_always"
  if key.startswith("dp_dev_"):
    return "write_offroad_dev"
  if key.startswith(("dp_lat_", "dp_lon_", "dp_toyota_", "dp_honda_", "dp_vag_")):
    return "write_offroad_tune"
  if key.startswith("dp_"):
    return "write_offroad_tune"
  if key.startswith("ai_"):
    if key == "ai_api_key":
      return "read_redacted"
    if key in ("ai_web_pin",):
      return "write_offroad_dev"
    return "write_offroad_ui"
  if key.startswith(("Osm", "OSM", "Mapd", "Map")):
    if key in ("MapSpeedLimit", "MapAdvisorySpeedLimit", "NextMapSpeedLimit", "MapTargetVelocities", "RoadName"):
      return "read_always"
    return "write_offroad_tune"
  if key.startswith("ModelManager_"):
    if key in ("ModelManager_ModelsCache", "ModelManager_LastSyncTime", "ModelRunnerTypeCache"):
      return "read_always"
    return "write_offroad_tune"
  if key in ("SpDevBeep", "RecordAudio", "RecordFront", "AlwaysOnDM", "DistractionDetectionLevel",
             "ShowAdvancedControls", "Brightness", "QuietMode"):
    return "write_offroad_ui"
  if key in ("QuickBootToggle", "EnableGithubRunner", "EnableCopyparty"):
    return "write_offroad_dev"
  if key in ("CarParamsSP", "CarParamsSPCache", "CarParamsSPPersistent", "CarList"):
    return "read_always"
  return "write_offroad_tune"


def _infer_section(key: str) -> str:
  if key.startswith("dp_lat_"):
    return "Lateral"
  if key.startswith("dp_lon_"):
    return "Longitudinal"
  if key.startswith("dp_toyota_"):
    return "Toyota"
  if key.startswith("dp_honda_"):
    return "Honda"
  if key.startswith("dp_vag_"):
    return "VAG"
  if key.startswith("dp_ui_"):
    return "UI"
  if key.startswith("dp_dev_"):
    return "Device"
  if key.startswith("ai_"):
    return "AI"
  for prefix, section in _SP_SECTION_HINTS.items():
    if key.startswith(prefix) or key == prefix:
      return section
  if key == "CarPlatformBundle":
    return "Vehicle"
  return "openpilot"


def _section_from_path(rel_path: str) -> str:
  pl = rel_path.replace("\\", "/").lower()
  for frag, section in _PATH_SECTION_HINTS:
    if frag in pl:
      return section
  return "openpilot"


def _unescape_tr(s: str) -> str:
  return s.replace("\\n", "\n").replace("\\'", "'").replace('\\"', '"').replace("<br>", " ").strip()


def _extract_ui_metadata_from_text(text: str, rel_path: str) -> dict[str, dict[str, Any]]:
  section_default = _section_from_path(rel_path)
  out: dict[str, dict[str, Any]] = {}

  for m in _TOGGLE_DEF_KEY_RE.finditer(text):
    key = m.group(1)
    chunk = text[m.start(): m.start() + 600]
    strings = [_unescape_tr(s) for s in _TR_RE.findall(chunk)]
    title = strings[0] if strings else key
    desc = strings[1] if len(strings) > 1 else title
    out[key] = {
      "title": title[:160],
      "summary": desc[:400],
      "section": section_default,
      "ui_source": rel_path,
    }

  for m in _PARAM_RE.finditer(text):
    key = m.group(1)
    start = max(0, m.start() - 900)
    chunk = text[start: m.end() + 120]
    strings = [_unescape_tr(s) for s in _TR_RE.findall(chunk)]
    title = strings[0] if strings else key
    desc = strings[1] if len(strings) > 1 else (strings[0] if strings else key)
    prev = out.get(key)
    if prev is None or (strings and len(title) > 3):
      out[key] = {
        "title": title[:160],
        "summary": desc[:400],
        "section": section_default,
        "ui_source": rel_path,
      }
  return out


def _discover_sunnypilot_ui_metadata() -> dict[str, dict[str, Any]]:
  merged: dict[str, dict[str, Any]] = {}
  for root in _SP_UI_ROOTS:
    if not root.is_dir():
      continue
    for path in root.rglob("*.py"):
      try:
        rel = str(path.relative_to(_OP_ROOT)).replace("\\", "/")
        text = path.read_text(encoding="utf-8", errors="replace")
      except OSError:
        continue
      for key, meta in _extract_ui_metadata_from_text(text, rel).items():
        if key not in merged or len(meta.get("summary", "")) > len(merged[key].get("summary", "")):
          merged[key] = meta
  return merged


def _parse_sunnypilot_params_keys() -> list[str]:
  if not _PARAMS_KEYS_H.is_file():
    return []
  keys: list[str] = []
  in_sp = False
  for line in _PARAMS_KEYS_H.read_text(encoding="utf-8", errors="replace").splitlines():
    if "// --- sunnypilot params" in line:
      in_sp = True
      continue
    if in_sp and "// sunnypilot C3 dev" in line:
      break
    if not in_sp:
      continue
    m = re.match(r'\s*\{"([^"]+)"', line)
    if m:
      keys.append(m.group(1))
  return keys


def _enrich_entry(entry: dict[str, Any], ui_meta: dict[str, Any] | None) -> dict[str, Any]:
  out = dict(entry)
  if ui_meta:
    if ui_meta.get("title") and (not out.get("title") or out.get("summary") == out.get("key")):
      out["title"] = ui_meta["title"]
    if ui_meta.get("summary") and len(str(ui_meta["summary"])) > len(str(out.get("summary", ""))):
      out["summary"] = ui_meta["summary"]
    if ui_meta.get("section") and out.get("section") in (None, "", "openpilot", "sunnypilot", "General"):
      out["section"] = ui_meta["section"]
    if ui_meta.get("ui_source"):
      out["ui_source"] = ui_meta["ui_source"]
  if not out.get("title"):
    out["title"] = out.get("summary") or out.get("key")
  return out


@lru_cache(maxsize=1)
def build_merged_catalog() -> dict[str, dict[str, Any]]:
  merged: dict[str, dict[str, Any]] = {}
  ui_meta_all = _discover_sunnypilot_ui_metadata()

  if _STATIC.is_file():
    data = json.loads(_STATIC.read_text(encoding="utf-8"))
    for entry in data.get("params") or []:
      key = entry.get("key")
      if key:
        merged[key] = _enrich_entry(dict(entry), ui_meta_all.get(key))

  try:
    from dragonpilot.settings import SETTINGS
  except ImportError:
    SETTINGS = []

  for section in SETTINGS:
    section_title = section.get("title", "")
    for setting in section.get("settings", []):
      key = setting.get("key")
      if not key or setting.get("type") == "action_item":
        continue
      if key in merged:
        continue
      title = setting.get("title")
      if callable(title):
        title = str(title)
      desc = setting.get("description")
      if callable(desc):
        desc = str(desc)
      entry: dict[str, Any] = {
        "key": key,
        "tier": _infer_tier(key),
        "section": section_title or _infer_section(key),
        "summary": (desc or title or key)[:400],
        "title": (title or key)[:160],
      }
      brands = setting.get("brands")
      if brands:
        entry["brands"] = brands
      merged[key] = _enrich_entry(entry, ui_meta_all.get(key))

  for key in _parse_sunnypilot_params_keys():
    if key in merged:
      merged[key] = _enrich_entry(merged[key], ui_meta_all.get(key))
      continue
    fb = _STATIC_FALLBACK.get(key, {})
    merged[key] = _enrich_entry({
      "key": key,
      "tier": _infer_tier(key),
      "section": fb.get("section") or _infer_section(key),
      "summary": fb.get("summary", key),
      "title": fb.get("title", key),
    }, ui_meta_all.get(key))

  for key, ui_meta in ui_meta_all.items():
    if key in merged:
      merged[key] = _enrich_entry(merged[key], ui_meta)
      continue
    merged[key] = _enrich_entry({
      "key": key,
      "tier": _infer_tier(key),
      "section": ui_meta.get("section") or _infer_section(key),
      "summary": ui_meta.get("summary", key),
      "title": ui_meta.get("title", key),
    }, ui_meta)

  for legacy, sp_key in DP_TO_SP_PARAM_ALIASES.items():
    merged.pop(legacy, None)
    if sp_key in merged:
      entry = dict(merged[sp_key])
      aliases = list(entry.get("legacy_aliases") or [])
      if legacy not in aliases:
        aliases.append(legacy)
      entry["legacy_aliases"] = aliases
      merged[sp_key] = entry

  return merged


def clear_catalog_cache() -> None:
  build_merged_catalog.cache_clear()
