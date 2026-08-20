"""Read-only SSH exec for comma device diagnostics."""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any

_ALLOWED_PREFIXES = (
  "df ",
  "free ",
  "uptime",
  "uname ",
  "ls ",
  "ls\n",
  "cat /data/openpilot/",
  "cat /data/log/",
  "git -C /data/openpilot status",
  "git -C /data/openpilot rev-parse",
  "git -C /data/openpilot branch",
  "wc ",
  "head ",
  "tail ",
  "ps ",
  "top -bn1",
  "ip addr",
  "ping -c ",
)

_FORBIDDEN = re.compile(
  r"(rm\s|reboot|shutdown|dd\s|mkfs|chmod\s|chown\s|>\s|>>\s|sudo\s|curl\s|wget\s)",
  re.I,
)


def ssh_readonly_exec(
  *,
  host: str,
  command: str,
  identity: str = "",
  timeout: int = 30,
) -> dict[str, Any]:
  """Run a whitelisted read-only command over SSH."""
  host = (host or "").strip()
  cmd = (command or "").strip()
  if not host or not cmd:
    return {"ok": False, "error": "host and command required"}
  if _FORBIDDEN.search(cmd):
    return {"ok": False, "error": "command blocked by safety policy"}
  if not any(cmd.startswith(p) or cmd == p.rstrip() for p in _ALLOWED_PREFIXES):
    return {
      "ok": False,
      "error": "command not in read-only allowlist",
      "hint": "Allowed prefixes: df, free, uptime, ls, cat /data/openpilot/, git status, ps, ip addr, ping -c",
    }
  ssh = shutil.which("ssh")
  if not ssh:
    return {"ok": False, "error": "ssh not installed"}
  args = [ssh, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", f"ConnectTimeout={min(timeout, 15)}"]
  ident = (identity or "").strip()
  if ident:
    args.extend(["-i", ident])
  args.append(f"comma@{host}")
  args.append(cmd)
  try:
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if len(out) > 8000:
      out = out[:8000] + "\n... (truncated)"
    return {
      "ok": proc.returncode == 0,
      "returncode": proc.returncode,
      "stdout": out,
      "stderr": err[:2000],
      "host": host,
      "command": cmd,
    }
  except subprocess.TimeoutExpired:
    return {"ok": False, "error": f"SSH timed out after {timeout}s"}
  except Exception as e:
    return {"ok": False, "error": str(e)}
