"""Device health and Panda status for comma/AGNOS + PC dev."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ai.system.paths import is_comma_device, openpilot_root
from ai.tools.domains.platform.system_info_tools import get_build_info


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

  try:
    from ai.tools.domains.platform.panda_flash_tools import list_all_pandas

    usb = list_all_pandas()
    if usb.get("ok"):
      out["usb_all"] = usb.get("pandas", [])
      out["usb_f4"] = usb.get("f4_pandas", [])
      out["usb_h7"] = usb.get("h7_pandas", [])
      out["multi_panda"] = usb.get("multi_panda")
      out["pandad_snapshot"] = usb.get("pandad")
      out["firmware_path"] = usb.get("firmware_path")
      out["firmware_exists"] = usb.get("firmware_exists")
  except Exception as e:
    out["usb_scan_error"] = str(e)

  try:
    from ai.tsk.lib.panda_connect import tici_info

    info = tici_info()
    out["device_type"] = info.get("device_type")
    out["panda_backend"] = info.get("panda_backend")
    out["pandad_process"] = info.get("pandad_process")
    if info.get("device_type") == "tici" and info.get("tici_dos"):
      out["dos_note"] = "C3 DOS: F4 firmware is panda/board/obj/panda.bin.signed"
  except Exception:
    pass

  if shutil.which("lsusb"):
    out["lsusb"] = _run(["lsusb"])
  for dev in ("/dev/panda", "/dev/panda0"):
    if os.path.exists(dev):
      out["dev_path"] = dev
      break

  if not out["pandas"] and not out.get("dev_path"):
    out["hint"] = "NO PANDA: run panda_recovery_hint → tsk_restart_pandad or recover_dos_panda (skill c3-dos-panda)."
  elif not out["pandas"] and out.get("usb_all"):
    multi = out.get("multi_panda") or {}
    pandad = out.get("pandad_snapshot") or {}
    if multi.get("count", 0) >= 2:
      out["hint"] = (
        "USB 可见多 Panda 但 pandaStates 空：查 pandad 是否崩溃循环 "
        "(USBErrorBusy)；rebuild_pandad(confirm=true) + reboot。"
      )
      if multi.get("heterogeneous_f4_h7"):
        out["hint"] += " 场景：内置 F4 + 外接红熊 H7。"
    elif pandad.get("possible_crash_loop"):
      out["hint"] = "pandad 可能崩溃循环：grep_log USBErrorBusy → rebuild_pandad(confirm=true)。"
    elif out.get("usb_f4"):
      out["hint"] = "USB F4 seen but pandaStates empty: tsk_restart_pandad(confirm=true) or recover_dos_panda."

  return out
