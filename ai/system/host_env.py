"""Detect op助手 host: comma device (C3/C3X/C4) vs PC dev (Ubuntu/macOS/WSL)."""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path
from typing import Any

from ai.system.paths import is_comma_device, openpilot_root, path_summary, routes_dir

_OPENPILOT_ROOT = openpilot_root()


def is_pc_dev() -> bool:
  return not is_comma_device()


def _has_gui_display() -> bool:
  if sys.platform == "darwin":
    return True
  if sys.platform == "win32":
    return True
  return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _routes_dir() -> str:
  return routes_dir()


def _resolve_tool_path(*parts: str) -> Path:
  return _OPENPILOT_ROOT.joinpath(*parts)


def pc_tool_inventory() -> dict[str, Any]:
  """Which PC-native binaries/scripts exist on this host."""
  items: dict[str, dict[str, Any]] = {}
  candidates = {
    "plotjuggler": ("tools/plotjuggler/juggle.py", "python"),
    "jotpluggler": ("tools/jotpluggler/jotpluggler", "binary"),
    "replay": ("tools/replay/replay", "binary"),
    "cabana": ("tools/cabana/cabana", "binary"),
    "auth": ("tools/lib/auth.py", "python"),
    "sim_bridge": ("tools/sim/run_bridge.py", "python"),
    "camerastream": ("tools/camerastream/compressed_vipc.py", "python"),
    "replay_ui": ("tools/replay/ui.py", "python"),
  }
  for name, (rel, kind) in candidates.items():
    path = _resolve_tool_path(*rel.split("/"))
    exists = path.is_file()
    items[name] = {
      "path": str(path),
      "exists": exists,
      "kind": kind,
      "launchable": exists and (kind == "python" or os.access(path, os.X_OK)),
    }
  pj_bin = _resolve_tool_path("tools/plotjuggler/bin/plotjuggler")
  items["plotjuggler_binary"] = {
    "path": str(pj_bin),
    "exists": pj_bin.is_file(),
    "kind": "binary",
    "launchable": pj_bin.is_file() and os.access(pj_bin, os.X_OK),
  }
  return items


def get_host_environment() -> dict[str, Any]:
  inv = pc_tool_inventory()
  paths = path_summary()
  hardware_profile: dict[str, Any] | None = None
  try:
    from ai.tsk.lib.panda_connect import host_hardware_profile

    hardware_profile = host_hardware_profile()
  except Exception:
    hardware_profile = None
  out: dict[str, Any] = {
    "ok": True,
    "host_kind": "comma_device" if is_comma_device() else "pc_dev",
    "is_pc_dev": is_pc_dev(),
    "is_comma_device": is_comma_device(),
    "platform": platform.platform(),
    "python": sys.version.split()[0],
    "has_gui_display": _has_gui_display(),
    "routes_dir": _routes_dir(),
    "openpilot_root": str(_OPENPILOT_ROOT),
    "paths": paths,
    "pc_tools": inv,
    "hint": (
      "PC 上若仓库不在默认位置，可设置环境变量 OPENPILOT_ROOT；"
      "路线目录可设 OPENPILOT_ROUTES_DIR（默认 ~/.comma/media/0/realdata）。"
      "车机请用 Web Cabana + 路线工具；PC 可用 pc_launch_* 启动桌面工具。"
    ),
  }
  if hardware_profile is not None:
    out["hardware_profile"] = hardware_profile
    if is_comma_device():
      out["comma_device"] = hardware_profile
  return out
