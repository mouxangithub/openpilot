"""Developer panel helpers (error log)."""

from __future__ import annotations

import datetime
import os
from pathlib import Path
from typing import Any


def _error_log_path() -> Path:
  try:
    from openpilot.common.hardware import PC
    from openpilot.common.hardware.hw import Paths
    root = Paths.crash_log_root()
  except Exception:
    root = "/data/crash"
  return Path(root) / "error.log"


def developer_error_log() -> dict[str, Any]:
  path = _error_log_path()
  if os.environ.get("WEBUI_DEV_PC") == "1":
    return {
      "ok": True,
      "exists": False,
      "html": "<p>No error log on PC preview.</p>",
      "dev_pc": True,
    }
  try:
    if not path.is_file():
      return {"ok": True, "exists": False, "html": "<p>No error log found.</p>"}
    mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime)
    header = f"<b>{mtime.strftime('%d-%b-%Y %H:%M:%S').upper()}</b><br><br>"
    try:
      body = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
      body = str(exc)
    escaped = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return {"ok": True, "exists": True, "html": header + f"<pre style='white-space:pre-wrap'>{escaped}</pre>"}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def developer_delete_error_log() -> dict[str, Any]:
  path = _error_log_path()
  try:
    if path.is_file():
      path.unlink()
    return {"ok": True}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}
