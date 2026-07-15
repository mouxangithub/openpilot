"""
Vehicle adaptation draft workspace — human + AI co-adaptation.

Writes ONLY under adaptation_drafts/ (never opendbc production paths).
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from ai.system.paths import adaptation_drafts_dir

_MAX_DBC_CHARS = 500_000
_MAX_BUNDLE_FILES = 40


def _drafts_root() -> Path:
  root = adaptation_drafts_dir()
  root.mkdir(parents=True, exist_ok=True)
  return root


def _safe_project_id(name: str) -> str:
  name = (name or "").strip()
  if not name:
    return f"adapt_{int(time.time())}"
  safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", name)[:64]
  return safe or f"adapt_{int(time.time())}"


def list_adaptation_projects() -> dict[str, Any]:
  root = _drafts_root()
  projects = []
  for p in sorted(root.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
    if not p.is_dir():
      continue
    meta_path = p / "manifest.json"
    meta = {}
    if meta_path.is_file():
      try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
      except Exception:
        pass
    projects.append({
      "id": p.name,
      "path": str(p),
      "fingerprint": meta.get("fingerprint", ""),
      "updated_at": meta.get("updated_at", int(p.stat().st_mtime)),
      "files": [f.name for f in p.iterdir() if f.is_file()],
    })
  return {"ok": True, "projects": projects[:30], "root": str(root)}


def list_dbcs() -> dict[str, Any]:
  from ai.cabana import _list_dbc_names
  return {"ok": True, "dbcs": _list_dbc_names()}


def read_dbc_file(dbc_name: str, *, max_chars: int = 120_000) -> dict[str, Any]:
  from ai.cabana import _load_dbc_content, _parse_dbc_signals
  if not dbc_name or ".." in dbc_name or "/" in dbc_name or "\\" in dbc_name:
    return {"ok": False, "error": "Invalid dbc name"}
  content = _load_dbc_content(dbc_name)
  if content is None:
    return {"ok": False, "error": f"DBC '{dbc_name}' not found"}
  if len(content) > max_chars:
    content = content[:max_chars] + "\n\n... [truncated] ..."
  signals = _parse_dbc_signals(dbc_name)
  return {
    "ok": True,
    "name": dbc_name,
    "content": content,
    "signal_count": len(signals),
    "signals_preview": signals[:40],
  }


def save_adaptation_draft(
  *,
  project_id: str,
  fingerprint: str = "",
  files: dict[str, str],
  notes: str = "",
  metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
  """Save draft files (dbc, carstate.py.snippet, carcontroller.py.snippet, README.md)."""
  if not files:
    return {"ok": False, "error": "files object is required"}
  pid = _safe_project_id(project_id)
  root = _drafts_root() / pid
  root.mkdir(parents=True, exist_ok=True)

  allowed_ext = {".dbc", ".md", ".txt", ".json", ".py", ".snippet", ".yaml", ".yml"}
  written: list[str] = []
  for rel, content in files.items():
    rel = (rel or "").strip().replace("\\", "/")
    if not rel or ".." in rel or rel.startswith("/"):
      return {"ok": False, "error": f"Invalid file path: {rel}"}
    suffix = Path(rel).suffix.lower()
    if suffix not in allowed_ext and "." in Path(rel).name:
      return {"ok": False, "error": f"Extension not allowed: {rel}"}
    if len(content) > _MAX_DBC_CHARS:
      return {"ok": False, "error": f"File too large: {rel}"}
    dest = root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    written.append(rel)

  manifest = {
    "project_id": pid,
    "fingerprint": fingerprint,
    "updated_at": int(time.time()),
    "notes": notes[:4000] if notes else "",
    "metadata": metadata or {},
    "files": written,
  }
  (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
  if notes:
    (root / "NOTES.md").write_text(notes, encoding="utf-8")

  return {
    "ok": True,
    "project_id": pid,
    "path": str(root),
    "written": written,
    "hint": "Download bundle from PC via export_adaptation_bundle; merge into opendbc on dev machine after review.",
  }


def export_adaptation_bundle(project_id: str) -> dict[str, Any]:
  pid = _safe_project_id(project_id)
  root = _drafts_root() / pid
  if not root.is_dir():
    return {"ok": False, "error": f"Project '{pid}' not found"}

  bundle: dict[str, str] = {}
  count = 0
  for path in root.rglob("*"):
    if not path.is_file() or count >= _MAX_BUNDLE_FILES:
      continue
    rel = str(path.relative_to(root)).replace("\\", "/")
    try:
      text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
      continue
    if len(text) > _MAX_DBC_CHARS:
      text = text[:_MAX_DBC_CHARS] + "\n... [truncated] ..."
    bundle[rel] = text
    count += 1

  manifest = bundle.get("manifest.json", "{}")
  try:
    meta = json.loads(manifest)
  except Exception:
    meta = {}

  return {
    "ok": True,
    "project_id": pid,
    "fingerprint": meta.get("fingerprint", ""),
    "file_count": len(bundle),
    "files": bundle,
    "pr_checklist": [
      "Review DBC BO_/SG_ lines and checksums",
      "Fingerprint dict {0xID: length} — five signal classes (speed, steer, brake, gas, gear)",
      "CarState: vEgo, steeringAngleDeg, gas, brake, gasPressed, brakePressed, standstill, gear",
      "CarController: LKAS/SCC msgs, apply_driver_steer_torque_limits, MAX_STEER_SPEED",
      "CarSpecs: mass, wheelbase, steerRatio (values.py)",
      "STEER_MAX, STEER_DELTA_UP/DOWN, ACCEL_MIN/MAX",
      "Add fingerprint to opendbc/car/fingerprints.py",
      "Register interface in opendbc/car/*/interface.py",
      "Closed-course steering + longitudinal test before public road",
    ],
  }


def analyze_can_id_pattern(hex_ids: list[str]) -> dict[str, Any]:
  """Heuristic summary of CAN IDs for fingerprint brainstorming."""
  ids: list[int] = []
  for h in hex_ids:
    h = h.strip().lower().replace("0x", "")
    if not h:
      continue
    try:
      ids.append(int(h, 16))
    except ValueError:
      continue
  ids = sorted(set(ids))
  by_len: dict[int, int] = {}
  return {
    "ok": True,
    "count": len(ids),
    "ids_hex": [f"0x{i:X}" for i in ids[:80]],
    "hint": (
      "按五类信号找 CAN ID：车速、转向角、制动、加速踏板、档位；"
      "分 bus 0/1/2 抓包；对照 opendbc fingerprints 与同品牌车型。"
    ),
    "checklist": [
      "speed (vEgo / wheel speed)",
      "steering angle",
      "brake / brake pressure",
      "accelerator pedal",
      "gear shifter",
    ],
  }


_SIGNAL_CATEGORIES: dict[str, list[str]] = {
  "speed": ["WHL", "WHEEL", "SPEED", "VSS", "VEH_SPD", "ESP_V"],
  "steering": ["STEER", "SAS", "ANGLE", "EPS", "LKAS"],
  "brake": ["BRK", "BRAKE", "BRK_", "PRESSURE"],
  "accelerator": ["GAS", "ACCEL", "PEDAL", "APPS"],
  "gear": ["GEAR", "SHIFTER", "PRNDL", "LEVER"],
}


def suggest_signals_for_adaptation(dbc_name: str, *, max_per_category: int = 8) -> dict[str, Any]:
  """Suggest DBC signals for the five fingerprint/adaptation classes."""
  from ai.cabana import _parse_dbc_signals

  if not dbc_name or ".." in dbc_name:
    return {"ok": False, "error": "Invalid dbc_name"}

  signals = _parse_dbc_signals(dbc_name)
  if not signals:
    return {"ok": False, "error": f"No signals parsed for DBC '{dbc_name}'"}

  by_category: dict[str, list[dict[str, Any]]] = {k: [] for k in _SIGNAL_CATEGORIES}
  for sig in signals:
    name = str(sig.get("name", "")).upper()
    msg = str(sig.get("message", "")).upper()
    combined = f"{msg} {name}"
    for cat, keywords in _SIGNAL_CATEGORIES.items():
      if any(kw in combined for kw in keywords):
        entry = {
          "message": sig.get("message"),
          "name": sig.get("name"),
          "address_hex": f"0x{int(sig.get('address', 0)):X}" if sig.get("address") is not None else None,
          "unit": sig.get("unit", ""),
        }
        if entry not in by_category[cat]:
          by_category[cat].append(entry)
        break

  for cat in by_category:
    by_category[cat] = by_category[cat][:max_per_category]

  return {
    "ok": True,
    "dbc_name": dbc_name,
    "categories": by_category,
    "hint": "Pick one signal per class; confirm address in Cabana; build fingerprint with compare_fingerprint.",
  }
