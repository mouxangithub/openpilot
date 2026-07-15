"""TSK SecOC pipeline — part of op 助手 (:5090 settings → SecOC)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import socket
import subprocess
import threading
import time
import traceback
from typing import Any

from ai.tsk.guidance import enrich_failure_response, matcher_next_steps
from ai.tsk.job_control import clear_cancel, is_cancelled, request_cancel
from ai.tsk.lib.collect_can import (
  PROTECTED_TARGET,
  SYNC_TARGET,
  collect as collect_can,
  count_oracle_frames,
  oracle_path as can_oracle_path,
)
from ai.tsk.lib.dump_dataflash import DUMP_TOTAL, dump as dump_dataflash, dump_path
from ai.tsk.lib.env import is_agnos, setup as tsk_env_setup
from ai.tsk.lib.extractor import NotAGNOSError, TSKExtractor
from ai.tsk.lib.key_file_manager import KeyFileManager, format_key
from ai.tsk.lib.matcher import run as run_matcher
from ai.tsk.lib.panda_connect import tici_info

OFFROAD_ALERT_PARAM = "Offroad_NoFirmware"
PING_REPORT = "!!!! 发生意外错误。请截图后发到 #toyota-security 并 @calvinspark"

_public_port: int = 5090
_initialized = False
_init_lock = threading.Lock()

panda_lock = threading.Lock()
matcher_lock = threading.Lock()
can_lock = threading.Lock()
df_lock = threading.Lock()

can_state: dict[str, Any] = {
  "ready": False,
  "status": "idle",
  "sync_count": 0,
  "protected_count": 0,
  "seconds": 0.0,
  "message": "",
}

df_state: dict[str, Any] = {
  "ready": False,
  "status": "idle",
  "frames": 0,
  "bytes": 0,
  "total": DUMP_TOTAL,
  "message": "",
  "size": 0,
}

DRY_RUN_FAKE_KEY = "a1b2c3d4e5f6a7b8a1b2c3d4e5f6a7b8"
dry_run_counter = 0


def configure(*, public_port: int = 5090) -> None:
  global _public_port
  _public_port = int(public_port)


def append_address(addresses: list[str], ip: str) -> None:
  if ip and not ip.startswith("127.") and ip not in addresses:
    addresses.append(ip)


def get_ipv4_addresses() -> list[str]:
  addresses: list[str] = []
  try:
    output = subprocess.check_output(
      ["ip", "-o", "-4", "route", "get", "1.1.1.1"],
      encoding="utf-8",
      stderr=subprocess.DEVNULL,
      timeout=1.0,
    )
    parts = output.split()
    if "src" in parts:
      append_address(addresses, parts[parts.index("src") + 1])
  except (OSError, subprocess.SubprocessError, TimeoutError):
    pass

  try:
    for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
      append_address(addresses, info[4][0])
  except OSError:
    pass

  try:
    output = subprocess.check_output(
      ["ip", "-o", "-4", "addr", "show", "scope", "global"],
      encoding="utf-8",
      stderr=subprocess.DEVNULL,
      timeout=1.0,
    )
    for line in output.splitlines():
      parts = line.split()
      if "inet" not in parts:
        continue
      cidr = parts[parts.index("inet") + 1]
      append_address(addresses, cidr.split("/", 1)[0])
  except (OSError, subprocess.SubprocessError, TimeoutError):
    pass

  return addresses


def get_tsk_url() -> str | None:
  addresses = get_ipv4_addresses()
  return f"http://{addresses[0]}:{_public_port}/?settings=secoc" if addresses else None


def get_params_dir() -> Path:
  params_root = Path(os.getenv("PARAMS_ROOT", "/data/params"))
  params_prefix = os.getenv("OPENPILOT_PREFIX", "d") or "d"
  return params_root / params_prefix


def key_status_payload() -> dict[str, Any]:
  return get_key_status()


def write_offroad_alert(url: str | None) -> bool:
  params_dir = get_params_dir()
  if not params_dir.exists():
    return False

  alert_path = params_dir / OFFROAD_ALERT_PARAM
  if url is None:
    try:
      alert_path.unlink()
    except FileNotFoundError:
      pass
    return True

  payload = json.dumps({
    "text": "丰田 SecOC 安全密钥\n用手机浏览器打开 %1（op助手 → 设置 → SecOC）",
    "severity": 0,
    "extra": url,
  }, sort_keys=True)
  tmp_path = params_dir / f".tmp_{OFFROAD_ALERT_PARAM}_{os.getpid()}"
  with open(tmp_path, "w", encoding="utf-8") as f:
    f.write(payload)
    f.flush()
    os.fsync(f.fileno())
  os.replace(tmp_path, alert_path)
  try:
    dir_fd = os.open(params_dir, os.O_RDONLY)
    try:
      os.fsync(dir_fd)
    finally:
      os.close(dir_fd)
  except OSError:
    pass
  return True


def clear_offroad_alert() -> None:
  try:
    write_offroad_alert(None)
  except OSError as e:
    print(f"TSK: could not clear offroad alert: {e}", flush=True)


def _df_progress(status=None, frames=None, bytes_done=None, total=None, message=None) -> None:
  with df_lock:
    if status is not None:
      df_state["status"] = status
    if frames is not None:
      df_state["frames"] = frames
    if bytes_done is not None:
      df_state["bytes"] = bytes_done
    if total is not None:
      df_state["total"] = total
    if message is not None:
      df_state["message"] = message


def _run_dataflash_mock() -> None:
  for done in (4096, 8192, 16384, 24576, DUMP_TOTAL):
    time.sleep(0.4)
    _df_progress(status="running", frames=done // 4, bytes_done=done, total=DUMP_TOTAL)
  with df_lock:
    df_state.update(
      status="complete", frames=DUMP_TOTAL // 4, bytes=DUMP_TOTAL, total=DUMP_TOTAL,
      size=DUMP_TOTAL, ready=True, message=f"导出完成：{DUMP_TOTAL} 字节（模拟）。",
    )


def _run_dataflash_job() -> None:
  clear_cancel()
  try:
    result = dump_dataflash(progress_cb=_df_progress, should_cancel=is_cancelled)
    status = result.get("status", "failed")
    with df_lock:
      df_state.update(
        status=status,
        frames=result.get("frames", df_state["frames"]),
        bytes=result.get("bytes", df_state["bytes"]),
        total=result.get("total", DUMP_TOTAL),
        message=result.get("message", ""),
        ready=(status == "complete"),
        size=result.get("bytes", 0) if status == "complete" else 0,
      )
  except NotAGNOSError:
    _run_dataflash_mock()
  except Exception as e:
    with df_lock:
      df_state.update(status="failed", message=str(e), ready=False, size=0)
  finally:
    TSKExtractor._close_panda()
    panda_lock.release()


def start_dataflash_job() -> bool:
  if not panda_lock.acquire(blocking=False):
    return False
  with df_lock:
    df_state.update(status="running", frames=0, bytes=0, total=DUMP_TOTAL, message="", ready=False, size=0)
  try:
    threading.Thread(target=_run_dataflash_job, name="tsk_dataflash_dump", daemon=True).start()
  except Exception:
    with df_lock:
      df_state.update(status="failed", message="无法启动 DataFlash 导出任务。", ready=False)
    panda_lock.release()
    return False
  return True


def clear_dataflash() -> bool:
  with df_lock:
    if df_state["status"] == "running":
      return False
    df_state.update(ready=False, status="idle", frames=0, bytes=0, total=DUMP_TOTAL, message="", size=0)
  for path in (dump_path(), Path(str(dump_path()) + ".partial")):
    try:
      path.unlink()
    except (FileNotFoundError, OSError):
      pass
  return True


def rehydrate_dataflash_state() -> None:
  try:
    size = dump_path().stat().st_size
  except OSError:
    size = None
  if size == DUMP_TOTAL:
    with df_lock:
      df_state.update(
        ready=True, status="complete", frames=DUMP_TOTAL // 4, bytes=DUMP_TOTAL,
        total=DUMP_TOTAL, size=DUMP_TOTAL, message="导出完成。",
      )
    return
  try:
    Path(str(dump_path()) + ".partial").stat()
  except OSError:
    return
  with df_lock:
    df_state.update(
      ready=False, status="partial", total=DUMP_TOTAL,
      message="磁盘上有部分导出。\n请尝试「查找丰田 SecOC 密钥」。\n"
              "若仍失败，请熄火并切回 Not Ready to Drive 模式后重新导出。",
    )


def _can_progress(seconds=None, sync=None, protected=None) -> None:
  with can_lock:
    if seconds is not None:
      can_state["seconds"] = seconds
    if sync is not None:
      can_state["sync_count"] = sync
    if protected is not None:
      can_state["protected_count"] = protected


def _run_can_mock() -> None:
  for i in range(1, 7):
    time.sleep(0.4)
    _can_progress(seconds=i * 10.0, sync=i * 10, protected=i * 600)
  with can_lock:
    can_state.update(
      status="complete", ready=True, seconds=60.0, sync_count=60, protected_count=3600,
      message="已采集 60 条 sync 与 3600 条 protected 帧（模拟）。",
    )


def _run_can_job() -> None:
  clear_cancel()
  try:
    result = collect_can(progress_cb=_can_progress, should_cancel=is_cancelled)
    status = result.get("status", "failed")
    with can_lock:
      can_state.update(
        status=status,
        sync_count=result.get("sync", can_state["sync_count"]),
        protected_count=result.get("protected", can_state["protected_count"]),
        message=result.get("message", ""),
        ready=(status == "complete"),
      )
  except NotAGNOSError:
    _run_can_mock()
  except Exception as e:
    with can_lock:
      can_state.update(status="failed", message=str(e), ready=False)
  finally:
    TSKExtractor._close_panda()
    panda_lock.release()


def start_can_job() -> bool:
  if not panda_lock.acquire(blocking=False):
    return False
  with can_lock:
    can_state.update(status="running", sync_count=0, protected_count=0, seconds=0.0, message="", ready=False)
  try:
    threading.Thread(target=_run_can_job, name="tsk_can_collect", daemon=True).start()
  except Exception:
    with can_lock:
      can_state.update(status="failed", message="无法启动 CAN 采集任务。", ready=False)
    panda_lock.release()
    return False
  return True


def clear_can() -> bool:
  with can_lock:
    if can_state["status"] == "running":
      return False
    can_state.update(ready=False, status="idle", sync_count=0, protected_count=0, seconds=0.0, message="")
  try:
    can_oracle_path().unlink()
  except (FileNotFoundError, OSError):
    pass
  return True


def rehydrate_can_state() -> None:
  sync, protected = count_oracle_frames()
  if sync >= SYNC_TARGET and protected >= PROTECTED_TARGET:
    with can_lock:
      can_state.update(
        ready=True, status="complete", sync_count=sync, protected_count=protected,
        message=f"已采集 {sync} 条 sync 与 {protected} 条 protected 帧。",
      )


def get_health() -> dict[str, Any]:
  return {
    "status": "ok",
    "service": "tsk",
    "host": "0.0.0.0",
    "port": _public_port,
    "url": get_tsk_url(),
    "addresses": get_ipv4_addresses(),
    "dry_run": not is_agnos(),
    "is_agnos": is_agnos(),
    **tici_info(),
  }


def get_key_status() -> dict[str, Any]:
  key = KeyFileManager().installed_key
  return {"installed": key is not None, "key": key}


def get_can_status() -> dict[str, Any]:
  with can_lock:
    return dict(can_state)


def get_dataflash_status() -> dict[str, Any]:
  with df_lock:
    return dict(df_state)


def get_summary() -> dict[str, Any]:
  """Combined snapshot for chat progress cards."""
  key = get_key_status()
  can = get_can_status()
  df = get_dataflash_status()
  can_ready = bool(can.get("ready"))
  df_ready = bool(df.get("ready"))
  df_partial = df.get("status") == "partial"
  installed = bool(key.get("installed"))
  busy = (
    can.get("status") == "running"
    or df.get("status") == "running"
    or matcher_lock.locked()
  )
  steps: list[str] = []
  install_options: list[str] = []
  if not installed:
    install_options.extend([
      "RAV4 Prime/Sienna 等：TSK 一键提取（UDS，无需 CAN/DataFlash）",
      "已有密钥：设置 → SecOC → 手动输入安装",
      "2021+ 多数车型：采集 CAN → 导出 DataFlash → 查找密钥",
    ])
  if not can_ready:
    steps.append("采集 CAN（READY 模式）")
  if not (df_ready or df_partial):
    steps.append("导出 DataFlash（Not Ready to Drive）")
  if can_ready and (df_ready or df_partial) and not installed:
    steps.append("查找并安装 SecOC 密钥")
  if installed:
    steps.append("重启设备使密钥生效")
  return {
    "ok": True,
    "url": get_tsk_url(),
    "secoc_key_installed": installed,
    "secoc_key_prefix": (key.get("key") or "")[:8] + "…" if len(key.get("key") or "") >= 8 else "",
    "can": can,
    "dataflash": df,
    "next_steps": steps,
    "install_options": install_options,
    "busy": busy,
    "poll": busy or (not installed and (can_ready or df_ready or df_partial)),
    **tici_info(),
  }


def _extract_dry_run() -> dict[str, Any]:
  global dry_run_counter
  scenario = dry_run_counter % 3
  dry_run_counter += 1
  if scenario == 0:
    KeyFileManager().install_key(DRY_RUN_FAKE_KEY)
    return {
      "ok": True,
      "key": DRY_RUN_FAKE_KEY,
      "message": f"成功！\n\n您的密钥：\n{format_key(DRY_RUN_FAKE_KEY)}\n\n请立即截图保存。",
    }
  if scenario == 1:
    from ai.tsk.lib.panda_connect import pandad_process_name

    proc = pandad_process_name()
    return {
      "ok": False,
      "message": (
        f"{proc} 未在运行。\n\n请重试。若问题持续，请熄火并将车辆切回「Not Ready to Drive」模式后再试。"
        f"\n\n{PING_REPORT}"
      ),
    }
  return {
    "ok": False,
    "message": (
      "UDS 请求超时\n\n"
      f"{PING_REPORT}\n"
    ),
  }


def run_extract() -> dict[str, Any]:
  if not panda_lock.acquire(blocking=False):
    return {"ok": False, "message": "另一项 Panda 操作（导出或 CAN 采集）正在进行中。"}
  try:
    secoc_key = TSKExtractor.hack()
    KeyFileManager().install_key(secoc_key)
    return {
      "ok": True,
      "key": secoc_key,
      "message": f"成功！\n\n您的密钥：\n{format_key(secoc_key)}\n\n请立即截图保存。",
      **get_key_status(),
    }
  except NotAGNOSError:
    return _extract_dry_run()
  except Exception as e:
    tb = traceback.format_exc()
    return {"ok": False, "message": f"{e}\n\n{tb}\n\n{PING_REPORT}"}
  finally:
    TSKExtractor._close_panda()
    panda_lock.release()


def run_match_and_install() -> dict[str, Any]:
  if not matcher_lock.acquire(blocking=False):
    return {"ok": False, "status": "running", "message": "密钥查找已在运行中。"}
  try:
    result = run_matcher()
    if result["status"] == "found":
      KeyFileManager().install_key(result["key"])
      detail = (
        f"在 {result['address']} 找到 — {result['matches']} 次匹配 "
        f"（sync {result['sync']}，protected {result['protected']}）。"
      )
      message = f"您的密钥：\n{format_key(result['key'])}\n\n{detail}\n\n请立即截图保存。"
      return {
        "ok": True,
        "status": "found",
        "key": result["key"],
        "message": message,
        "next_steps": matcher_next_steps({"status": "found"}),
        **get_key_status(),
      }
    failure = enrich_failure_response({
      "ok": False,
      "status": result["status"],
      "message": result["message"],
      "matches": result.get("matches"),
      "sync": result.get("sync"),
      "protected": result.get("protected"),
      "address": result.get("address"),
      "offset": result.get("offset"),
      "windows_scanned": result.get("windows_scanned"),
      "survivors": result.get("survivors"),
      "malformed": result.get("malformed"),
      "dump_partial": result.get("dump_partial"),
    })
    return failure
  except Exception as e:
    tb = traceback.format_exc()
    return {"ok": False, "status": "error", "message": f"{e}\n\n{tb}\n\n{PING_REPORT}", "traceback": tb}
  finally:
    matcher_lock.release()


def run_install_key(key_raw: str) -> dict[str, Any]:
  key = re.sub(r"[^0-9a-fA-F]", "", (key_raw or "").strip()).lower()
  if len(key) != 32:
    return {
      "ok": False,
      "message": "密钥须为 32 位十六进制字符（可含空格或冒号分隔）。",
      **get_key_status(),
    }
  try:
    mgr = KeyFileManager()
    mgr.install_key(key)
    if mgr.installed_key != key:
      return {
        "ok": False,
        "message": "安装失败，请确认车辆已 offroad 且存储路径可写。",
        **get_key_status(),
      }
    return {
      "ok": True,
      "key": key,
      "message": f"密钥已安装：\n{format_key(key)}\n\n请重启设备使密钥生效。",
      **get_key_status(),
    }
  except Exception as e:
    return {
      "ok": False,
      "message": str(e),
      "traceback": traceback.format_exc(),
      **get_key_status(),
    }


def run_uninstall() -> dict[str, Any]:
  try:
    key_manager = KeyFileManager()
    key_was_installed = key_manager.installed_key is not None
    key_manager.uninstall_key()
    return {
      "ok": True,
      "title": "密钥已移除" if key_was_installed else "密钥未安装",
      "message": "已移除已安装的密钥。" if key_was_installed else "没有可移除的密钥。",
      **get_key_status(),
    }
  except Exception as e:
    return {
      "ok": False,
      "title": "意外错误",
      "message": str(e),
      "traceback": traceback.format_exc(),
      **get_key_status(),
    }


def run_can_collect_start() -> dict[str, Any]:
  if start_can_job():
    return {"ok": True, "status": "running"}
  return {"ok": False, "status": "running", "message": "CAN 采集或其他 Panda 操作已在进行中。"}


def run_dataflash_dump_start() -> dict[str, Any]:
  if start_dataflash_job():
    return {"ok": True, "status": "running"}
  return {"ok": False, "status": "running", "message": "DataFlash 导出或其他 Panda 操作已在进行中。"}


def run_clear_cache() -> dict[str, Any]:
  with can_lock:
    can_running = can_state["status"] == "running"
  with df_lock:
    df_running = df_state["status"] == "running"
  if can_running or df_running:
    return {"ok": False, "status": "running", "message": "采集或导出正在进行中。请等待完成后再清除。"}
  clear_can()
  clear_dataflash()
  return {"ok": True}


def run_reboot_device() -> dict[str, Any]:
  from ai.tools.system_control_tools import reboot_device

  return reboot_device()


def run_restart_manager() -> dict[str, Any]:
  from ai.tools.system_control_tools import manager_control

  return manager_control("restart")


def run_restart_pandad() -> dict[str, Any]:
  from ai.tsk.lib.panda_connect import restart_pandad

  return restart_pandad()


def get_offroad_alert_status() -> dict[str, Any]:
  alert_path = get_params_dir() / OFFROAD_ALERT_PARAM
  url = get_tsk_url()
  try:
    exists = alert_path.exists()
    payload = json.loads(alert_path.read_text(encoding="utf-8")) if exists else None
  except (OSError, json.JSONDecodeError):
    exists = False
    payload = None
  return {
    "ok": True,
    "alert_active": bool(exists),
    "url": url,
    "payload": payload,
  }


def wait_for_job(*, job: str = "can", timeout_seconds: float = 600) -> dict[str, Any]:
  job = (job or "can").lower().strip()
  if job not in ("can", "dataflash", "match"):
    return {"ok": False, "error": "job 须为 can、dataflash 或 match。"}
  deadline = time.time() + max(1.0, float(timeout_seconds))
  while time.time() < deadline:
    if job == "can":
      st = get_can_status()
      if st.get("status") != "running":
        ok = st.get("status") == "complete"
        out: dict[str, Any] = {
          "ok": ok,
          "job": "can",
          "status": st.get("status"),
          "can": st,
        }
        if st.get("message"):
          out["message"] = st.get("message")
        if not ok:
          out.update(enrich_failure_response({"status": st.get("status"), "message": st.get("message", "")}))
        return out
    elif job == "dataflash":
      st = get_dataflash_status()
      if st.get("status") != "running":
        ok = st.get("status") in ("complete", "partial")
        out = {
          "ok": ok,
          "job": "dataflash",
          "status": st.get("status"),
          "dataflash": st,
        }
        if st.get("message"):
          out["message"] = st.get("message")
        if not ok:
          out.update(enrich_failure_response({"status": st.get("status"), "message": st.get("message", "")}))
        return out
    elif job == "match":
      if not matcher_lock.locked():
        return {"ok": True, "job": "match", "status": "idle", "message": "密钥查找未在运行。"}
    time.sleep(0.5)
  return {
    "ok": False,
    "job": job,
    "status": "timeout",
    "message": f"等待 {job} 超时（{int(timeout_seconds)}s）。",
  }


def run_cancel_job(job: str = "all") -> dict[str, Any]:
  job = (job or "all").lower().strip()
  if job not in ("can", "dataflash", "all"):
    return {"ok": False, "message": "job 须为 can、dataflash 或 all。"}
  with can_lock:
    can_running = can_state.get("status") == "running"
  with df_lock:
    df_running = df_state.get("status") == "running"
  if job == "can" and not can_running:
    return {"ok": False, "message": "CAN 采集未在运行。"}
  if job == "dataflash" and not df_running:
    return {"ok": False, "message": "DataFlash 导出未在运行。"}
  if job == "all" and not can_running and not df_running:
    return {"ok": False, "message": "没有正在运行的 CAN 或 DataFlash 任务。"}
  request_cancel()
  TSKExtractor._close_panda()
  cancelled: list[str] = []
  if job in ("can", "all") and can_running:
    with can_lock:
      if can_state.get("status") == "running":
        can_state.update(status="cancelled", message="CAN 采集已取消。", ready=False)
    cancelled.append("can")
  if job in ("dataflash", "all") and df_running:
    with df_lock:
      if df_state.get("status") == "running":
        df_state.update(
          status="cancelled",
          message="DataFlash 导出已取消。",
          ready=False,
          size=0,
        )
    cancelled.append("dataflash")
  return {
    "ok": True,
    "cancelled": cancelled,
    "message": f"已取消：{', '.join(cancelled)}。" if cancelled else "已发送取消请求。",
  }


def run_secoc_pipeline(
  *,
  skip_can: bool = False,
  skip_dataflash: bool = False,
  can_timeout_seconds: float = 120,
  dataflash_timeout_seconds: float = 300,
) -> dict[str, Any]:
  """Run CAN → DataFlash → find/install when prerequisites are missing."""
  steps: list[dict[str, Any]] = []
  summary = get_summary()
  if summary.get("secoc_key_installed"):
    return {"ok": True, "status": "already_installed", "message": "SecOC 密钥已安装。", "steps": steps}

  can = summary.get("can") or {}
  if not skip_can and not can.get("ready"):
    start = run_can_collect_start()
    steps.append({"step": "can_start", **start})
    if not start.get("ok"):
      return {"ok": False, "steps": steps, **start}
    wait = wait_for_job(job="can", timeout_seconds=can_timeout_seconds)
    steps.append({"step": "can_wait", **wait})
    if not wait.get("ok"):
      return {"ok": False, "steps": steps, "status": "can_failed", **wait}

  summary = get_summary()
  df = summary.get("dataflash") or {}
  df_ok = bool(df.get("ready")) or df.get("status") == "partial"
  if not skip_dataflash and not df_ok:
    start = run_dataflash_dump_start()
    steps.append({"step": "dataflash_start", **start})
    if not start.get("ok"):
      return {"ok": False, "steps": steps, **start}
    wait = wait_for_job(job="dataflash", timeout_seconds=dataflash_timeout_seconds)
    steps.append({"step": "dataflash_wait", **wait})
    if not wait.get("ok"):
      return {"ok": False, "steps": steps, "status": "dataflash_failed", **wait}

  match = run_match_and_install()
  steps.append({"step": "match", "ok": match.get("ok"), "status": match.get("status")})
  out = dict(match)
  out["steps"] = steps
  return out


def initialize(*, public_port: int = 5090) -> None:
  global _initialized
  with _init_lock:
    if _initialized:
      configure(public_port=public_port)
      return
    from ai.tsk.lib.panda_connect import ensure_tici_env

    ensure_tici_env()
    configure(public_port=public_port)
    tsk_env_setup()
    rehydrate_dataflash_state()
    rehydrate_can_state()
    clear_offroad_alert()
    _initialized = True
