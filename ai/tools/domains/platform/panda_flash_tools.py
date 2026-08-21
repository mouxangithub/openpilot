"""F4 (black/DOS) panda firmware helpers for op助手.

Firmware policy
---------------
``panda.bin.signed`` / ``panda_h7.bin.signed`` are **build artifacts** under the
connected openpilot tree (``panda/board/obj/``). They are **not** shipped inside
the ``ai`` package and must **not** be copied into ``ai/`` — when the ``panda``
submodule changes, run ``build_panda_firmware`` (``scons panda/board``) on the
device or build host, then flash.

Self-contained: does **not** require ``ai/scripts/recover_dos_panda.py`` (optional CLI wrapper on some forks).
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

from ai.system.paths import is_comma_device, openpilot_root, source_path, tools_path

FW_REL = Path("panda", "board", "obj", "panda.bin.signed")
TICI_FW_REL = Path("panda", "board", "obj", "panda_h7.bin.signed")
# Resolved via openpilot_root() — never under ai/
FIRMWARE_POLICY = {
  "bundled_in_ai": False,
  "source": "panda submodule (scons panda/board)",
  "f4_path": str(FW_REL),
  "h7_path": str(TICI_FW_REL),
  "build_tool": "build_panda_firmware",
  "build_cmd": "cd panda/board && scons -j$(nproc)",
  "after_panda_submodule_update": "rebuild firmware, then offroad flash_panda_firmware",
}
REBUILD_SCRIPT = Path("ai", "scripts", "rebuild_pandad.sh")
RECOVER_SCRIPT = Path("ai", "scripts", "recover_dos_panda.py")

OFFROAD_FLASH_ERROR = (
  "当前处于 onroad，Panda 刷写仅能在 offroad（停车）下进行。"
  "请挂 P 挡、退出 openpilot 后再试。"
)


def _default_state_reader():
  try:
    from ai.server.deps import get_state_reader
    return get_state_reader()
  except Exception:
    return None


def detect_onroad(*, get_state_reader=None) -> dict[str, Any]:
  """Return onroad/offroad snapshot for UI and guards."""
  reader_fn = get_state_reader or _default_state_reader
  force_offroad = False
  try:
    reader = reader_fn()
    if reader is not None:
      state = reader.update(timeout=0)
      force_offroad = bool(getattr(state, "force_offroad", False))
      onroad = bool(getattr(state, "started", False)) and not force_offroad
      return {
        "onroad": onroad,
        "offroad": not onroad,
        "source": "state_reader",
        "force_offroad": force_offroad,
        "started": bool(getattr(state, "started", False)),
      }
  except Exception:
    pass

  try:
    from openpilot.common.params import Params

    params = Params()
    force_offroad = params.get_bool("OffroadMode")
    onroad = params.get_bool("IsOnroad") and not force_offroad
    return {
      "onroad": onroad,
      "offroad": not onroad,
      "source": "params:IsOnroad",
      "force_offroad": force_offroad,
      "started": onroad,
    }
  except Exception:
    pass

  return {
    "onroad": False,
    "offroad": True,
    "source": None,
    "force_offroad": force_offroad,
    "started": False,
  }


def offroad_flash_guard(*, get_state_reader=None) -> dict[str, Any] | None:
  """Block Panda flash/write firmware when onroad. Returns error dict or None."""
  info = detect_onroad(get_state_reader=get_state_reader)
  if info.get("onroad"):
    return {
      "ok": False,
      "onroad": True,
      "offroad": False,
      "error": OFFROAD_FLASH_ERROR,
      "onroad_source": info.get("source"),
    }
  if is_comma_device() and info.get("source") is None:
    return {
      "ok": False,
      "onroad": None,
      "error": "无法确认 offroad 状态，为安全起见已拒绝刷写。",
    }
  return None


def _attach_offroad_flash_policy(payload: dict[str, Any], *, get_state_reader=None) -> dict[str, Any]:
  info = detect_onroad(get_state_reader=get_state_reader)
  payload.update(info)
  blocked = offroad_flash_guard(get_state_reader=get_state_reader)
  payload["flash_allowed"] = blocked is None
  if blocked:
    payload["flash_blocked_reason"] = blocked.get("error")
  return payload


def _fw_path() -> Path:
  return openpilot_root() / FW_REL


def _tici_fw_path() -> Path:
  return openpilot_root() / TICI_FW_REL


def _firmware_scenario_guidance(multi: dict[str, Any] | None) -> dict[str, Any]:
  """Human-readable build/flash guidance from connected Panda layout (C3 DOS / aux H7)."""
  multi = multi or {}
  scenario = multi.get("scenario")
  count = int(multi.get("count") or 0)
  f4_count = int(multi.get("f4_count") or 0)
  h7_count = int(multi.get("h7_count") or 0)

  if scenario == "heterogeneous_f4_h7":
    return {
      "scenario": scenario,
      "build_f4": True,
      "build_h7": True,
      "summary_zh": (
        "内置 F4 + 外接 H7（红熊）：一次 scons panda/board 产出 F4 与 H7 固件，分别刷两块。"
        "控车 safety（含 MADS）在外接 H7；内置 F4 为 noOutput，只刷 F4 不能解决 MADS。"
      ),
      "summary_en": (
        "Internal F4 + external H7 (red panda): one scons panda/board builds both images; flash both."
        "Vehicle safety (incl. MADS) runs on external H7; internal F4 is noOutput."
      ),
      "mads_zh": "修改 opendbc/safety（如 mads.h）后 scons panda/board，再刷 F4 + H7（panda_h7.bin.signed）。",
      "mads_en": "After opendbc/safety changes (e.g. mads.h), scons panda/board, then flash F4 + H7 (panda_h7.bin.signed).",
    }

  if count <= 1 and f4_count == 1 and h7_count == 0:
    return {
      "scenario": "single_f4",
      "build_f4": True,
      "build_h7": False,
      "summary_zh": "单内置 F4（C3 DOS）：MADS / safety 由 panda/board/obj/panda.bin.signed 决定，只需编译并刷 panda/。",
      "summary_en": "Single internal F4 (C3 DOS): MADS/safety comes from panda/board/obj/panda.bin.signed — build and flash panda/ only.",
      "mads_zh": "改 mads.h 后 scons panda/board → 刷 F4 即可。",
      "mads_en": "After mads.h changes: scons panda/board → flash F4.",
    }

  if count <= 1 and h7_count == 1 and f4_count == 0:
    return {
      "scenario": "single_h7",
      "build_f4": False,
      "build_h7": True,
      "summary_zh": "仅 H7（红熊）：固件为 panda/board/obj/panda_h7.bin.signed，由 pandad 自动刷写。",
      "summary_en": "H7 only (red panda): firmware is panda/board/obj/panda_h7.bin.signed, flashed via pandad.",
      "mads_zh": "MADS 在 H7 固件内；改 opendbc 后 scons panda/board 并刷 H7。",
      "mads_en": "MADS lives in H7 firmware; after opendbc edits, scons panda/board and flash H7.",
    }

  if count == 0:
    return {
      "scenario": "none_detected",
      "build_f4": True,
      "build_h7": False,
      "summary_zh": "未检测到 Panda：C3 DOS 默认只需 panda/ 固件；若已接外接红熊请插好 USB 后刷新状态。",
      "summary_en": "No Panda detected: C3 DOS normally needs panda/ only; plug external red panda and refresh if used.",
      "mads_zh": "单内置 F4：改 safety 后编 panda/board；双 Panda（F4+H7）同一次 scons 产出两镜像。",
      "mads_en": "Single internal F4: rebuild panda/board after safety edits; F4+H7 uses one scons for both images.",
    }

  if h7_count >= 1 and f4_count == 0:
    return {
      "scenario": scenario or "multi_h7",
      "build_f4": False,
      "build_h7": True,
      "summary_zh": f"检测到 {h7_count} 块 H7：scons panda/board 后由 flash_panda_firmware 刷写。",
      "summary_en": f"{h7_count} H7 panda(s): scons panda/board, then flash_panda_firmware.",
      "mads_zh": "MADS 由 H7 固件执行（panda_h7.bin.signed）。",
      "mads_en": "MADS is enforced on H7 firmware (panda_h7.bin.signed).",
    }

  return {
    "scenario": scenario or "multi_mixed",
    "build_f4": f4_count > 0,
    "build_h7": h7_count > 0,
    "summary_zh": (
      f"多 Panda（F4×{f4_count} H7×{h7_count}）：F4/H7 均来自 panda/board/obj；"
      "含外接红熊时控车 safety 在 H7 上。"
    ),
    "summary_en": (
      f"Multi panda (F4×{f4_count} H7×{h7_count}): both images from panda/board/obj; "
      "with external red panda, vehicle safety runs on H7."
    ),
    "mads_zh": "异构双 Panda 时须两边 opendbc safety 同步编译。",
    "mads_en": "Heterogeneous dual panda: sync opendbc safety in both firmware builds.",
  }


def _tool_script(rel: Path) -> Path:
  return openpilot_root().joinpath(*rel.parts)


def _python() -> str:
  venv_py = Path("/usr/local/venv/bin/python3")
  if venv_py.is_file():
    return str(venv_py)
  return sys.executable


def _sub_env() -> dict[str, str]:
  root = str(openpilot_root())
  env = os.environ.copy()
  env["PYTHONPATH"] = root
  path = env.get("PATH", "")
  for prefix in ("/usr/local/venv/bin", "/usr/bin", "/bin"):
    if prefix not in path.split(":"):
      path = f"{prefix}:{path}" if path else prefix
  env["PATH"] = path
  return env


def shutil_which(cmd: str) -> str | None:
  from shutil import which
  return which(cmd)


def _coerce_hw_type(hw: Any) -> bytes:
  """Normalize USB controlRead hw type (bytes or bytearray) for dict lookups."""
  if isinstance(hw, bytearray):
    return bytes(hw)
  if isinstance(hw, bytes):
    return hw
  if isinstance(hw, int):
    return bytes([hw & 0xFF])
  return bytes(hw) if hw is not None else b"\x00"


def _hw_type_label(hw: bytes | bytearray) -> str:
  try:
    from panda import Panda
  except ImportError:
    hw = _coerce_hw_type(hw)
    return hw.hex()

  hw = _coerce_hw_type(hw)
  labels = {
    Panda.HW_TYPE_WHITE_PANDA: "WHITE_PANDA",
    Panda.HW_TYPE_GREY_PANDA: "GREY_PANDA",
    Panda.HW_TYPE_BLACK_PANDA: "BLACK_PANDA",
    Panda.HW_TYPE_PEDAL: "PEDAL",
    Panda.HW_TYPE_UNO: "UNO",
    Panda.HW_TYPE_DOS: "DOS",
    Panda.HW_TYPE_RED_PANDA: "RED_PANDA",
    Panda.HW_TYPE_RED_PANDA_V2: "RED_PANDA_V2",
    Panda.HW_TYPE_TRES: "TRES",
    Panda.HW_TYPE_CUATRO: "CUATRO",
    Panda.HW_TYPE_BODY: "BODY",
  }
  return labels.get(hw, hw.hex())


def _describe_panda(serial: str) -> dict[str, Any]:
  try:
    from panda import Panda

    p = Panda(serial)
    hw = _coerce_hw_type(p.get_type())
    internal = p.is_internal()
    mcu = p.get_mcu_type().config.app_fn
    bootstub = p.bootstub
    p.close()
    is_f4 = hw in Panda.F4_DEVICES
    is_h7 = hw in Panda.H7_DEVICES
    return {
      "serial": serial,
      "internal": internal,
      "role": "internal" if internal else "external",
      "hw_type": hw.hex() if isinstance(hw, bytes) else str(hw),
      "hw_type_name": _hw_type_label(hw),
      "mcu": mcu,
      "bootstub": bootstub,
      "is_f4": is_f4,
      "is_h7": is_h7,
    }
  except Exception as e:
    return {"serial": serial, "error": str(e)}


def _analyze_multi_panda(entries: list[dict[str, Any]]) -> dict[str, Any]:
  valid = [e for e in entries if "error" not in e]
  f4 = [e for e in valid if e.get("is_f4")]
  h7 = [e for e in valid if e.get("is_h7")]
  internal = [e for e in valid if e.get("internal")]
  external = [e for e in valid if not e.get("internal")]
  scenario: str | None = None
  if len(valid) >= 2:
    if f4 and h7:
      scenario = "heterogeneous_f4_h7"
    elif len(h7) >= 2:
      scenario = "dual_h7"
    elif len(f4) >= 2:
      scenario = "dual_f4"
    else:
      scenario = "multi_mixed"
  return {
    "count": len(valid),
    "f4_count": len(f4),
    "h7_count": len(h7),
    "internal_count": len(internal),
    "external_count": len(external),
    "scenario": scenario,
    "heterogeneous_f4_h7": scenario == "heterogeneous_f4_h7",
    "needs_pandad_dual_usb": scenario in ("heterogeneous_f4_h7", "dual_h7", "dual_f4"),
    # backward compat for older UI/tests
    "needs_pandad_tici_dual_usb": scenario in ("heterogeneous_f4_h7", "dual_h7", "dual_f4"),
  }


def _pandad_process_snapshot() -> dict[str, Any]:
  out: dict[str, Any] = {"running": False, "processes": [], "serials_in_cmdline": []}
  if not shutil_which("pgrep"):
    out["note"] = "pgrep unavailable"
    return out
  try:
    proc = subprocess.run(
      ["pgrep", "-af", "pandad"],
      capture_output=True,
      text=True,
      timeout=5,
    )
    lines = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
    out["processes"] = lines
    out["running"] = bool(lines)
    serials: list[str] = []
    for line in lines:
      for token in line.split():
        if len(token) >= 20 and all(c in "0123456789abcdef" for c in token.lower()):
          serials.append(token)
    out["serials_in_cmdline"] = list(dict.fromkeys(serials))
  except Exception as e:
    out["error"] = str(e)

  log_path = openpilot_root() / "data" / "log" / "manager.log"
  if log_path.is_file():
    try:
      tail = log_path.read_text(encoding="utf-8", errors="replace")[-12000:]
      crash_markers = (
        "USBErrorBusy",
        "selfdrive.pandad.pandad",
        "exitcode -6",
        "BOARDD_SKIP_FW_CHECK",
      )
      hits = [m for m in crash_markers if m in tail]
      if hits:
        out["recent_log_markers"] = hits
        out["possible_crash_loop"] = (
          not out.get("running")
          or "USBErrorBusy" in hits
          or "exitcode -6" in hits
        )
    except Exception:
      pass
  return out


def pick_serial(serials: list[str], *, external: bool, internal: bool) -> str | None:
  try:
    from panda import Panda
  except ImportError:
    return serials[0] if serials else None

  if not serials:
    return None

  candidates: list[str] = []
  for serial in serials:
    try:
      p = Panda(serial)
      is_internal = p.is_internal()
      is_f4 = p.get_type() in Panda.F4_DEVICES
      p.close()
    except Exception:
      continue
    if not is_f4:
      continue
    if external and not is_internal:
      candidates.append(serial)
    elif internal and is_internal:
      candidates.append(serial)
    elif not external and not internal:
      candidates.append(serial)

  if external or internal:
    return candidates[0] if candidates else None

  for serial in serials:
    try:
      p = Panda(serial)
      if p.is_internal() and p.get_type() in Panda.F4_DEVICES:
        p.close()
        return serial
      p.close()
    except Exception:
      continue
  return serials[0]


def recover_dfu() -> tuple[list[str], str]:
  """Try internal DFU recovery. Returns (serials, log text)."""
  from panda import Panda, PandaDFU
  from openpilot.common.hardware import HARDWARE

  buf = io.StringIO()
  with redirect_stdout(buf), redirect_stderr(buf):
    print("no panda found, entering DFU recovery...")
    HARDWARE.recover_internal_panda()
    if not Panda.wait_for_dfu(None, 15):
      print("DFU not found")
      return [], buf.getvalue()
    dfu = PandaDFU(None)
    print("DFU mcu:", dfu.get_mcu_type())
    dfu.recover()
    dfu.reset()
    time.sleep(2)
    if not Panda.wait_for_panda(None, 30):
      print("panda did not come back after DFU recover")
      return [], buf.getvalue()
    serials = Panda.list()
    print("pandas after DFU:", serials)
  return serials, buf.getvalue()


def flash_serial(serial: str, *, fw_path: Path | None = None) -> dict[str, Any]:
  """Flash one F4 panda. Returns structured result (no process exit codes)."""
  from panda import Panda

  fw = fw_path or _fw_path()
  log = io.StringIO()

  def _log(msg: str) -> None:
    log.write(msg + "\n")

  try:
    p = Panda(serial)
    _log(f"serial: {serial}")
    _log(f"bootstub: {p.bootstub}")
    _log(f"hw_type: {p.get_type()!r}")
    _log(f"internal: {p.is_internal()}")
    _log(f"mcu: {p.get_mcu_type()}")

    if not fw.is_file():
      p.close()
      return {"ok": False, "error": f"missing firmware: {fw}", "log": log.getvalue()}

    expected = Panda.get_signature_from_firmware(str(fw))
    _log(f"expected sig: {expected.hex()[:16]}")
    if not p.bootstub:
      try:
        current_sig = p.get_signature()
        _log(f"current sig: {current_sig.hex()[:16]}")
        _log(f"health pkt: {p.get_packets_versions()}")
        if current_sig == expected:
          _log("firmware already matches, no flash needed")
          p.close()
          return {"ok": True, "skipped": True, "serial": serial, "log": log.getvalue()}
      except Exception as e:
        _log(f"health read error: {e}")

    _log(f"flashing {fw}")
    code = fw.read_bytes()
    mcu_type = p.get_mcu_type()
    if not p.bootstub:
      try:
        p._handle.controlWrite(Panda.REQUEST_IN, 0xd1, 1, 0, b'', timeout=15000, expect_disconnect=True)
      except Exception:
        pass
      p.close()
      time.sleep(1)
      p = Panda(serial)
    if not p.bootstub:
      p.close()
      return {"ok": False, "error": "failed to enter bootstub", "log": log.getvalue()}

    Panda.flash_static(p._handle, code, mcu_type=mcu_type)
    p.close()

    time.sleep(2)
    p2 = Panda(serial)
    _log(f"after flash bootstub: {p2.bootstub}")
    _log(f"version: {p2.get_version()}")
    _log(f"signature: {p2.get_signature().hex()[:16]}")
    _log(f"health pkt: {p2.get_packets_versions()}")
    ok = (not p2.bootstub) and p2.get_signature() == expected
    p2.close()
    _log("OK" if ok else "FAILED")
    return {
      "ok": ok,
      "serial": serial,
      "flash_ok": ok,
      "log": log.getvalue(),
    }
  except Exception as e:
    return {"ok": False, "error": str(e), "log": log.getvalue()}


def execute_recover_dos_panda(
  *,
  serial: str = "",
  external: bool = False,
  internal: bool = False,
  try_dfu: bool = True,
) -> dict[str, Any]:
  """Core recover/flash implementation (no subprocess, no external script)."""
  try:
    from panda import Panda
  except ImportError as e:
    return {"ok": False, "error": f"panda module unavailable: {e}"}

  fw = _fw_path()
  if not fw.is_file():
    return {"ok": False, "error": f"missing firmware: {fw}", "hint": "build_panda_firmware first"}

  logs: list[str] = []
  serials = Panda.list()
  logs.append(f"pandas: {serials}")
  for s in serials:
    logs.append(f"  {_describe_panda(s)}")

  if not serials and try_dfu:
    serials, dfu_log = recover_dfu()
    logs.append(dfu_log)
    if not serials:
      return {"ok": False, "error": "no panda after DFU", "log": "\n".join(logs), "implementation": "inline"}

  if not serials:
    return {"ok": False, "error": "no panda found", "log": "\n".join(logs), "implementation": "inline"}

  if serial:
    if serial not in serials:
      return {"ok": False, "error": f"serial not found: {serial}", "log": "\n".join(logs)}
    target = serial
  else:
    target = pick_serial(serials, external=external, internal=internal)
    if target is None:
      kind = "external" if external else ("internal" if internal else "F4")
      return {"ok": False, "error": f"no {kind} panda found", "log": "\n".join(logs)}
  logs.append(f"selected: {target}")

  result = flash_serial(target, fw_path=fw)
  result["log"] = "\n".join(logs) + "\n" + result.get("log", "")
  result["implementation"] = "inline"
  result["recover_script_present"] = _tool_script(RECOVER_SCRIPT).is_file()
  return result


def list_all_pandas() -> dict[str, Any]:
  """List all USB pandas with MCU/hw_type, multi-panda scenario, and pandad process snapshot."""
  try:
    from panda import Panda
  except ImportError as e:
    return {"ok": False, "error": f"panda module unavailable: {e}"}

  serials = Panda.list()
  entries = [_describe_panda(s) for s in serials]
  f4 = [e for e in entries if e.get("is_f4")]
  h7 = [e for e in entries if e.get("is_h7")]
  multi = _analyze_multi_panda(entries)
  pandad = _pandad_process_snapshot()
  fw = _fw_path()
  tici_fw = _tici_fw_path()
  script = _tool_script(RECOVER_SCRIPT)
  guidance = _firmware_scenario_guidance(multi)
  hint = guidance.get("summary_zh", "")
  if multi.get("heterogeneous_f4_h7"):
    hint += " 若 GUI Panda 否且 pgrep 无 pandad，先 rebuild_pandad(confirm=true) 并查 USBErrorBusy。"
  elif multi.get("needs_pandad_dual_usb"):
    hint += " 双 Panda USB：确认 pgrep -af pandad 含两个 serial。"

  return {
    "ok": True,
    "serials": serials,
    "pandas": entries,
    "f4_pandas": f4,
    "h7_pandas": h7,
    "multi_panda": multi,
    "pandad": pandad,
    "firmware_path": str(fw),
    "firmware_exists": fw.is_file(),
    "tici_firmware_path": str(tici_fw),
    "tici_firmware_exists": tici_fw.is_file(),
    "firmware_guidance": guidance,
    "recover_script": str(script),
    "recover_script_present": script.is_file(),
    "flash_implementation": "inline (ai.tools.domains.platform.panda_flash_tools); script optional",
    "hint": hint,
  }


def list_f4_pandas() -> dict[str, Any]:
  """List connected F4 pandas (DOS/black) with internal/external hints."""
  listing = list_all_pandas()
  if not listing.get("ok"):
    return listing
  return {
    "ok": True,
    "serials": listing.get("serials", []),
    "pandas": listing.get("pandas", []),
    "f4_pandas": listing.get("f4_pandas", []),
    "h7_pandas": listing.get("h7_pandas", []),
    "multi_panda": listing.get("multi_panda"),
    "pandad": listing.get("pandad"),
    "firmware_path": listing.get("firmware_path"),
    "firmware_exists": listing.get("firmware_exists"),
    "recover_script": listing.get("recover_script"),
    "recover_script_present": listing.get("recover_script_present"),
    "flash_implementation": listing.get("flash_implementation"),
    "hint": listing.get("hint"),
  }


def _scons_board(board_dir: Path, *, jobs: int, firmware_path: Path) -> dict[str, Any]:
  if not board_dir.is_dir():
    return {"ok": False, "error": f"missing board dir: {board_dir}"}
  if not shutil_which("scons"):
    return {"ok": False, "error": "scons not found in PATH"}
  jobs = max(1, min(int(jobs or 4), 32))
  try:
    proc = subprocess.run(
      ["scons", f"-j{jobs}"],
      cwd=str(board_dir),
      env=_sub_env(),
      capture_output=True,
      text=True,
      timeout=600,
    )
    return {
      "ok": proc.returncode == 0 and firmware_path.is_file(),
      "returncode": proc.returncode,
      "board_dir": str(board_dir),
      "firmware_path": str(firmware_path),
      "firmware_exists": firmware_path.is_file(),
      "stdout_tail": (proc.stdout or "")[-2000:],
      "stderr_tail": (proc.stderr or "")[-1000:],
    }
  except subprocess.TimeoutExpired:
    return {"ok": False, "error": "scons timed out after 600s", "board_dir": str(board_dir)}
  except Exception as e:
    return {"ok": False, "error": str(e), "board_dir": str(board_dir)}


def build_panda_h7_firmware(*, jobs: int = 4) -> dict[str, Any]:
  """Compile H7 firmware from panda/board (panda_h7.bin.signed)."""
  board = openpilot_root() / "panda" / "board"
  fw = _tici_fw_path()
  if not board.is_dir():
    return {
      "ok": False,
      "error": f"missing panda/board at {board}",
      "hint": "git submodule update --init panda",
      "kind": "h7",
    }
  result = _scons_board(board, jobs=jobs, firmware_path=fw)
  result["kind"] = "h7"
  return result


def build_panda_tici_firmware(*, jobs: int = 4) -> dict[str, Any]:
  """Deprecated alias — H7 firmware now builds from panda/board."""
  out = build_panda_h7_firmware(jobs=jobs)
  out["deprecated_alias"] = "build_panda_tici_firmware → build_panda_h7_firmware"
  return out


def build_panda_firmware(*, jobs: int = 4, target: str = "auto") -> dict[str, Any]:
  """
  Compile Panda firmware from the openpilot tree.

  target:
    auto — from connected pandas (via list_all_pandas); C3 single F4 → panda/ only
    f4   — panda/board (panda.bin.signed)
    h7   — panda/board (panda_h7.bin.signed, same scons as F4)
    all  — scons panda/board (both binaries)
  """
  listing = list_all_pandas()
  multi = listing.get("multi_panda") if listing.get("ok") else None
  guidance = _firmware_scenario_guidance(multi)
  target = (target or "auto").strip().lower()
  if target == "auto":
    build_f4 = bool(guidance.get("build_f4"))
    build_h7 = bool(guidance.get("build_h7"))
  elif target == "f4":
    build_f4, build_h7 = True, False
  elif target == "h7":
    build_f4, build_h7 = False, True
  elif target == "all":
    build_f4, build_h7 = True, True
  else:
    return {"ok": False, "error": f"unknown target: {target}", "allowed_targets": ["auto", "f4", "h7", "all"]}

  out: dict[str, Any] = {
    "ok": True,
    "target": target,
    "guidance": guidance,
    "build_f4": build_f4,
    "build_h7": build_h7,
    "firmware_policy": FIRMWARE_POLICY,
  }
  parts: list[dict[str, Any]] = []
  if build_f4:
    board = openpilot_root() / "panda" / "board"
    f4 = _scons_board(board, jobs=jobs, firmware_path=_fw_path())
    f4["kind"] = "f4"
    out["f4"] = f4
    parts.append(f4)
  if build_h7:
    h7 = build_panda_h7_firmware(jobs=jobs)
    out["h7"] = h7
    parts.append(h7)
  if not parts:
    out["ok"] = False
    out["error"] = "nothing to build for this target/scenario"
  else:
    out["ok"] = all(p.get("ok") for p in parts)
  out["firmware_path"] = str(_fw_path())
  out["firmware_exists"] = _fw_path().is_file()
  out["tici_firmware_path"] = str(_tici_fw_path())
  out["tici_firmware_exists"] = _tici_fw_path().is_file()
  return out


def rebuild_pandad(*, confirm: bool = False) -> dict[str, Any]:
  """Re-link pandad binary after git reset (offroad)."""
  script = _tool_script(REBUILD_SCRIPT)
  pandad_dir = source_path("selfdrive", "pandad")
  if not script.is_file() and not pandad_dir.is_dir():
    return {
      "ok": False,
      "error": "pandad not found in this tree",
      "hint": "ai/scripts/rebuild_pandad.sh or full scons selfdrive/pandad",
    }
  if not confirm:
    return {
      "ok": True,
      "needs_confirmation": True,
      "script": str(script) if script.is_file() else None,
      "hint": "Set confirm=true to run rebuild (offroad only).",
    }
  if not script.is_file():
    return {
      "ok": False,
      "error": f"missing {script}",
      "hint": "Run full scons or manager_control(rebuild).",
      "pandad_dir": str(pandad_dir),
    }
  try:
    proc = subprocess.run(
      ["bash", str(script)],
      cwd=str(openpilot_root()),
      env=_sub_env(),
      capture_output=True,
      text=True,
      timeout=300,
    )
    return {
      "ok": proc.returncode == 0,
      "returncode": proc.returncode,
      "stdout": (proc.stdout or "")[-3000:],
      "stderr": (proc.stderr or "")[-1000:],
    }
  except Exception as e:
    return {"ok": False, "error": str(e)}


def rebuild_pandad_tici(*, confirm: bool = False) -> dict[str, Any]:
  """Deprecated alias for rebuild_pandad."""
  out = rebuild_pandad(confirm=confirm)
  out["deprecated_alias"] = "rebuild_pandad_tici → rebuild_pandad"
  return out


def recover_dos_panda(
  *,
  confirm: bool = False,
  serial: str = "",
  external: bool = False,
  internal: bool = False,
  build_firmware: bool = False,
) -> dict[str, Any]:
  """
  Flash F4 panda with panda/ firmware.
  Requires confirm=true. Offroad required. Works without ai/scripts/recover_dos_panda.py.
  """
  listing = list_f4_pandas()
  fw = _fw_path()
  script = _tool_script(RECOVER_SCRIPT)
  preview = {
    "firmware_path": str(fw),
    "firmware_exists": fw.is_file(),
    "f4_pandas": listing.get("f4_pandas", []),
    "recover_script_present": script.is_file(),
    "implementation": "inline (no script required)",
    "target": {
      "serial": serial or None,
      "external": external,
      "internal": internal,
      "default": "internal F4 preferred" if not (serial or external or internal) else None,
    },
    "build_firmware": build_firmware,
    "warnings": [
      "内置 DOS / 外接黑熊必须用 panda/board/obj/panda.bin.signed",
      "F4 勿用 Panda.flash()（H7 由 pandad 刷写）",
      "刷机后可 rebuild_pandad(confirm=true) 或 reboot",
    ],
  }

  if not confirm:
    preview = _attach_offroad_flash_policy(preview)
    if not preview.get("flash_allowed"):
      return {
        "ok": False,
        "needs_confirmation": False,
        "onroad": preview.get("onroad"),
        "error": preview.get("flash_blocked_reason") or OFFROAD_FLASH_ERROR,
        "preview": preview,
      }
    return {"ok": True, "needs_confirmation": True, "preview": preview, "hint": "Set confirm=true to flash (offroad)."}

  blocked = offroad_flash_guard()
  if blocked:
    return blocked

  if build_firmware and not fw.is_file():
    built = build_panda_firmware(target="auto")
    if not built.get("ok"):
      return {"ok": False, "error": "firmware build failed", "build": built}

  if not fw.is_file():
    return {
      "ok": False,
      "error": f"missing firmware: {fw}",
      "hint": "Run with build_firmware=true or scons in panda/board first.",
    }

  result = execute_recover_dos_panda(
    serial=serial.strip(),
    external=external,
    internal=internal,
    try_dfu=True,
  )
  result["next_steps"] = [
    "rebuild_pandad(confirm=true)",
    "reboot_device",
    "panda_status to verify",
  ]
  return result


def panda_recovery_hint(get_state_reader=None) -> dict[str, Any]:
  """Suggest recovery steps when pandaStates empty or sidebar shows NO PANDA."""
  listing = list_all_pandas()
  live: list[Any] = []
  if get_state_reader is not None:
    try:
      reader = get_state_reader()
      reader.update(timeout=0)
      full = reader.latest()
      if isinstance(full, dict):
        live = full.get("pandaStates") or []
    except Exception:
      pass

  multi = listing.get("multi_panda") or {}
  pandad = listing.get("pandad") or {}
  usb_count = multi.get("count", 0)
  scenario = multi.get("scenario")

  steps: list[str] = ["panda_status", "list_all_pandas", "device_health", "grep_log pandad|panda|xhci|USBErrorBusy"]
  diagnosis: list[str] = []

  if usb_count >= 2 and not live:
    diagnosis.append(f"USB 可见 {usb_count} 只 Panda 但 pandaStates 为空")
    if scenario == "heterogeneous_f4_h7":
      diagnosis.append("场景：内置 F4 (DOS) + 外接 H7 (红熊)，双 USB 非官方 SPI+H7 组合")
    elif scenario:
      diagnosis.append(f"多 Panda 场景：{scenario}")

  if pandad.get("possible_crash_loop"):
    diagnosis.append("manager.log 含 USBErrorBusy/exitcode -6，pandad 可能崩溃循环")
    steps.extend([
      "grep_log USBErrorBusy|exitcode -6|pandad — 确认 pandad 崩溃",
      "rebuild_pandad(confirm=true) — offroad，双 USB libusb_open 修复后需重链二进制",
      "reboot_device",
    ])
  elif usb_count >= 2 and not pandad.get("running"):
    diagnosis.append("pgrep 无 pandad 进程，但 USB 已枚举多 Panda")
    steps.append("rebuild_pandad(confirm=true) — offroad")

  if not listing.get("firmware_exists"):
    diagnosis.append("缺少 panda/board/obj/panda.bin.signed（F4 固件未编译或 panda 子模块未移植 F4）")
    steps.insert(0, "build_panda_firmware — scons panda/board 生成固件（ai 不内置 panda.bin.signed）")
    steps.insert(1, "读 ai/docs/PANDA_C3_F4_PORTING.md — 合入 panda@7d703710 + sp@43d4f56f + opendbc@3244efe")

  if not live:
    steps.extend([
      "tsk_restart_pandad(confirm=true) — offroad",
      "若仍 NO PANDA：list_f4_pandas → recover_dos_panda(confirm=true)（仅 F4）",
      "C3 内置：recover_dos_panda(internal=true)；外接 aux 黑熊：external=true",
      "外接红熊 (H7) 勿用 recover_dos_panda；由 pandad 自动刷 panda_h7.bin.signed",
      "无需 ai/scripts/recover_dos_panda.py，op 助手内联刷机",
    ])
    if usb_count >= 2:
      steps.append("验证：pgrep -af pandad 应含两个 serial（内置+外接）")
  try:
    from ai.tsk.lib.panda_connect import tici_info

    info = tici_info()
    device_type = info.get("device_type")
    if device_type == "tici":
      steps.append("C3 DOS：F4 固件 panda.bin.signed；单内置走 DOS 快速路径不自动刷机")
      if scenario == "heterogeneous_f4_h7":
        steps.append(
          "异构双 Panda：pandad 须 set_aux_panda + 双 serial；"
          "has_non_h7_panda 用于 BOARDD_SKIP_FW_CHECK"
        )
  except Exception:
    pass

  return {
    "ok": True,
    "panda_states_count": len(live),
    "usb_pandas": listing.get("pandas", []),
    "usb_f4": listing.get("f4_pandas", []),
    "usb_h7": listing.get("h7_pandas", []),
    "multi_panda": multi,
    "pandad": pandad,
    "diagnosis": diagnosis,
    "firmware_exists": listing.get("firmware_exists"),
    "recover_script_present": listing.get("recover_script_present"),
    "recommended_steps": steps,
    "skill": "c3-dos-panda",
    "doc": "ai/docs/PANDA_FLASH.md",
    "porting_doc": "ai/docs/PANDA_C3_F4_PORTING.md",
    "firmware_policy": FIRMWARE_POLICY,
    "reference_commits": {
      "panda": "7d703710",
      "openpilot": "43d4f56f",
      "opendbc_repo": "3244efe",
    },
  }


def _resolve_pandad_flash():
  """Import flash_panda + get_expected_signature from the active pandad wrapper."""
  for modname in ("openpilot.selfdrive.pandad.pandad",):
    try:
      mod = __import__(modname, fromlist=["flash_panda", "get_expected_signature"])
      return mod.flash_panda, mod.get_expected_signature, modname
    except ImportError:
      continue
  return None, None, None


def _panda_signature_info(serial: str, entry: dict[str, Any]) -> dict[str, Any]:
  """Attach firmware signature match info for one panda."""
  out = dict(entry)
  try:
    from panda import Panda

    p = Panda(serial)
    cur = b"" if p.bootstub else p.get_signature()
    exp = b""
    if entry.get("is_f4"):
      fw = _fw_path()
      if fw.is_file():
        exp = Panda.get_signature_from_firmware(str(fw))
    elif entry.get("is_h7"):
      _, get_sig, _ = _resolve_pandad_flash()
      if get_sig is not None:
        exp = get_sig(p)
    out["signature"] = cur.hex()[:16] if cur else None
    out["expected_signature"] = exp.hex()[:16] if exp else None
    out["firmware_match"] = (cur == exp) if (cur and exp) else None
    out["bootstub"] = p.bootstub
    p.close()
  except Exception as e:
    out["firmware_match"] = None
    out["status_error"] = str(e)
  return out


def panda_firmware_status() -> dict[str, Any]:
  """List pandas with firmware signature match (read-only)."""
  listing = list_all_pandas()
  if not listing.get("ok"):
    return listing

  enriched: list[dict[str, Any]] = []
  for entry in listing.get("pandas", []):
    if "error" in entry:
      enriched.append({**entry, "firmware_match": None})
      continue
    enriched.append(_panda_signature_info(entry["serial"], entry))

  matches = [e.get("firmware_match") for e in enriched if e.get("firmware_match") is not None]
  listing["pandas"] = enriched
  listing["all_firmware_match"] = bool(matches) and all(matches)
  listing["any_firmware_mismatch"] = any(e.get("firmware_match") is False for e in enriched)
  listing["firmware_guidance"] = listing.get("firmware_guidance") or _firmware_scenario_guidance(
    listing.get("multi_panda")
  )
  listing["tici_firmware_path"] = str(_tici_fw_path())
  listing["tici_firmware_exists"] = _tici_fw_path().is_file()
  flash_fn, _, flash_source = _resolve_pandad_flash()
  listing["h7_flash_source"] = flash_source
  listing["h7_flash_available"] = flash_fn is not None
  return _attach_offroad_flash_policy(listing)


def flash_h7_serial(serial: str) -> dict[str, Any]:
  """Flash one H7 panda via pandad flash_panda."""
  flash_fn, get_sig, source = _resolve_pandad_flash()
  if flash_fn is None:
    return {"ok": False, "error": "pandad flash_panda unavailable", "serial": serial, "hw": "h7"}

  try:
    p = flash_fn(serial)
    sig = p.get_signature()
    exp = get_sig(p) if get_sig else b""
    ok = (not p.bootstub) and bool(exp) and sig == exp
    version = "bootstub" if p.bootstub else p.get_version()
    p.close()
    return {
      "ok": ok,
      "serial": serial,
      "hw": "h7",
      "flash_source": source,
      "version": version,
      "signature": sig.hex()[:16] if sig else None,
      "expected_signature": exp.hex()[:16] if exp else None,
      "skipped": False,
    }
  except Exception as e:
    return {"ok": False, "error": str(e), "serial": serial, "hw": "h7", "flash_source": source}


def flash_panda_firmware(
  *,
  confirm: bool = False,
  serial: str = "",
  all_pandas: bool = True,
  external: bool = False,
  internal: bool = False,
  build_firmware: bool = False,
) -> dict[str, Any]:
  """
  Flash connected pandas with repo firmware (H7 via pandad, F4 via panda/).
  Requires confirm=true. Offroad required.
  """
  status = panda_firmware_status()
  guidance = status.get("firmware_guidance") or {}
  preview = {
    "pandas": status.get("pandas", []),
    "firmware_path": status.get("firmware_path"),
    "firmware_exists": status.get("firmware_exists"),
    "tici_firmware_path": status.get("tici_firmware_path"),
    "tici_firmware_exists": status.get("tici_firmware_exists"),
    "firmware_guidance": guidance,
    "h7_flash_available": status.get("h7_flash_available"),
    "h7_flash_source": status.get("h7_flash_source"),
    "target": {
      "serial": serial or None,
      "all_pandas": all_pandas and not (serial or external or internal),
      "external": external,
      "internal": internal,
    },
    "build_firmware": build_firmware,
    "warnings": [
      "请在 offroad 下刷机；刷机期间 manager/pandad 可能占用 USB（LIBUSB_ERROR_BUSY 可忽略若签名已匹配）",
      "F4/DOS/黑熊 → panda/board/obj/panda.bin.signed；H7/红熊 → panda/board/obj/panda_h7.bin.signed（pandad 刷写）",
      guidance.get("summary_zh") or "单内置 F4：只需 panda/board；外接红熊控车时还须刷 H7 镜像",
      guidance.get("mads_zh") or "",
    ],
  }

  if not confirm:
    preview = _attach_offroad_flash_policy(preview)
    if not preview.get("flash_allowed"):
      return {
        "ok": False,
        "needs_confirmation": False,
        "onroad": preview.get("onroad"),
        "error": preview.get("flash_blocked_reason") or OFFROAD_FLASH_ERROR,
        "preview": preview,
      }
    return {"ok": True, "needs_confirmation": True, "preview": preview, "hint": "Set confirm=true to flash (offroad)."}

  blocked = offroad_flash_guard()
  if blocked:
    return blocked

  if build_firmware:
    need_f4 = guidance.get("build_f4") and not _fw_path().is_file()
    need_h7 = guidance.get("build_h7") and not _tici_fw_path().is_file()
    if need_f4 or need_h7:
      built = build_panda_firmware(target="auto")
      if not built.get("ok"):
        return {"ok": False, "error": "firmware build failed", "build": built}

  try:
    from panda import Panda
  except ImportError as e:
    return {"ok": False, "error": f"panda module unavailable: {e}"}

  serials = Panda.list()
  if not serials:
    serials, dfu_log = recover_dfu()
    if not serials:
      return {"ok": False, "error": "no panda found", "log": dfu_log}

  targets: list[str] = []
  if serial:
    if serial not in serials:
      return {"ok": False, "error": f"serial not found: {serial}", "serials": serials}
    targets = [serial]
  elif external or internal:
    picked = pick_serial(serials, external=external, internal=internal)
    if not picked:
      kind = "external" if external else "internal"
      return {"ok": False, "error": f"no {kind} panda found", "serials": serials}
    targets = [picked]
  elif all_pandas:
    targets = list(serials)
  else:
    picked = pick_serial(serials)
    targets = [picked] if picked else []

  if not targets:
    return {"ok": False, "error": "no flash target", "serials": serials}

  needs_f4 = False
  for target in targets:
    entry = next((e for e in status.get("pandas", []) if e.get("serial") == target), {})
    desc = entry if entry else _describe_panda(target)
    if entry.get("is_f4") or desc.get("is_f4"):
      needs_f4 = True
      break

  pandad_release: dict[str, Any] = {}
  if needs_f4:
    try:
      from ai.tsk.lib.panda_connect import is_manager_running, stop_pandad

      stop_pandad()
      time.sleep(1.5)
      pandad_release = {
        "pandad_stopped": True,
        "manager_running": is_manager_running(),
      }
    except Exception as e:
      pandad_release = {"pandad_stopped": False, "error": str(e)}

  results: list[dict[str, Any]] = []
  for target in targets:
    entry = next((e for e in status.get("pandas", []) if e.get("serial") == target), {})
    if entry.get("is_h7"):
      results.append(flash_h7_serial(target))
    elif entry.get("is_f4"):
      results.append({**flash_serial(target), "hw": "f4"})
    else:
      desc = _describe_panda(target)
      if desc.get("is_h7"):
        results.append(flash_h7_serial(target))
      elif desc.get("is_f4"):
        results.append({**flash_serial(target), "hw": "f4"})
      else:
        results.append({
          "ok": False,
          "serial": target,
          "error": f"unsupported hw_type: {desc.get('hw_type_name', desc.get('hw_type'))}",
        })

  ok = all(r.get("ok") for r in results)
  skipped = all(r.get("skipped") for r in results if r.get("ok"))
  pandad_recovery: dict[str, Any] | None = None
  if ok and needs_f4:
    try:
      from ai.tsk.lib.panda_connect import recover_pandad_after_flash

      pandad_recovery = recover_pandad_after_flash()
    except Exception as e:
      pandad_recovery = {"ok": False, "error": str(e)}
  return {
    "ok": ok,
    "skipped": skipped and ok,
    "results": results,
    "targets": targets,
    "pandad_release": pandad_release,
    "pandad_recovery": pandad_recovery,
    "next_steps": [
      "panda_firmware_status 验证签名",
      "rebuild_pandad(confirm=true) if dual USB",
      "reboot_device",
    ],
  }
