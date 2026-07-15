"""Device power and manager control for op助手."""

from __future__ import annotations

import os
import subprocess
import time
from typing import Any

from ai.system.paths import is_comma_device, openpilot_root


def reboot_device(*, delay_sec: int = 3) -> dict[str, Any]:
  delay_sec = max(0, min(int(delay_sec), 30))
  if not is_comma_device() and os.name == "nt":
    return {"ok": False, "error": "reboot_device is for comma/AGNOS device only"}
  cmd = f"sleep {delay_sec} && sudo reboot"
  try:
    subprocess.Popen(
      cmd,
      shell=True,
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
      start_new_session=True,
    )
  except OSError as e:
    return {"ok": False, "error": str(e)}
  return {
    "ok": True,
    "message": f"Reboot scheduled in {delay_sec}s",
    "hint": "Device will disconnect; reconnect after boot.",
  }


def shutdown_device(*, delay_sec: int = 5) -> dict[str, Any]:
  delay_sec = max(0, min(int(delay_sec), 60))
  if not is_comma_device() and os.name == "nt":
    return {"ok": False, "error": "shutdown_device is for comma/AGNOS device only"}
  cmd = f"sleep {delay_sec} && sudo poweroff"
  try:
    subprocess.Popen(
      cmd,
      shell=True,
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
      start_new_session=True,
    )
  except OSError as e:
    return {"ok": False, "error": str(e)}
  return {
    "ok": True,
    "message": f"Shutdown scheduled in {delay_sec}s",
    "hint": "Ignition off / parking recommended before shutdown.",
  }


def _manager_running() -> bool:
  try:
    r = subprocess.run(
      ["pgrep", "-f", "system/manager/manager.py"],
      capture_output=True,
      text=True,
      timeout=5,
    )
    return r.returncode == 0
  except Exception:
    return False


def manager_control(
  action: str,
  *,
  use_webcam: bool = False,
  rebuild: bool = False,
  timeout: int = 600,
) -> dict[str, Any]:
  action = (action or "").strip().lower()
  root = openpilot_root()
  manager_py = root / "system" / "manager" / "manager.py"
  timeout = max(30, min(int(timeout), 1800))

  if action == "status":
    return {
      "ok": True,
      "running": _manager_running(),
      "manager_script": str(manager_py),
      "openpilot_root": str(root),
    }

  if action == "stop":
    subprocess.run(["pkill", "-f", "system/manager/manager.py"], check=False)
    time.sleep(0.5)
    return {"ok": True, "message": "Sent stop to manager", "running": _manager_running()}

  if action == "restart":
    subprocess.run(["pkill", "-f", "system/manager/manager.py"], check=False)
    time.sleep(1.0)
    action = "start"

  if action == "rebuild":
    try:
      proc = subprocess.run(
        ["scons", "-u", "-j8"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=timeout,
      )
      out = (proc.stdout or "")[-4000:]
      err = (proc.stderr or "")[-2000:]
      return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout_tail": out,
        "stderr_tail": err,
        "hint": "Run manager_control start after successful rebuild.",
      }
    except subprocess.TimeoutExpired:
      return {"ok": False, "error": f"scons timed out after {timeout}s"}
    except FileNotFoundError:
      return {"ok": False, "error": "scons not found; install build tools first"}

  if action == "start":
    if not manager_py.is_file():
      return {"ok": False, "error": f"manager.py not found: {manager_py}"}
    env = os.environ.copy()
    if use_webcam:
      env["USE_WEBCAM"] = "1"
    if rebuild:
      build = manager_control("rebuild", timeout=timeout)
      if not build.get("ok"):
        return build
    log_path = root / "ai_manager_launch.log"
    try:
      with log_path.open("a", encoding="utf-8") as logf:
        logf.write(f"\n--- launch {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        proc = subprocess.Popen(
          ["python", str(manager_py)],
          cwd=str(root),
          env=env,
          stdout=logf,
          stderr=subprocess.STDOUT,
          start_new_session=True,
        )
    except OSError as e:
      return {"ok": False, "error": str(e)}
    time.sleep(1.5)
    return {
      "ok": True,
      "pid": proc.pid,
      "running": _manager_running(),
      "log": str(log_path),
      "use_webcam": use_webcam,
    }

  return {
    "ok": False,
    "error": "action must be one of: status, start, stop, restart, rebuild",
  }
