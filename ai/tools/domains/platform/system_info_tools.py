"""Build info and manager process list."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

from ai.system.paths import openpilot_root, source_path


def _git_field(*args: str) -> str:
  try:
    return subprocess.check_output(
      ["git", "-C", str(openpilot_root())] + list(args),
      text=True,
      stderr=subprocess.DEVNULL,
      timeout=5,
    ).strip()
  except Exception:
    return ""


def get_build_info() -> dict[str, Any]:
  root = openpilot_root()
  info: dict[str, Any] = {
    "ok": True,
    "openpilot_root": str(root),
    "platform": platform.platform(),
    "python": sys.version.split()[0],
    "git": {
      "branch": _git_field("rev-parse", "--abbrev-ref", "HEAD"),
      "commit": _git_field("rev-parse", "--short", "HEAD"),
      "describe": _git_field("describe", "--tags", "--always", "--dirty"),
    },
  }
  try:
    from openpilot.common.params import Params
    p = Params()
    for key in (
      "CarPlatformBundle",
      "CarParams",
      "Version",
    ):
      raw = p.get(key)
      if raw is None:
        continue
      if key == "CarParams":
        try:
          from cereal import car
          with car.CarParams.from_bytes(raw) as cp:
            info["car_params"] = {
              "carFingerprint": cp.carFingerprint,
              "carName": getattr(cp, "carName", ""),
            }
        except Exception:
          info["car_params"] = "[binary]"
      else:
        info[key] = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw)
  except Exception as e:
    info["params_warning"] = str(e)

  models_dir = source_path("selfdrive", "modeld", "models")
  if models_dir.is_dir():
    info["model_files"] = [f.name for f in list(models_dir.glob("*.onnx"))[:12]]

  return info


def list_managed_processes(get_state_reader) -> dict[str, Any]:
  try:
    reader = get_state_reader()
    reader.update(timeout=0)
    snap = reader.snapshot()
    full = reader.latest()
  except Exception as e:
    return {"ok": False, "error": str(e)}

  processes = full.get("processes") or [] if isinstance(full, dict) else []

  if not processes:
    return {
      "ok": True,
      "processes": [],
      "hint": "No managerState yet; is manager running?",
      "enabled": snap.enabled,
      "vEgo": round(snap.v_ego, 3),
      "script": "cereal managerState",
    }

  not_running = [p for p in processes if p.get("shouldBeRunning") and not p.get("running")]
  return {
    "ok": True,
    "process_count": len(processes),
    "processes": processes[:60],
    "not_running_expected": not_running[:20],
    "enabled": snap.enabled,
    "vEgo": round(snap.v_ego, 3),
    "script": "cereal managerState",
  }
