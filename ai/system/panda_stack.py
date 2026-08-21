"""Detect Panda / pandad layout in the connected openpilot tree (fork-agnostic).

Supports common community layouts, for example:

- **Unified**: ``panda/`` builds F4+H7; ``selfdrive/pandad`` loads both
- **Split (legacy)**: ``panda/`` F4 + ``panda_tici/`` H7; may use ``pandad_tici``
- **Hybrid**: ``panda_tici`` present but only ``selfdrive/pandad`` (no ``pandad_tici``)

Detection is filesystem-based under ``openpilot_root()`` (``OPENPILOT_ROOT`` / ``OP_ROOT``).

Signed firmware (``panda.bin.signed``, ``panda_h7.bin.signed``) lives under ``panda/board/obj/``
after ``scons`` — **not** in the ``ai`` package. op助手 only resolves paths and invokes build/flash tools.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from ai.system.paths import find_repo_file, openpilot_root, source_path, source_path_exists, tools_path

StackKind = Literal[
  "unified",
  "panda_tici_pandad_tici",
  "panda_tici_pandad",
  "panda_only",
  "unknown",
]

F4_FW_REL = Path("panda", "board", "obj", "panda.bin.signed")
H7_FW_UNIFIED_REL = Path("panda", "board", "obj", "panda_h7.bin.signed")
H7_FW_TICI_REL = Path("panda_tici", "board", "obj", "panda.bin.signed")


def _root() -> Path:
  return openpilot_root()


def _path_exists(rel: str) -> bool:
  return (_root() / rel).exists()


def has_panda_tree() -> bool:
  return _path_exists("panda/board") or _path_exists("openpilot/panda/board")


def has_panda_tici_tree() -> bool:
  return _path_exists("panda_tici/board") or _path_exists("openpilot/panda_tici/board")


def has_pandad_tree() -> bool:
  return (
    source_path_exists("selfdrive", "pandad", "pandad.py")
    or source_path_exists("selfdrive", "pandad", "pandad.cc")
  )


def has_pandad_tici_tree() -> bool:
  return (
    source_path_exists("selfdrive", "pandad_tici", "pandad.py")
    or source_path_exists("selfdrive", "pandad_tici", "pandad.cc")
  )


def f4_firmware_path() -> Path:
  found = find_repo_file(
    "panda/board/obj/panda.bin.signed",
    "openpilot/panda/board/obj/panda.bin.signed",
  )
  return found if found is not None else _root() / F4_FW_REL


def h7_firmware_path() -> Path:
  """Return the expected H7 signed firmware path for this tree."""
  unified = find_repo_file(
    "panda/board/obj/panda_h7.bin.signed",
    "openpilot/panda/board/obj/panda_h7.bin.signed",
  )
  if unified is not None:
    return unified
  tici = find_repo_file(
    "panda_tici/board/obj/panda.bin.signed",
    "openpilot/panda_tici/board/obj/panda.bin.signed",
  )
  if tici is not None:
    return tici
  if has_panda_tici_tree():
    return _root() / H7_FW_TICI_REL
  return _root() / H7_FW_UNIFIED_REL


def h7_board_dir() -> Path | None:
  """Directory to run ``scons`` for H7 firmware."""
  unified = find_repo_file("panda/board", "openpilot/panda/board")
  tici = find_repo_file("panda_tici/board", "openpilot/panda_tici/board")
  if unified is not None:
    if (unified / "stm32h7").is_dir() or (unified / "obj" / "panda_h7.bin.signed").is_file():
      return unified
  if tici is not None:
    return tici
  return unified


def f4_board_dir() -> Path | None:
  return find_repo_file("panda/board", "openpilot/panda/board")


def stack_kind() -> StackKind:
  pt = has_panda_tree()
  pti = has_panda_tici_tree()
  pd = has_pandad_tree()
  pdt = has_pandad_tici_tree()
  if pti and pdt:
    return "panda_tici_pandad_tici"
  if pti and pd and not pdt:
    return "panda_tici_pandad"
  if pt and pd and not pti:
    return "unified"
  if pt and not pti:
    return "panda_only"
  if pti:
    return "panda_tici_pandad" if pd else "panda_tici_pandad_tici"
  return "unknown"


def resolve_pandad_module(*, prefer_tici: bool | None = None) -> str:
  """Pick pandad Python module for stop/start/restart."""
  has_tici = has_pandad_tici_tree()
  has_std = has_pandad_tree()
  if prefer_tici is None:
    if has_std and has_tici:
      # Both present: prefer unified pandad (newer merges); DP-only trees usually lack pandad/.
      prefer_tici = False
    else:
      prefer_tici = has_tici and not has_std
  if prefer_tici and has_tici:
    return "selfdrive.pandad_tici.pandad"
  if has_std:
    return "selfdrive.pandad.pandad"
  if has_tici:
    return "selfdrive.pandad_tici.pandad"
  return "selfdrive.pandad.pandad"


def pandad_process_name(*, prefer_tici: bool | None = None) -> str:
  mod = resolve_pandad_module(prefer_tici=prefer_tici)
  return "pandad_tici" if "pandad_tici" in mod else "pandad"


def resolve_panda_backend(*, for_h7: bool = False) -> str:
  """Python package name for Panda USB (display / import hint)."""
  if for_h7 and has_panda_tici_tree():
    unified_h7 = find_repo_file(
      "panda/board/obj/panda_h7.bin.signed",
      "openpilot/panda/board/obj/panda_h7.bin.signed",
    )
    if unified_h7 is None or not unified_h7.is_file():
      return "panda_tici"
  return "panda"


def use_tici_panda_stack() -> bool:
  """True when this tree uses split ``panda_tici`` / ``pandad_tici`` (or H7 via panda_tici)."""
  kind = stack_kind()
  return kind in ("panda_tici_pandad_tici", "panda_tici_pandad")


def rebuild_script_path(*, prefer_tici: bool | None = None) -> Path:
  mod = resolve_pandad_module(prefer_tici=prefer_tici)
  ai_root = openpilot_root()

  def _ai_script(name: str) -> Path:
    return ai_root / "ai" / "scripts" / name

  if "pandad_tici" in mod:
    tici = tools_path("rebuild_pandad_tici.sh")
    if tici.is_file():
      return tici
    ai_tici = _ai_script("rebuild_pandad_tici.sh")
    if ai_tici.is_file():
      return ai_tici

  std = tools_path("rebuild_pandad.sh")
  if std.is_file():
    return std
  ai_std = _ai_script("rebuild_pandad.sh")
  if ai_std.is_file():
    return ai_std

  legacy = tools_path("rebuild_pandad_tici.sh")
  if legacy.is_file():
    return legacy
  return ai_std if ai_std.is_file() else std


def can_hash_sync_targets() -> list[str]:
  """Human-readable firmware trees to mention when opendbc/safety/can.h changes."""
  targets: list[str] = []
  if has_panda_tree():
    targets.append("panda/board (F4" + (" + H7" if h7_board_dir() and h7_board_dir() == f4_board_dir() else "") + ")")
  if has_panda_tici_tree() and h7_board_dir() != f4_board_dir():
    targets.append("panda_tici/board (H7)")
  return targets or ["panda/board"]


def detect_panda_stack() -> dict[str, Any]:
  kind = stack_kind()
  f4_board = f4_board_dir()
  h7_board = h7_board_dir()
  return {
    "stack_kind": kind,
    "panda_tree": has_panda_tree(),
    "panda_tici_tree": has_panda_tici_tree(),
    "pandad_tree": has_pandad_tree(),
    "pandad_tici_tree": has_pandad_tici_tree(),
    "panda_tici_available": has_panda_tici_tree(),
    "pandad_tici_available": has_pandad_tici_tree(),
    "use_tici_panda_stack": use_tici_panda_stack(),
    "panda_backend": resolve_panda_backend(),
    "panda_backend_h7": resolve_panda_backend(for_h7=True),
    "pandad_process": pandad_process_name(),
    "pandad_module": resolve_pandad_module(),
    "f4_firmware_path": str(f4_firmware_path()),
    "h7_firmware_path": str(h7_firmware_path()),
    "f4_board_dir": str(f4_board) if f4_board else None,
    "h7_board_dir": str(h7_board) if h7_board else None,
    "rebuild_script": str(rebuild_script_path()),
    "can_hash_sync_targets": can_hash_sync_targets(),
  }


# Backward-compatible names used by older tools/tests.
def has_panda_tici() -> bool:
  return has_panda_tici_tree()


def has_pandad_tici() -> bool:
  return has_pandad_tici_tree()
