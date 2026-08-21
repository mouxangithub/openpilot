"""Dev CI helpers: pytest and scons (PC / stationary only)."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any

from ai.system.paths import openpilot_root


def _run(cmd: list[str], *, timeout: int = 600, cwd: str | None = None) -> dict[str, Any]:
  try:
    proc = subprocess.run(
      cmd,
      capture_output=True,
      text=True,
      timeout=timeout,
      cwd=cwd or str(openpilot_root()),
    )
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if len(out) > 10000:
      out = out[:10000] + "\n... (truncated)"
    if len(err) > 4000:
      err = err[:4000] + "\n... (truncated)"
    return {
      "ok": proc.returncode == 0,
      "returncode": proc.returncode,
      "stdout": out,
      "stderr": err,
      "command": " ".join(cmd[:8]),
    }
  except subprocess.TimeoutExpired:
    return {"ok": False, "error": f"Command timed out after {timeout}s"}
  except Exception as e:
    return {"ok": False, "error": str(e)}


def run_pytest(
  *,
  path: str = "ai/tests",
  keyword: str = "",
  max_fail: int = 1,
) -> dict[str, Any]:
  """Run pytest on a path (default ai/tests)."""
  py = shutil.which("py") or shutil.which("python3") or shutil.which("python")
  if not py:
    return {"ok": False, "error": "python not found"}
  target = (path or "ai/tests").strip()
  if ".." in target:
    return {"ok": False, "error": "invalid path"}
  args = [py, "-m", "pytest", target, "-q", f"--maxfail={max(1, int(max_fail or 1))}"]
  kw = (keyword or "").strip()
  if kw:
    args.extend(["-k", kw])
  return _run(args, timeout=900)


def run_scons_build(
  *,
  target: str = "",
  jobs: int | None = None,
) -> dict[str, Any]:
  """Run scons in openpilot root (optional target, e.g. selfdrive)."""
  scons = shutil.which("scons")
  if not scons:
    return {"ok": False, "error": "scons not installed"}
  args = [scons]
  j = jobs or min(8, (os.cpu_count() or 4))
  args.append(f"-j{j}")
  tgt = (target or "").strip()
  if tgt and ".." not in tgt:
    args.append(tgt)
  return _run(args, timeout=3600)
