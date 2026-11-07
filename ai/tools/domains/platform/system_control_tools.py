"""Device power and manager control for op助手."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Callable

from ai.system.paths import is_comma_device, openpilot_root, source_path

_MANAGER_PATTERN = "manager/manager.py"


async def reboot_device(*, delay_sec: int = 3) -> dict[str, Any]:
  delay_sec = max(0, min(int(delay_sec), 30))
  if not is_comma_device() and os.name == "nt":
    return {"ok": False, "error": "reboot_device is for comma/AGNOS device only"}
  cmd = f"sleep {delay_sec} && sudo reboot"
  try:
    await asyncio.create_subprocess_shell(
      cmd,
      stdout=asyncio.subprocess.DEVNULL,
      stderr=asyncio.subprocess.DEVNULL,
      start_new_session=True,
    )
  except OSError as e:
    return {"ok": False, "error": str(e)}
  return {
    "ok": True,
    "message": f"Reboot scheduled in {delay_sec}s",
    "hint": "Device will disconnect; reconnect after boot.",
  }


async def shutdown_device(*, delay_sec: int = 5) -> dict[str, Any]:
  delay_sec = max(0, min(int(delay_sec), 60))
  if not is_comma_device() and os.name == "nt":
    return {"ok": False, "error": "shutdown_device is for comma/AGNOS device only"}
  cmd = f"sleep {delay_sec} && sudo poweroff"
  try:
    await asyncio.create_subprocess_shell(
      cmd,
      stdout=asyncio.subprocess.DEVNULL,
      stderr=asyncio.subprocess.DEVNULL,
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
    from ai.tsk.lib.panda_connect import is_manager_running

    return is_manager_running()
  except Exception:
    return False


async def manager_control(
  action: str,
  *,
  use_webcam: bool = False,
  rebuild: bool = False,
  timeout: int = 600,
  is_cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
  action = (action or "").strip().lower()
  root = openpilot_root()
  manager_py = source_path("system", "manager", "manager.py")
  timeout = max(30, min(int(timeout), 1800))

  if action == "status":
    return {
      "ok": True,
      "running": _manager_running(),
      "manager_script": str(manager_py),
      "openpilot_root": str(root),
    }

  async def _pkill(pattern: str) -> None:
    proc = await asyncio.create_subprocess_exec("pkill", "-f", pattern)
    await proc.wait()

  if action == "stop":
    await _pkill(_MANAGER_PATTERN)
    await asyncio.sleep(0.5)
    return {"ok": True, "message": "Sent stop to manager", "running": _manager_running()}

  if action == "restart":
    await _pkill(_MANAGER_PATTERN)
    await asyncio.sleep(1.0)
    action = "start"

  if action == "rebuild":
    if is_cancelled and is_cancelled():
      return {"ok": False, "error": "rebuild cancelled before starting"}
    try:
      proc = await asyncio.create_subprocess_exec(
        "scons", "-u", "-j8",
        cwd=str(root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
      )
      try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
      except asyncio.TimeoutError:
        try:
          proc.kill()
        except ProcessLookupError:
          pass
        await proc.wait()
        return {"ok": False, "error": f"scons timed out after {timeout}s"}
      out = (stdout.decode("utf-8", errors="replace") or "")[-4000:]
      err = (stderr.decode("utf-8", errors="replace") or "")[-2000:]
      return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout_tail": out,
        "stderr_tail": err,
        "hint": "Run manager_control start after successful rebuild.",
      }
    except FileNotFoundError:
      return {"ok": False, "error": "scons not found; install build tools first"}
    except asyncio.CancelledError:
      try:
        proc.kill()
      except ProcessLookupError:
        pass
      await proc.wait()
      raise

  if action == "start":
    if not manager_py.is_file():
      return {"ok": False, "error": f"manager.py not found: {manager_py}"}
    env = os.environ.copy()
    if use_webcam:
      env["USE_WEBCAM"] = "1"
    if rebuild:
      build = await manager_control("rebuild", timeout=timeout, is_cancelled=is_cancelled)
      if not build.get("ok"):
        return build
    log_path = root / "ai_manager_launch.log"
    try:
      with log_path.open("a", encoding="utf-8") as logf:
        logf.write(f"\n--- launch {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        proc = await asyncio.create_subprocess_exec(
          "python", str(manager_py),
          cwd=str(root),
          env=env,
          stdout=logf,
          stderr=asyncio.subprocess.STDOUT,
          start_new_session=True,
        )
    except OSError as e:
      return {"ok": False, "error": str(e)}
    await asyncio.sleep(1.5)
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
