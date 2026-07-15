"""Panda USB access on comma devices — aligned with launch_chffrplus.sh / manager.py.

Product naming (devicetree ``comma <type>``):
  - **tici** — comma three (C3), internal panda F4 → ``panda_tici`` / ``pandad_tici`` when both packages exist
  - **tizi** — comma threeX (C3X), internal panda H7 → ``panda`` / ``pandad`` (TICI_TRES)
  - **mici** — comma four (C4), internal panda H7 → ``panda`` / ``pandad`` (TICI_TRES)

If ``panda_tici`` or ``pandad_tici`` is missing from the tree, F4/C3 still uses ``panda`` + ``pandad``.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PANDA_MCU_CACHE = "/persist/dp_dev_panda_mcu_type"
DEVICE_TREE_MODEL = "/sys/firmware/devicetree/base/model"
PANDAD_TICI_MODULE = "selfdrive.pandad_tici.pandad"
PANDAD_MODULE = "selfdrive.pandad.pandad"

_COMMA_PRODUCTS: dict[str, dict[str, str]] = {
  "tici": {"label": "C3", "name": "comma three"},
  "tizi": {"label": "C3X", "name": "comma threeX"},
  "mici": {"label": "C4", "name": "comma four"},
}


def _openpilot_root() -> Path:
  return Path(__file__).resolve().parents[3]


def _import_spec_available(name: str) -> bool:
  try:
    return importlib.util.find_spec(name) is not None
  except (ModuleNotFoundError, ValueError, ImportError):
    return False


def has_panda_tici() -> bool:
  """Whether the ``panda_tici`` Python package is installed in this tree."""
  if _import_spec_available("panda_tici"):
    return True
  return (_openpilot_root() / "panda_tici").is_dir()


def has_pandad_tici() -> bool:
  """Whether ``selfdrive.pandad_tici.pandad`` exists (built / shipped in this fork)."""
  if _import_spec_available(PANDAD_TICI_MODULE):
    return True
  return (_openpilot_root() / "selfdrive" / "pandad_tici" / "pandad.py").is_file()


def use_tici_panda_stack() -> bool:
  """F4/DOS hardware **and** both ``panda_tici`` + ``pandad_tici`` are present."""
  return is_tici_dos() and has_panda_tici() and has_pandad_tici()


def _import_probe_panda():
  """Prefer ``panda_tici`` when installed; otherwise ``panda``."""
  if has_panda_tici():
    from panda_tici import Panda

    return Panda, "panda_tici"
  from panda import Panda

  return Panda, "panda"


def _mcu_from_raw(mcu_raw: str) -> str | None:
  if "F4" in mcu_raw:
    return "F4"
  if "H7" in mcu_raw:
    return "H7"
  return None


def _backend_for_mcu(mcu: str | None) -> dict[str, Any]:
  """Map MCU type to panda/pandad stack (F4 may fall back when tici packages missing)."""
  if mcu == "F4" and has_panda_tici() and has_pandad_tici():
    return {
      "panda_backend": "panda_tici",
      "pandad_process": "pandad_tici",
      "pandad_module": PANDAD_TICI_MODULE,
      "tici_dos": True,
      "tici_tres": False,
      "inferred_class": "C3",
    }
  if mcu == "F4":
    return {
      "panda_backend": "panda",
      "pandad_process": "pandad",
      "pandad_module": PANDAD_MODULE,
      "tici_dos": True,
      "tici_tres": False,
      "inferred_class": "C3",
    }
  return {
    "panda_backend": "panda",
    "pandad_process": "pandad",
    "pandad_module": PANDAD_MODULE,
    "tici_dos": False,
    "tici_tres": True,
    "inferred_class": "C3X/C4",
  }


def get_device_type() -> str | None:
  """Return devicetree device slug: ``tici`` | ``tizi`` | ``mici``, or None off-device."""
  try:
    with open(DEVICE_TREE_MODEL) as f:
      model = f.read().strip("\x00")
    tail = model.split("comma ")[-1].strip().lower()
  except OSError:
    return None
  return tail if tail in ("tici", "tizi", "mici") else None


def is_comma_hw() -> bool:
  if os.environ.get("TICI_HW") == "1":
    return True
  return get_device_type() in ("tici", "tizi", "mici")


def is_tici_hw() -> bool:
  """True on comma AGNOS hardware (tici / tizi / mici). Name kept for API compat."""
  return is_comma_hw()


def _read_mcu_cache() -> str | None:
  try:
    value = Path(PANDA_MCU_CACHE).read_text(encoding="utf-8").strip()
  except OSError:
    return None
  return value if value in ("F4", "H7") else None


def _query_panda_mcu_type() -> str | None:
  """Query panda MCU (F4=DOS/C3, H7=TRES/C3X+C4). Uses installed panda library."""
  try:
    Panda, _probe = _import_probe_panda()
    panda = Panda(cli=False)
    try:
      mcu = str(panda.get_mcu_type())
    finally:
      panda.close()
  except Exception:
    return None
  return _mcu_from_raw(mcu)


def is_tici_dos() -> bool:
  """True on comma three (C3 / tici, F4) hardware (independent of panda_tici install)."""
  if os.environ.get("TICI_DOS") == "1" or "TICI_DOS" in os.environ:
    return True
  if os.environ.get("TICI_TRES") == "1" or "TICI_TRES" in os.environ:
    return False
  cached = _read_mcu_cache()
  if cached == "F4":
    return True
  if cached == "H7":
    return False
  device = get_device_type()
  if device == "tici":
    return True
  if device in ("tizi", "mici"):
    return False
  if not is_comma_hw():
    return False
  queried = _query_panda_mcu_type()
  if queried == "F4":
    return True
  if queried == "H7":
    return False
  return False


def ensure_tici_env() -> None:
  """Align os.environ with detected hardware (aid may run without launch.sh exports)."""
  if not is_comma_hw():
    return
  if "TICI_DOS" in os.environ or "TICI_TRES" in os.environ:
    return
  if is_tici_dos():
    os.environ["TICI_DOS"] = "1"
  else:
    os.environ["TICI_TRES"] = "1"


def panda_backend() -> str:
  """C3/F4 with tici stack → ``panda_tici``; otherwise ``panda``."""
  return "panda_tici" if use_tici_panda_stack() else "panda"


def pandad_process_name() -> str:
  return "pandad_tici" if use_tici_panda_stack() else "pandad"


def pandad_module() -> str:
  return PANDAD_TICI_MODULE if use_tici_panda_stack() else PANDAD_MODULE


def import_panda_class():
  if use_tici_panda_stack():
    from panda_tici import Panda
  else:
    from panda import Panda
  return Panda


def is_manager_running() -> bool:
  try:
    return subprocess.run(
      ["pgrep", "-f", "system/manager/manager.py"],
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
      check=False,
    ).returncode == 0
  except OSError:
    return False


def is_pandad_running() -> bool:
  pattern = pandad_module()
  try:
    return subprocess.run(
      ["pgrep", "-f", pattern],
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
      check=False,
    ).returncode == 0
  except OSError:
    return False


def stop_pandad() -> None:
  """Stop only this device's pandad variant (never blanket ``pkill pandad``)."""
  subprocess.run(["pkill", "-9", "-f", pandad_module()], check=False)


def start_pandad(*, wait_seconds: float = 0.5) -> bool:
  """Start the device-appropriate pandad module (used when manager is not running)."""
  ensure_tici_env()
  root = _openpilot_root()
  module = pandad_module()
  env = os.environ.copy()
  try:
    subprocess.Popen(
      [sys.executable, "-m", module],
      cwd=str(root),
      env=env,
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
      start_new_session=True,
    )
  except OSError:
    return False
  if wait_seconds > 0:
    time.sleep(wait_seconds)
  return is_pandad_running()


def stop_manager_and_pandad() -> None:
  """Release the USB panda before TSK extract/dump/collect."""
  subprocess.run(["pkill", "-9", "-f", "manager.py"], check=False)
  stop_pandad()
  time.sleep(2)


def restart_pandad() -> dict[str, Any]:
  """Kill and optionally restart the correct pandad for this device."""
  ensure_tici_env()
  proc = pandad_process_name()
  module = pandad_module()
  stop_pandad()
  time.sleep(1)
  if is_manager_running():
    return {
      "ok": True,
      "started": False,
      "pandad_process": proc,
      "pandad_module": module,
      "message": f"已终止 {proc}。manager 正在运行，将自动重新拉起。",
    }
  started = start_pandad()
  if started:
    return {
      "ok": True,
      "started": True,
      "pandad_process": proc,
      "pandad_module": module,
      "message": f"已重启 {proc}（manager 未运行，已直接启动 {module}）。",
    }
  return {
    "ok": False,
    "started": False,
    "pandad_process": proc,
    "pandad_module": module,
    "message": f"已终止 {proc}，但未能重新启动 {module}。请尝试「重启 manager」或重启设备。",
  }


def probe_pc_panda() -> dict[str, Any]:
  """On PC dev: read panda MCU via installed library (``panda_tici`` if present)."""
  out: dict[str, Any] = {"connected": False}
  try:
    Panda, probe = _import_probe_panda()
    out["probe"] = probe
    panda = Panda(cli=False)
    try:
      mcu_raw = str(panda.get_mcu_type())
      out["connected"] = True
      out["mcu_raw"] = mcu_raw
      mcu = _mcu_from_raw(mcu_raw)
      out["panda_mcu"] = mcu
      if mcu:
        out.update(_backend_for_mcu(mcu))
    finally:
      panda.close()
  except Exception as exc:
    out["probe"] = out.get("probe") or ("panda_tici" if has_panda_tici() else "panda")
    out["error"] = str(exc)[:240]
  return out


def host_hardware_profile() -> dict[str, Any]:
  """Unified hardware snapshot for Web dev panel and ``get_host_environment``."""
  runtime = {
    "manager_running": is_manager_running(),
    "pandad_running": is_pandad_running(),
  }
  if is_comma_hw():
    info = tici_info()
    mcu = info.get("panda_mcu_cache")
    if mcu not in ("F4", "H7"):
      if info.get("tici_dos"):
        mcu = "F4"
      elif info.get("tici_tres"):
        mcu = "H7"
      else:
        mcu = _query_panda_mcu_type()
    return {
      **info,
      **runtime,
      "host_kind_label": info.get("product_label") or info.get("device_type"),
      "panda_mcu": mcu,
      "panda_connected": True,
      "panda_probe": "comma_internal",
    }

  probe = probe_pc_panda()
  profile: dict[str, Any] = {
    "host_kind_label": "PC",
    "product_label": "PC",
    "device_type": None,
    **runtime,
    "panda_probe": probe.get("probe", "panda_tici"),
    "panda_connected": bool(probe.get("connected")),
  }
  if probe.get("connected"):
    profile.update({
      "panda_mcu": probe.get("panda_mcu"),
      "tici_dos": probe.get("tici_dos"),
      "tici_tres": probe.get("tici_tres"),
      "panda_backend": probe.get("panda_backend"),
      "pandad_process": probe.get("pandad_process"),
      "pandad_module": probe.get("pandad_module"),
      "inferred_class": probe.get("inferred_class"),
      "mcu_raw": probe.get("mcu_raw"),
    })
    if probe.get("panda_mcu") == "F4":
      profile["host_kind_label"] = "PC · F4"
    elif probe.get("panda_mcu") == "H7":
      profile["host_kind_label"] = "PC · H7"
  else:
    profile["panda_probe_error"] = probe.get("error")
    profile["panda_backend"] = "panda"
    profile["pandad_process"] = "pandad"
    profile["pandad_module"] = "selfdrive.pandad.pandad"
  return profile


def comma_product_meta(device_type: str | None) -> dict[str, str | None]:
  meta = _COMMA_PRODUCTS.get(device_type or "", {})
  return {
    "product_label": meta.get("label"),
    "product_name": meta.get("name"),
  }


def tici_info() -> dict[str, Any]:
  ensure_tici_env()
  cached = _read_mcu_cache()
  dos = is_tici_dos()
  device = get_device_type()
  return {
    "device_type": device,
    "tici_hw": is_comma_hw(),
    "tici_dos": dos,
    "tici_tres": is_comma_hw() and not dos,
    "panda_mcu_cache": cached,
    "panda_tici_available": has_panda_tici(),
    "pandad_tici_available": has_pandad_tici(),
    "use_tici_panda_stack": use_tici_panda_stack(),
    "panda_backend": panda_backend(),
    "pandad_process": pandad_process_name(),
    "pandad_module": pandad_module(),
    **comma_product_meta(device),
  }
