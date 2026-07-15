"""Network diagnostics for comma device / PC dev host."""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any

from ai.system.host_env import get_host_environment, is_pc_dev
from ai.system.paths import is_comma_device, openpilot_root

_IP_RE = re.compile(r"^[\w.\-]+$")


def _run(cmd: list[str], *, timeout: int = 12) -> dict[str, Any]:
  try:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    return {
      "ok": proc.returncode == 0,
      "returncode": proc.returncode,
      "stdout": out[:4000],
      "stderr": err[:2000],
    }
  except subprocess.TimeoutExpired:
    return {"ok": False, "error": "timeout"}
  except FileNotFoundError:
    return {"ok": False, "error": "command not found"}
  except Exception as e:
    return {"ok": False, "error": str(e)}


def network_diagnostics(
  *,
  device_ip: str = "",
  ping_count: int = 3,
) -> dict[str, Any]:
  """WiFi / SSH / DNS / comma auth connectivity snapshot."""
  ping_count = max(1, min(int(ping_count), 10))
  host = get_host_environment()
  out: dict[str, Any] = {
    "ok": True,
    "host": host,
    "is_comma_device": is_comma_device(),
    "is_pc_dev": is_pc_dev(),
    "checks": {},
  }

  if shutil.which("ip"):
    out["checks"]["ip_addr"] = _run(["ip", "-br", "addr"])
  if shutil.which("iwconfig"):
    out["checks"]["wifi"] = _run(["iwconfig"])
  elif shutil.which("nmcli"):
    out["checks"]["wifi"] = _run(["nmcli", "-t", "dev", "wifi"])

  if shutil.which("ping"):
    targets = ["8.8.8.8", "1.1.1.1"]
    for t in targets:
      out["checks"][f"ping_{t}"] = _run(
        ["ping", "-c", str(ping_count), "-W", "2", t],
        timeout=ping_count * 3 + 5,
      )

  ip = (device_ip or "").strip()
  if ip:
    if not _IP_RE.match(ip) or ".." in ip:
      out["checks"]["device_ping"] = {"ok": False, "error": "invalid device_ip"}
    elif shutil.which("ping"):
      out["checks"]["device_ping"] = _run(
        ["ping", "-c", str(ping_count), "-W", "2", ip],
        timeout=ping_count * 3 + 5,
      )
    if shutil.which("ssh"):
      out["checks"]["device_ssh"] = _run(
        [
          "ssh",
          "-o", "BatchMode=yes",
          "-o", "ConnectTimeout=5",
          "-o", "StrictHostKeyChecking=accept-new",
          f"comma@{ip}",
          "echo ok",
        ],
        timeout=15,
      )

  try:
    from ai.tools.comma_cloud_tools import comma_auth_status
    out["checks"]["comma_auth"] = comma_auth_status()
  except Exception as e:
    out["checks"]["comma_auth"] = {"ok": False, "error": str(e)}

  issues: list[str] = []
  for name, chk in out["checks"].items():
    if isinstance(chk, dict) and chk.get("ok") is False and "error" in chk:
      issues.append(f"{name}: {chk['error']}")
    elif name.startswith("ping_") and isinstance(chk, dict) and not chk.get("ok"):
      issues.append(f"{name} failed")

  out["issues"] = issues
  out["healthy"] = len(issues) == 0
  out["openpilot_root"] = str(openpilot_root())
  out["hint"] = "Use pc_devsync_status after SSH works; comma_auth for route upload."
  return out
