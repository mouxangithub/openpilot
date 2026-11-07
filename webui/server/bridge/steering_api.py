"""Steering panel helpers — torque tune version tree."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def _torque_versions_path() -> Path | None:
  candidates = [
    Path(__file__).resolve().parents[3] / "openpilot" / "sunnypilot" / "selfdrive" / "controls" / "lib" / "latcontrol_torque_versions.json",
    Path(__file__).resolve().parents[4] / "openpilot" / "sunnypilot" / "selfdrive" / "controls" / "lib" / "latcontrol_torque_versions.json",
  ]
  for c in candidates:
    if c.is_file():
      return c
  return None


def _load_torque_versions() -> dict[str, dict[str, Any]]:
  path = _torque_versions_path()
  if not path:
    return {}
  try:
    return json.loads(path.read_text(encoding="utf-8"))
  except Exception:
    return {}


def _current_torque_label(raw_val: bytes | None, versions: dict[str, dict[str, Any]]) -> str:
  if not raw_val:
    return "Default"
  try:
    current = float(raw_val)
    for label, info in versions.items():
      try:
        if math.isclose(float(info["version"]), current, rel_tol=1e-5):
          return label
      except (KeyError, TypeError, ValueError):
        continue
  except (TypeError, ValueError):
    pass
  return "Default"


def torque_versions() -> dict[str, Any]:
  versions = _load_torque_versions()
  options: list[dict[str, Any]] = [{"label": "Default", "version": None}]
  for label, info in sorted(versions.items(), key=lambda kv: float(kv[1].get("version", 0)), reverse=True):
    try:
      options.append({"label": label, "version": float(info["version"])})
    except (KeyError, TypeError, ValueError):
      continue

  current_label = "Default"
  try:
    from openpilot.common.params import Params
    current_label = _current_torque_label(Params().get("TorqueControlTune"), versions)
  except Exception:
    pass

  return {"ok": True, "options": options, "current_label": current_label}
