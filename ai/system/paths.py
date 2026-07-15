"""Central path resolution for op助手 — works on comma device and PC dev hosts."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# Repo root: directory that contains `ai/`, `selfdrive/`, `tools/`.
_DEFAULT_ROOT = Path(__file__).resolve().parents[2]


def openpilot_root() -> Path:
  """Openpilot 源码根目录。PC 上可通过环境变量 OPENPILOT_ROOT 覆盖。"""
  env = (os.environ.get("OPENPILOT_ROOT") or os.environ.get("OP_ROOT") or "").strip()
  if env:
    return Path(env).expanduser().resolve()
  return _DEFAULT_ROOT


def is_comma_device() -> bool:
  if os.path.isfile("/TICI") or os.path.isfile("/AGNOS"):
    return True
  try:
    from openpilot.system.hardware import TICI
    return bool(TICI)
  except Exception:
    return False


def routes_dir() -> str:
  """
  行车日志（route）存放目录。
  - 车机：/data/media/0/realdata
  - PC：环境变量 OPENPILOT_ROUTES_DIR，或 openpilot Paths.log_root()，或 ~/.comma/media/0/realdata
  """
  env = (os.environ.get("OPENPILOT_ROUTES_DIR") or os.environ.get("OP_ROUTES_DIR") or "").strip()
  if env:
    return str(Path(env).expanduser())
  if is_comma_device():
    return "/data/media/0/realdata"
  try:
    from openpilot.system.hardware.hw import Paths
    return Paths.log_root()
  except Exception:
    pass
  home = Path.home()
  candidates = [
    home / ".comma" / "media" / "0" / "realdata",
    openpilot_root() / "data" / "media" / "0" / "realdata",
  ]
  for path in candidates:
    if path.is_dir():
      return str(path)
  return str(candidates[0])


def workspace_path(*parts: str, mkdir: bool = False) -> Path:
  """在 openpilot 根目录下的数据路径（适配草稿、RAG 索引等）。"""
  path = openpilot_root().joinpath(*parts)
  if mkdir:
    path.parent.mkdir(parents=True, exist_ok=True)
  return path


def adaptation_drafts_dir() -> Path:
  return workspace_path("adaptation_drafts", mkdir=True)


def tune_snapshots_dir() -> Path:
  return workspace_path("ai_tune_snapshots", mkdir=True)


def rag_vectors_path() -> Path:
  return workspace_path("ai_rag_vectors.json", mkdir=True)


def rag_seed_version_path() -> Path:
  return workspace_path("ai_rag_seed_version.json", mkdir=True)


def notifications_path() -> Path:
  return workspace_path("ai_notifications.json", mkdir=True)


def path_summary() -> dict[str, Any]:
  root = openpilot_root()
  rd = routes_dir()
  return {
    "openpilot_root": str(root),
    "routes_dir": rd,
    "routes_dir_exists": os.path.isdir(rd),
    "adaptation_drafts": str(adaptation_drafts_dir()),
    "env_overrides": {
      "OPENPILOT_ROOT": os.environ.get("OPENPILOT_ROOT") or os.environ.get("OP_ROOT"),
      "OPENPILOT_ROUTES_DIR": os.environ.get("OPENPILOT_ROUTES_DIR") or os.environ.get("OP_ROUTES_DIR"),
    },
    "detected_from": "env" if os.environ.get("OPENPILOT_ROOT") or os.environ.get("OP_ROOT") else "repo",
    "python": sys.version.split()[0],
  }
