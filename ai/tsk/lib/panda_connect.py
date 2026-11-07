"""Panda USB access on comma devices — fork-aware ``panda`` / ``pandad`` selection.

Product naming (devicetree ``comma <type>``):

  - **tici** — comma three (C3), internal panda F4 (DOS)
  - **tizi** — comma threeX (C3X), internal panda H7
  - **mici** — comma four (C4), internal panda H7

Firmware / process layout is detected at runtime from the connected openpilot tree
(``ai.system.panda_stack``): unified ``panda/`` + ``pandad``, or split ``panda_tici`` /
``pandad_tici`` on some legacy split-panda layouts.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PANDA_MCU_CACHE = "/persist/sp_dev_panda_mcu_type"
PANDA_MCU_LEGACY_CACHE = "/persist/dp_dev_panda_mcu_type"
DEVICE_TREE_MODEL = "/sys/firmware/devicetree/base/model"

_COMMA_PRODUCTS: dict[str, dict[str, str]] = {
  "tici": {"label": "C3", "name": "comma three"},
  "tizi": {"label": "C3X", "name": "comma threeX"},
  "mici": {"label": "C4", "name": "comma four"},
}


def _openpilot_root() -> Path:
  from ai.system.paths import openpilot_root

  return openpilot_root()


def _stack():
  from ai.system import panda_stack

  return panda_stack


def _pandad_module() -> str:
  return _stack().resolve_pandad_module()


def _mcu_from_raw(mcu_raw: str) -> str | None:
  if "F4" in mcu_raw:
    return "F4"
  if "H7" in mcu_raw:
    return "H7"
  return None


def _backend_for_mcu(mcu: str | None) -> dict[str, Any]:
  dos = mcu == "F4"
  st = _stack()
  return {
    "panda_backend": st.resolve_panda_backend(),
    "panda_backend_h7": st.resolve_panda_backend(for_h7=True),
    "pandad_process": st.pandad_process_name(),
    "pandad_module": st.resolve_pandad_module(),
    "tici_dos": dos,
    "tici_tres": mcu == "H7",
    "inferred_class": "C3" if dos else "C3X/C4",
    **_stack().detect_panda_stack(),
  }


def get_device_type() -> str | None:
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
  return is_comma_hw()


def _read_mcu_cache() -> str | None:
  for path in (PANDA_MCU_CACHE, PANDA_MCU_LEGACY_CACHE):
    try:
      value = Path(path).read_text(encoding="utf-8").strip()
    except OSError:
      continue
    if value in ("F4", "H7"):
      return value
  return None


def _query_panda_mcu_type() -> str | None:
  try:
    panda = import_panda_class()
    panda_inst = panda(cli=False)
    try:
      mcu = str(panda_inst.get_mcu_type())
    finally:
      panda_inst.close()
  except Exception:
    return None
  return _mcu_from_raw(mcu)


def is_tici_dos() -> bool:
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
  if not is_comma_hw():
    return
  if "TICI_DOS" in os.environ or "TICI_TRES" in os.environ:
    return
  if is_tici_dos():
    os.environ["TICI_DOS"] = "1"
  else:
    os.environ["TICI_TRES"] = "1"


def panda_backend() -> str:
  return _stack().resolve_panda_backend()


def pandad_process_name() -> str:
  return _stack().pandad_process_name()


def pandad_module() -> str:
  return _pandad_module()


def import_panda_class():
  st = _stack()
  for pkg in (st.resolve_panda_backend(), "panda"):
    try:
      mod = __import__(pkg, fromlist=["Panda"])
      return mod.Panda
    except ImportError:
      continue
  if st.has_panda_tici_tree():
    from panda_tici import Panda  # type: ignore[import-not-found]

    return Panda
  from panda import Panda

  return Panda


def is_manager_running() -> bool:
  """True when openpilot manager.py is running (comma system/manager or sunnypilot ./manager.py)."""
  patterns = (
    "system/manager/manager.py",
    "manager/manager.py",
  )
  try:
    for pat in patterns:
      if subprocess.run(
        ["pgrep", "-f", pat],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=5,
      ).returncode == 0:
        return True
    r = subprocess.run(
      ["pgrep", "-af", "[m]anager.py"],
      capture_output=True,
      text=True,
      timeout=5,
      check=False,
    )
    if r.returncode != 0:
      return False
    for line in (r.stdout or "").splitlines():
      if "system/manager/manager.py" in line or "manager/manager.py" in line:
        return True
      if re.search(r"python\S*\s+(\./|/)?manager\.py(?:\s|$)", line):
        return True
  except OSError:
    return False
  return False


def is_pandad_running() -> bool:
  mod = _pandad_module()
  patterns = (mod, "openpilot.selfdrive.pandad.pandad", "selfdrive/pandad/pandad", "./pandad")
  try:
    for pat in patterns:
      if subprocess.run(
        ["pgrep", "-f", pat],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
      ).returncode == 0:
        return True
  except OSError:
    return False
  return False


def stop_pandad() -> None:
  mod = _pandad_module()
  for pat in (mod, "openpilot.selfdrive.pandad.pandad", "selfdrive/pandad/pandad", "./pandad"):
    subprocess.run(["pkill", "-9", "-f", pat], check=False)


def start_pandad(*, wait_seconds: float = 0.5) -> bool:
  ensure_tici_env()
  root = _openpilot_root()
  mod = _pandad_module()
  env = os.environ.copy()
  try:
    subprocess.Popen(
      [sys.executable, "-m", mod],
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
  subprocess.run(["pkill", "-9", "-f", "manager.py"], check=False)
  stop_pandad()
  time.sleep(2)


def restart_pandad() -> dict[str, Any]:
  ensure_tici_env()
  mod = _pandad_module()
  proc = pandad_process_name()
  stop_pandad()
  time.sleep(1)

  manager_running = is_manager_running()
  if manager_running:
    for _ in range(4):
      if is_pandad_running():
        return {
          "ok": True,
          "started": False,
          "pandad_process": proc,
          "pandad_module": mod,
          "message": f"{proc} 已恢复（manager 监督进程）。",
        }
      time.sleep(1)

  started = start_pandad(wait_seconds=2.0)
  if started:
    return {
      "ok": True,
      "started": True,
      "pandad_process": proc,
      "pandad_module": mod,
      "message": (
        f"已重启 {proc}（manager 未运行，已直接启动 {mod}）。"
        if not manager_running
        else f"已重启 {proc}（manager 未能自动拉起，已手动启动 {mod}）。"
      ),
    }

  return {
    "ok": False,
    "started": False,
    "pandad_process": proc,
    "pandad_module": mod,
    "manager_running": manager_running,
    "message": (
      f"已终止 {proc}，但未能重新启动。请点 SecOC「重启 manager」或重启设备，否则 GUI 会显示 Panda 否。"
      if manager_running
      else f"已终止 {proc}，但未能重新启动。请尝试「重启 manager」或重启设备。"
    ),
  }


def recover_pandad_after_flash() -> dict[str, Any]:
  """Restart pandad after F4 flash so openpilot UI regains pandaStates."""
  return restart_pandad()


def probe_pc_panda() -> dict[str, Any]:
  st = _stack()
  out: dict[str, Any] = {"connected": False, "probe": st.resolve_panda_backend()}
  try:
    Panda = import_panda_class()
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
    out["error"] = str(exc)[:240]
  return out


def host_hardware_profile() -> dict[str, Any]:
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
  st = _stack()
  profile: dict[str, Any] = {
    "host_kind_label": "PC",
    "product_label": "PC",
    "device_type": None,
    **runtime,
    "panda_probe": st.resolve_panda_backend(),
    "panda_connected": bool(probe.get("connected")),
    "panda_backend": st.resolve_panda_backend(),
    "pandad_process": st.pandad_process_name(),
    "pandad_module": st.resolve_pandad_module(),
    **st.detect_panda_stack(),
  }
  if probe.get("connected"):
    profile.update({
      "panda_mcu": probe.get("panda_mcu"),
      "tici_dos": probe.get("tici_dos"),
      "tici_tres": probe.get("tici_tres"),
      "inferred_class": probe.get("inferred_class"),
      "mcu_raw": probe.get("mcu_raw"),
      "panda_backend_h7": probe.get("panda_backend_h7"),
    })
    if probe.get("panda_mcu") == "F4":
      profile["host_kind_label"] = "PC · F4"
    elif probe.get("panda_mcu") == "H7":
      profile["host_kind_label"] = "PC · H7"
  else:
    profile["panda_probe_error"] = probe.get("error")
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
  from ai.system.hardware_lite import lite_profile

  st = _stack()
  stack = st.detect_panda_stack()
  return {
    "device_type": device,
    "tici_hw": is_comma_hw(),
    "tici_dos": dos,
    "tici_tres": is_comma_hw() and not dos,
    "panda_mcu_cache": cached,
    "panda_backend": st.resolve_panda_backend(),
    "panda_backend_h7": st.resolve_panda_backend(for_h7=True),
    "pandad_process": st.pandad_process_name(),
    "pandad_module": st.resolve_pandad_module(),
    **stack,
    **comma_product_meta(device),
    **lite_profile(),
  }


# Re-export for tools that import from panda_connect.
def has_panda_tici() -> bool:
  return _stack().has_panda_tici_tree()


def has_pandad_tici() -> bool:
  return _stack().has_pandad_tici_tree()


def use_tici_panda_stack() -> bool:
  return _stack().use_tici_panda_stack()
