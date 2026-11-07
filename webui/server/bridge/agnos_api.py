"""AGNOS (comma OS) update status and headless install via WebUI."""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_THREAD: threading.Thread | None = None

_DEV_PARTITIONS = ("xbl", "abl", "boot", "system", "vendor")


def _openpilot_dir() -> Path:
  try:
    from openpilot.common.basedir import BASEDIR
    return Path(BASEDIR)
  except Exception:
    root = Path(os.environ.get("OPENPILOT_ROOT") or Path(__file__).resolve().parents[3])
    if (root / "openpilot").is_dir():
      return root / "openpilot"
    return root


def _is_dev_pc() -> bool:
  return os.environ.get("WEBUI_DEV_PC") == "1"


def _state_path() -> Path:
  if _is_dev_pc():
    base = os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp"
    return Path(base) / "agnos_webui_dev_state.json"
  return Path("/tmp/agnos_webui_state.json")


def _log_path() -> Path:
  if _is_dev_pc():
    base = os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp"
    return Path(base) / "agnos_webui_dev.log"
  return Path("/tmp/agnos_webui.log")


def _monorepo_root() -> str:
  base = _openpilot_dir()
  if base.name == "openpilot" and (base.parent / "launch_env.sh").is_file():
    return str(base.parent)
  return str(base)


def _read_version(path: str) -> str:
  try:
    return Path(path).read_text(encoding="utf-8").strip()
  except OSError:
    return ""


def _target_agnos_version() -> str:
  env = (os.getenv("AGNOS_VERSION") or "").strip()
  if env:
    return env
  launch_env = Path(_monorepo_root()) / "launch_env.sh"
  try:
    for line in launch_env.read_text(encoding="utf-8").splitlines():
      line = line.strip()
      if line.startswith("export AGNOS_VERSION="):
        return line.split("=", 1)[1].strip().strip('"').strip("'")
  except OSError:
    pass
  return ""


def resolve_agnos_manifest() -> str:
  from openpilot.common.hardware.comma.agnos import default_agnos_manifest_path
  return default_agnos_manifest_path(_monorepo_root())


def _agnos_py() -> str:
  return str(_openpilot_dir() / "common" / "hardware" / "comma" / "agnos.py")


def _read_state() -> dict[str, Any]:
  path = _state_path()
  try:
    if path.is_file():
      return json.loads(path.read_text(encoding="utf-8"))
  except Exception:
    pass
  return {"status": "idle", "message": "", "progress": 0}


def _write_state(**kwargs: Any) -> dict[str, Any]:
  state = _read_state()
  state.update(kwargs)
  state["updated_at"] = time.time()
  try:
    _state_path().write_text(json.dumps(state), encoding="utf-8")
  except OSError:
    pass
  return state


def _is_job_running() -> bool:
  return _read_state().get("status") == "running"


def _dev_sim() -> dict[str, Any]:
  from webui.dev.mock_runtime import SIM
  return SIM


def _dev_target_version() -> str:
  sim = _dev_sim()
  target = str(sim.get("agnos_target_version") or "").strip()
  if target:
    return target
  return _target_agnos_version() or "12.0.0"


def _dev_agnos_snapshot() -> dict[str, Any]:
  sim = _dev_sim()
  job = _read_state()
  current = str(sim.get("agnos_current_version") or "11.9.9")
  target = _dev_target_version()
  version_mismatch = bool(sim.get("agnos_update_required", False))
  ready_to_reboot = bool(sim.get("agnos_ready_to_reboot")) or job.get("status") == "done"
  update_required = version_mismatch or ready_to_reboot
  log_tail = ""
  try:
    lp = _log_path()
    if lp.is_file():
      log_tail = lp.read_text(encoding="utf-8", errors="replace")[-4000:]
  except OSError:
    pass
  return {
    "ok": True,
    "available": True,
    "dev_pc": True,
    "simulated": True,
    "current_version": current,
    "target_version": target,
    "update_required": update_required,
    "ready_to_reboot": ready_to_reboot,
    "version_mismatch": version_mismatch,
    "manifest": "dev-simulation",
    "verify_error": "",
    "job": job,
    "log_tail": log_tail,
    "install_running": job.get("status") == "running",
    "progress": job.get("progress", 0) if job.get("status") == "running" else None,
  }


def _agnos_pending_status() -> dict[str, Any]:
  """Shared AGNOS update detection for /api/opui/agnos and home screen."""
  if _is_dev_pc():
    snap = _dev_agnos_snapshot()
    return {
      "available": bool(snap.get("available")),
      "update_required": bool(snap.get("update_required")),
      "ready_to_reboot": bool(snap.get("ready_to_reboot")),
      "current_version": snap.get("current_version", ""),
      "target_version": snap.get("target_version", ""),
      "verify_error": snap.get("verify_error", ""),
      "version_mismatch": bool(snap.get("version_mismatch", snap.get("update_required"))),
    }

  if not os.path.isfile("/AGNOS"):
    return {
      "available": False,
      "update_required": False,
      "ready_to_reboot": False,
      "current_version": "",
      "target_version": "",
      "verify_error": "",
      "version_mismatch": False,
    }

  current = _read_version("/VERSION")
  target = _target_agnos_version()
  manifest = resolve_agnos_manifest()
  ready_to_reboot = False
  verify_error = ""

  if os.path.isfile(manifest):
    try:
      from openpilot.common.hardware.comma.agnos import get_target_slot_number, verify_agnos_update
      ready_to_reboot = verify_agnos_update(manifest, get_target_slot_number())
    except Exception as exc:
      verify_error = str(exc)

  version_mismatch = bool(target) and current != target
  # Show UI only when the OS version string lags. If /VERSION already matches
  # AGNOS_VERSION, treat the update as applied even if the inactive slot still
  # verifies, to avoid repeated false-positive prompts after reboot.
  update_required = version_mismatch

  return {
    "available": True,
    "update_required": update_required,
    "ready_to_reboot": ready_to_reboot,
    "current_version": current,
    "target_version": target,
    "verify_error": verify_error,
    "version_mismatch": version_mismatch,
  }


def agnos_snapshot() -> dict[str, Any]:
  if _is_dev_pc():
    return _dev_agnos_snapshot()
  pending = _agnos_pending_status()
  if not pending["available"]:
    return {"ok": True, "available": False}

  manifest = resolve_agnos_manifest()
  job = _read_state()
  log_tail = ""
  try:
    lp = _log_path()
    if lp.is_file():
      log_tail = lp.read_text(encoding="utf-8", errors="replace")[-4000:]
  except OSError:
    pass

  return {
    "ok": True,
    "available": True,
    "current_version": pending["current_version"],
    "target_version": pending["target_version"],
    "update_required": pending["update_required"],
    "ready_to_reboot": pending["ready_to_reboot"],
    "version_mismatch": pending["version_mismatch"],
    "manifest": manifest,
    "verify_error": pending["verify_error"],
    "job": job,
    "log_tail": log_tail,
    "install_running": job.get("status") == "running",
    "progress": job.get("progress", 0) if job.get("status") == "running" else None,
  }


_INSTALL_RE = re.compile(r"Installing (\S+):\s*(\d+)")
_DOWNLOAD_RE = re.compile(r"Downloading and writing (\S+)")
_ALREADY_RE = re.compile(r"Already flashed (\S+)")


def _manifest_partitions(manifest: str) -> list[str]:
  from openpilot.common.hardware.comma.agnos import restore_partitions
  with open(manifest, encoding="utf-8") as f:
    parts = restore_partitions(json.load(f))
  return [p["name"] for p in parts]


def _overall_progress(partition_names: list[str], partition: str, pct: int) -> int:
  n = len(partition_names) or 1
  try:
    idx = partition_names.index(partition)
  except ValueError:
    return min(100, max(0, pct))
  return min(100, int((idx * 100 + pct) / n))


def _partition_base_progress(partition_names: list[str], partition: str) -> int:
  n = len(partition_names) or 1
  try:
    idx = partition_names.index(partition)
  except ValueError:
    return 0
  return min(100, int(idx * 100 / n))


def _progress_from_log_line(line: str, partition_names: list[str]) -> tuple[str, int | None]:
  line = line.strip()
  if not line:
    return "", None

  if ":root:" in line:
    line = line.split(":root:", 1)[-1].strip()

  m = _INSTALL_RE.search(line)
  if m:
    name, pct = m.group(1), int(m.group(2))
    return f"Installing {name}", _overall_progress(partition_names, name, pct)

  m = _DOWNLOAD_RE.search(line)
  if m:
    name = m.group(1)
    return f"Downloading {name}", _partition_base_progress(partition_names, name)

  m = _ALREADY_RE.search(line)
  if m:
    name = m.group(1)
    n = len(partition_names) or 1
    try:
      idx = partition_names.index(name)
      overall = min(100, int((idx + 1) * 100 / n))
    except ValueError:
      overall = None
    return f"{name} up to date", overall

  if "Verification failed" in line or "Flashing AGNOS" in line:
    return "Preparing AGNOS flash...", 0

  if "Swap successful" in line or "Verification succeeded" in line:
    return "Finalizing AGNOS update...", 99

  if line.startswith("Installing ") and ":" in line:
    return line, None

  return line, None


def _parse_progress_line(line: str, partition_names: list[str] | None = None) -> tuple[str, int | None]:
  return _progress_from_log_line(line, partition_names or [])


def _schedule_dev_reboot(seconds: float = 5.0) -> None:
  sim = _dev_sim()
  sim["agnos_sim_rebooting"] = True
  sim["agnos_sim_reboot_until"] = time.time() + seconds
  sim["agnos_ready_to_reboot"] = False
  sim["agnos_update_required"] = False
  sim["agnos_current_version"] = _dev_target_version()


def _run_dev_agnos_install() -> None:
  parts = _DEV_PARTITIONS
  n = len(parts) or 1
  _write_state(
    status="running",
    message="Starting AGNOS update (simulated)...",
    progress=0,
    partition_total=n,
  )
  try:
    _log_path().write_text("AGNOS dev simulation\n", encoding="utf-8")
  except OSError:
    pass

  time.sleep(0.4)
  for idx, name in enumerate(parts):
    base = int(idx * 100 / n)
    _write_state(status="running", message=f"Downloading {name}", progress=base)
    time.sleep(0.2)
    for step in range(0, 101, 25):
      overall = min(100, int((idx * 100 + step) / n))
      _write_state(status="running", message=f"Installing {name}", progress=overall)
      time.sleep(0.18)

  _write_state(status="done", message="AGNOS update complete — reboot to apply", progress=100)
  sim = _dev_sim()
  sim["agnos_ready_to_reboot"] = True
  time.sleep(0.8)
  _schedule_dev_reboot(5.0)


def _run_agnos_swap() -> None:
  manifest = resolve_agnos_manifest()
  agnos_py = _agnos_py()
  partition_names: list[str] = []
  try:
    partition_names = _manifest_partitions(manifest)
  except Exception:
    pass

  _write_state(
    status="running",
    message="Starting AGNOS update...",
    progress=0,
    partition_total=len(partition_names),
  )
  try:
    _log_path().write_text("", encoding="utf-8")
  except OSError:
    pass

  try:
    proc = subprocess.Popen(
      [agnos_py, "--swap", manifest],
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      text=True,
      bufsize=1,
    )
  except Exception as exc:
    _write_state(status="failed", message=str(exc), progress=0)
    return

  assert proc.stdout is not None
  with _log_path().open("a", encoding="utf-8") as logf:
    for line in proc.stdout:
      logf.write(line)
      logf.flush()
      msg, pct = _parse_progress_line(line, partition_names)
      if pct is not None:
        _write_state(status="running", message=msg, progress=pct, partition_total=len(partition_names))
      elif msg:
        _write_state(status="running", message=msg)

  code = proc.wait()
  if code == 0:
    _write_state(status="done", message="AGNOS update complete — reboot to apply", progress=100)
    try:
      from openpilot.common.hardware import HARDWARE
      HARDWARE.reboot()
    except Exception:
      pass
  else:
    _write_state(status="failed", message=f"AGNOS update failed (exit {code})", progress=_read_state().get("progress", 0))


def _dev_agnos_reboot() -> dict[str, Any]:
  snap = _dev_agnos_snapshot()
  if not snap.get("ready_to_reboot"):
    return {"ok": False, "error": "not_ready"}
  _schedule_dev_reboot(5.0)
  _write_state(status="idle", message="", progress=0)
  return {"ok": True, "dev_sim_reboot": True}


def start_agnos_install() -> dict[str, Any]:
  global _THREAD

  if _is_dev_pc():
    snap = _dev_agnos_snapshot()
    if not snap.get("available"):
      return {"ok": False, "error": "not_agnos"}
    if not snap.get("update_required"):
      return {"ok": False, "error": "not_required"}
    if snap.get("ready_to_reboot"):
      return _dev_agnos_reboot()

    with _LOCK:
      if _is_job_running():
        return {"ok": True, "already_running": True, "job": _read_state()}
      _THREAD = threading.Thread(target=_run_dev_agnos_install, name="agnos-webui-dev", daemon=True)
      _THREAD.start()
    return {"ok": True, "started": True, "simulated": True, "job": _read_state()}

  snap = agnos_snapshot()
  if not snap.get("available"):
    return {"ok": False, "error": "not_agnos"}
  if not snap.get("update_required"):
    return {"ok": False, "error": "not_required"}
  if snap.get("ready_to_reboot"):
    try:
      from openpilot.common.hardware import HARDWARE
      HARDWARE.reboot()
      return {"ok": True, "action": "reboot"}
    except Exception as exc:
      return {"ok": False, "error": str(exc)}

  with _LOCK:
    if _is_job_running():
      return {"ok": True, "already_running": True, "job": _read_state()}
    _THREAD = threading.Thread(target=_run_agnos_swap, name="agnos-webui", daemon=True)
    _THREAD.start()
  return {"ok": True, "started": True, "job": _read_state()}


def agnos_reboot() -> dict[str, Any]:
  if _is_dev_pc():
    return _dev_agnos_reboot()
  snap = agnos_snapshot()
  if not snap.get("ready_to_reboot"):
    return {"ok": False, "error": "not_ready"}
  try:
    from openpilot.common.hardware import HARDWARE
    HARDWARE.reboot()
    return {"ok": True}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def agnos_home_fields() -> dict[str, Any]:
  """Lightweight AGNOS fields for the offroad home screen."""
  pending = _agnos_pending_status()
  if not pending.get("available"):
    return {
      "agnos_available": False,
      "agnos_update_required": False,
      "agnos_ready_to_reboot": False,
      "agnos_current_version": "",
      "agnos_target_version": "",
    }
  return {
    "agnos_available": True,
    "agnos_update_required": pending["update_required"],
    "agnos_ready_to_reboot": pending["ready_to_reboot"],
    "agnos_current_version": pending["current_version"],
    "agnos_target_version": pending["target_version"],
  }

