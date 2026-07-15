"""Device health and Panda status for comma/AGNOS + PC dev."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ai.system.paths import is_comma_device, openpilot_root
from ai.tools.system_info_tools import get_build_info


def _run(cmd: list[str], *, timeout: int = 10) -> dict[str, Any]:
  try:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return {
      "ok": proc.returncode == 0,
      "stdout": (proc.stdout or "").strip()[:3000],
      "stderr": (proc.stderr or "").strip()[:1000],
    }
  except Exception as e:
    return {"ok": False, "error": str(e)}


def device_health() -> dict[str, Any]:
  """Disk, thermal, version, platform snapshot."""
  info = get_build_info()
  out: dict[str, Any] = {
    "ok": True,
    "is_comma_device": is_comma_device(),
    "platform": platform.platform(),
    "build": info.get("git"),
    "openpilot_root": str(openpilot_root()),
  }

  try:
    from openpilot.common.params import Params
    p = Params()
    for key in ("Version", "AGNOSVersion", "DongleId", "HardwareSerial"):
      raw = p.get(key)
      if raw is not None:
        out[key] = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw)
  except Exception as e:
    out["params_warning"] = str(e)

  if shutil.which("df"):
    out["disk"] = _run(["df", "-h", "/data"] if is_comma_device() else ["df", "-h", "."])
  if shutil.which("free"):
    out["memory"] = _run(["free", "-h"])
  if is_comma_device() and Path("/sys/class/thermal").is_dir():
    temps: list[dict[str, Any]] = []
    try:
      for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*"))[:8]:
        tfile = zone / "temp"
        if tfile.is_file():
          raw = tfile.read_text().strip()
          temps.append({"zone": zone.name, "celsius": round(int(raw) / 1000, 1)})
    except Exception:
      pass
    if temps:
      out["thermal"] = temps
  if is_comma_device():
    try:
      from ai.tsk.lib.panda_connect import tici_info

      info = tici_info()
      if info.get("device_type"):
        out["board"] = info["device_type"]
      if info.get("product_label"):
        out["product_label"] = info["product_label"]
      out["panda_backend"] = info.get("panda_backend")
      out["pandad_process"] = info.get("pandad_process")
    except Exception:
      if os.path.isfile("/TICI"):
        out["board"] = "tici"
      elif os.path.isfile("/AGNOS"):
        out["board"] = "agnos"

  return out


def panda_status(get_state_reader=None) -> dict[str, Any]:
  """Panda USB / cereal pandaStates snapshot."""
  out: dict[str, Any] = {"ok": True, "pandas": []}

  if get_state_reader is not None:
    try:
      reader = get_state_reader()
      reader.update(timeout=0)
      full = reader.latest()
      if isinstance(full, dict):
        for ps in full.get("pandaStates") or []:
          out["pandas"].append(ps)
    except Exception as e:
      out["live_error"] = str(e)

  if shutil.which("lsusb"):
    out["lsusb"] = _run(["lsusb"])
  for dev in ("/dev/panda", "/dev/panda0"):
    if os.path.exists(dev):
      out["dev_path"] = dev
      break

  if not out["pandas"] and not out.get("dev_path"):
    out["hint"] = "Connect Panda or ensure manager is running for live pandaStates."

  return out
