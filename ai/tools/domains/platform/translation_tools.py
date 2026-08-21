"""Translation helpers for the op 鍔╂墜 project.

Provides safe wrappers around the Chinese translation scripts and guards against
running them on prebuilt/packaged branches where translation sources cannot be
regenerated.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from shutil import which
from typing import Any

from ai.system.paths import openpilot_root, openpilot_source_root


def _repo_root() -> Path:
  return openpilot_root()


def _src_root() -> Path:
  return openpilot_source_root()


def can_update_translations() -> dict[str, Any]:
  """Check whether this branch can regenerate translation files.

  Prebuilt/packaged branches may ship .po files without the source UI .py files
  or without SConstruct, in which case updating translations is not safe.
  """
  root = _repo_root()
  src = _src_root()

  sconstruct = root / "SConstruct"
  update_script = src / "selfdrive" / "ui" / "translations" / "update_translations.py"
  merge_script = root / "ai" / "scripts" / "merge_zh_translations.py"
  supplement_script = root / "ai" / "scripts" / "supplement_zh_translations.py"

  ui_sources = [
    src / "selfdrive" / "ui",
    src / "system" / "ui",
  ]
  has_ui_sources = any(d.is_dir() and list(d.rglob("*.py")) for d in ui_sources)

  checks = {
    "sconstruct_present": sconstruct.is_file(),
    "update_script_present": update_script.is_file(),
    "merge_script_present": merge_script.is_file(),
    "supplement_script_present": supplement_script.is_file(),
    "ui_sources_present": has_ui_sources,
    "scons_available": which("scons") is not None,
  }
  checks["can_update"] = (
    checks["sconstruct_present"]
    and checks["update_script_present"]
    and checks["merge_script_present"]
    and checks["supplement_script_present"]
    and checks["ui_sources_present"]
  )
  return checks


def _guard() -> None:
  status = can_update_translations()
  if not status["can_update"]:
    missing = [k for k, v in status.items() if k != "can_update" and not v]
    raise RuntimeError(
      "Translation update not available on this branch. "
      f"Missing/unavailable: {', '.join(missing)}. "
      "Prebuilt or packaged branches cannot regenerate translation files."
    )


def _run_script(script: Path, *args: str) -> dict[str, Any]:
  if not script.is_file():
    return {"ok": False, "error": f"script not found: {script}"}
  env = os.environ.copy()
  env["PYTHONPATH"] = str(_repo_root()) + (
    f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else ""
  )
  proc = subprocess.run(
    [sys.executable, str(script), *args],
    cwd=str(_repo_root()),
    env=env,
    capture_output=True,
    text=True,
  )
  return {
    "ok": proc.returncode == 0,
    "returncode": proc.returncode,
    "stdout": proc.stdout,
    "stderr": proc.stderr,
  }


def merge_zh_translations() -> dict[str, Any]:
  """Run ai/scripts/merge_zh_translations.py to extract strings and merge zh po."""
  _guard()
  script = _repo_root() / "ai" / "scripts" / "merge_zh_translations.py"
  return _run_script(script)


def supplement_zh_translations() -> dict[str, Any]:
  """Run ai/scripts/supplement_zh_translations.py to apply hard-coded zh strings."""
  _guard()
  script = _repo_root() / "ai" / "scripts" / "supplement_zh_translations.py"
  return _run_script(script)


def update_all_zh_translations() -> dict[str, Any]:
  """Run merge then supplement for Chinese translations."""
  _guard()
  merge = merge_zh_translations()
  if not merge["ok"]:
    return merge
  supplement = supplement_zh_translations()
  return {
    "ok": supplement["ok"],
    "merge": merge,
    "supplement": supplement,
  }


def get_translation(msgid: str, lang: str = "zh-CHS") -> str | None:
  """Return a hard-coded Chinese translation for msgid if available.

  Falls back to the Traditional Chinese mapping when lang is zh-CHT.
  """
  try:
    from ai.scripts.supplement_zh_translations import ZH_CHS, ZH_CHT
  except ImportError:
    return None
  mapping = ZH_CHT if lang == "zh-CHT" else ZH_CHS
  return mapping.get(msgid)


def translation_status() -> dict[str, Any]:
  """Human-readable status for AI tools / diagnostics."""
  status = can_update_translations()
  root = _repo_root()
  src = _src_root()
  return {
    **status,
    "repo_root": str(root),
    "source_root": str(src),
    "po_files": [
      str(p) for p in (src / "selfdrive" / "ui" / "translations").glob("app_*.po")
    ],
  }