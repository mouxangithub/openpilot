"""Central path resolution for op助手 — works on comma device and PC dev hosts."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Literal

# Repo root: directory that contains `ai/` (and either flat or nested openpilot tree).
_DEFAULT_ROOT = Path(__file__).resolve().parents[2]

Layout = Literal["nested", "flat", "unknown"]
_LAYOUT_CACHE: Layout | None = None
_SOURCE_ROOT_CACHE: Path | None = None


def openpilot_root() -> Path:
  """Openpilot 源码根目录。PC 上可通过环境变量 OPENPILOT_ROOT 覆盖。"""
  env = (os.environ.get("OPENPILOT_ROOT") or os.environ.get("OP_ROOT") or "").strip()
  if env:
    return Path(env).expanduser().resolve()
  return _DEFAULT_ROOT


def _detect_layout(root: Path) -> Layout:
  if (root / "openpilot" / "selfdrive").is_dir() or (root / "openpilot" / "system").is_dir():
    return "nested"
  if (root / "selfdrive").is_dir() or (root / "system").is_dir():
    return "flat"
  return "unknown"


def repo_layout() -> Layout:
  """Return ``nested`` (openpilot/selfdrive/...) or ``flat`` (selfdrive/ at repo root)."""
  global _LAYOUT_CACHE
  if _LAYOUT_CACHE is None:
    _LAYOUT_CACHE = _detect_layout(openpilot_root())
  return _LAYOUT_CACHE


def openpilot_source_root() -> Path:
  """Directory containing selfdrive/, system/, sunnypilot/, common/ (nested: repo/openpilot)."""
  global _SOURCE_ROOT_CACHE
  if _SOURCE_ROOT_CACHE is not None:
    return _SOURCE_ROOT_CACHE
  root = openpilot_root()
  nested = root / "openpilot"
  if (nested / "selfdrive").is_dir() or (nested / "system").is_dir():
    _SOURCE_ROOT_CACHE = nested
  else:
    _SOURCE_ROOT_CACHE = root
  return _SOURCE_ROOT_CACHE


def source_path(*parts: str) -> Path:
  """Path under the openpilot source tree (selfdrive, system, sunnypilot, common, …)."""
  return openpilot_source_root().joinpath(*parts)


def source_path_exists(*parts: str) -> bool:
  return source_path(*parts).exists()


def rel_source(*parts: str) -> str:
  """Relative path from repo root for display / docs (e.g. openpilot/selfdrive/... or selfdrive/...)."""
  root = openpilot_root()
  try:
    return str(source_path(*parts).relative_to(root))
  except ValueError:
    return str(source_path(*parts))


def find_repo_file(*rel_paths: str) -> Path | None:
  """Return first existing path relative to repo root (tries each candidate in order)."""
  root = openpilot_root()
  for rel in rel_paths:
    path = root / rel
    if path.exists():
      return path
  return None


def tools_path(*parts: str) -> Path:
  """
  Resolve tools/ path — build tools may live under openpilot/tools/ (nested) or root tools/.
  Prefers the location that exists; nested openpilot/tools wins when both exist.
  """
  root = openpilot_root()
  src = openpilot_source_root()
  candidates = [
    src.joinpath("tools", *parts),
    root.joinpath("tools", *parts),
  ]
  for path in candidates:
    if path.exists():
      return path
  # Default: nested layout prefers openpilot/tools; flat uses root/tools
  return candidates[0] if repo_layout() == "nested" else candidates[1]


def rel_tools(*parts: str) -> str:
  """Relative tools path from repo root for display."""
  root = openpilot_root()
  try:
    return str(tools_path(*parts).relative_to(root))
  except ValueError:
    return str(tools_path(*parts))


def is_comma_device() -> bool:
  if os.path.isfile("/TICI") or os.path.isfile("/AGNOS"):
    return True
  try:
    from openpilot.common.hardware import COMMA_HARDWARE
    return bool(COMMA_HARDWARE)
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
    from openpilot.common.hardware.hw import Paths
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


def assistant_workspace_dir(*, mkdir: bool = True) -> Path:
  """User-editable workspace markdown under ``<ai>/workspace/`` (gitignored)."""
  from ai.common.repo_targets import assistant_repo_path
  path = assistant_repo_path() / "workspace"
  if mkdir:
    path.mkdir(parents=True, exist_ok=True)
  return path


def ai_config_path() -> Path:
  from ai.common.config_store import ai_config_path as _path
  return _path()


def assistant_repo_root() -> Path:
  from ai.common.repo_targets import assistant_repo_path
  return assistant_repo_path()


def path_summary() -> dict[str, Any]:
  root = openpilot_root()
  rd = routes_dir()
  src = openpilot_source_root()
  layout = repo_layout()
  return {
    "openpilot_root": str(root),
    "openpilot_source_root": str(src),
    "repo_layout": layout,
    "routes_dir": rd,
    "routes_dir_exists": os.path.isdir(rd),
    "ai_config_path": str(ai_config_path()),
    "assistant_repo_root": str(assistant_repo_root()),
    "adaptation_drafts": str(adaptation_drafts_dir()),
    "env_overrides": {
      "OPENPILOT_ROOT": os.environ.get("OPENPILOT_ROOT") or os.environ.get("OP_ROOT"),
      "OPENPILOT_ROUTES_DIR": os.environ.get("OPENPILOT_ROUTES_DIR") or os.environ.get("OP_ROUTES_DIR"),
    },
    "detected_from": "env" if os.environ.get("OPENPILOT_ROOT") or os.environ.get("OP_ROOT") else "repo",
    "python": sys.version.split()[0],
  }
