#!/usr/bin/env python3
"""Collect the CAN oracle: capture sync + protected SecOC frames for the matcher.

Vehicle requirement: READY Mode (hybrid system on) so the protected frames are actively
signed. Writes can_oracle.ndjson (one raw CAN frame per line, {addr, bus, ts_ms,
data}) that tsk/lib/matcher.py reads.

Shares the panda-takeover preamble with dump_dataflash.py / extractor.py by
deliberate duplication: this is a distinct operation — a read-only bus capture with
no UDS session — kept independently testable rather than coupled through a helper.
"""
import json
import time
from pathlib import Path

from ai.tsk.lib.env import CAN_ORACLE_PATH, is_agnos
from ai.tsk.lib.extractor import NotAGNOSError, TSKExtractor
from ai.tsk.lib.panda_connect import stop_manager_and_pandad

SYNC_ADDR = 0x0F
PROTECTED_ADDRS = {0x131, 0x2E4, 0x344}
ORACLE_BUSES = {0, 2}

# UI/ready thresholds (raw frame counts, matching the index row's "N/50", "N/30").
SYNC_TARGET = 50
PROTECTED_TARGET = 30
COLLECT_SECONDS = 60.0  # hard cap; collection stops early once both targets are met


def oracle_path() -> Path:
  return Path(CAN_ORACLE_PATH)


def _noop(**kwargs) -> None:
  pass


def count_oracle_frames(path=None) -> tuple:
  """Count (sync_frames, protected_frames) in a persisted oracle; (0, 0) if missing.

  Skips malformed lines, matching the matcher's loader, so a torn capture is counted
  legibly rather than raising.
  """
  p = Path(path) if path is not None else oracle_path()
  sync = 0
  protected = 0
  try:
    with p.open("r", encoding="utf-8") as f:
      for line in f:
        if not line.strip():
          continue
        try:
          r = json.loads(line)
          addr = int(r["addr"])
          bus = int(r["bus"])
        except (ValueError, KeyError, TypeError):
          continue
        if bus not in ORACLE_BUSES:
          continue
        if addr == SYNC_ADDR:
          sync += 1
        elif addr in PROTECTED_ADDRS:
          protected += 1
  except OSError:
    return 0, 0
  return sync, protected


def collect(progress_cb=None, seconds=COLLECT_SECONDS, should_cancel=None) -> dict:
  """Capture SecOC oracle frames for up to `seconds` and write can_oracle.ndjson.

  progress_cb, if given, is called as progress_cb(seconds=, sync=, protected=).
  Returns {status, sync, protected, oracle_path, message} where status is one of:
    complete | insufficient | failed. Raises NotAGNOSError off-device.
  """
  if not is_agnos():
    raise NotAGNOSError

  cb = progress_cb or _noop

  from opendbc.car.structs import CarParams

  stop_manager_and_pandad()

  panda = TSKExtractor._connect_panda()
  panda.set_safety_mode(CarParams.SafetyModel.elm327)

  path = oracle_path()
  path.parent.mkdir(parents=True, exist_ok=True)

  sync_count = 0
  protected_count = 0
  begin = time.time()
  last_progress = begin
  cb(seconds=0.0, sync=0, protected=0)

  with path.open("w", encoding="utf-8") as f:
    while time.time() - begin < seconds:
      if should_cancel and should_cancel():
        return {
          "status": "cancelled",
          "sync": sync_count,
          "protected": protected_count,
          "oracle_path": str(path),
          "message": "CAN 采集已取消。",
        }
      frames = panda.can_recv()
      if not frames:
        time.sleep(0.005)
        continue

      ts_ms = (time.time() - begin) * 1000.0
      for addr, *_, data, bus in frames:
        if bus not in ORACLE_BUSES:
          continue
        if addr != SYNC_ADDR and addr not in PROTECTED_ADDRS:
          continue
        f.write(json.dumps({"addr": int(addr), "bus": int(bus),
                            "ts_ms": ts_ms, "data": bytes(data).hex()}) + "\n")
        if addr == SYNC_ADDR:
          sync_count += 1
        else:
          protected_count += 1

      now = time.time()
      if now - last_progress >= 1.0:
        last_progress = now
        cb(seconds=now - begin, sync=sync_count, protected=protected_count)

      # Stop as soon as both targets are met. Sync is the bottleneck (~10/s) while
      # protected floods (~100/s), so this exits with hundreds of protected samples,
      # far above the matcher floor. The seconds cap still bounds a slow/sparse bus.
      if sync_count >= SYNC_TARGET and protected_count >= PROTECTED_TARGET:
        break

  cb(seconds=time.time() - begin, sync=sync_count, protected=protected_count)

  if sync_count >= SYNC_TARGET and protected_count >= PROTECTED_TARGET:
    return {
      "status": "complete",
      "sync": sync_count,
      "protected": protected_count,
      "oracle_path": str(path),
      "message": f"已采集 {sync_count} 条 sync 与 {protected_count} 条 protected 帧。",
    }
  return {
    "status": "insufficient",
    "sync": sync_count,
    "protected": protected_count,
    "oracle_path": str(path),
    "message": (f"仅采集到 {sync_count}/{SYNC_TARGET} 条 sync 与 {protected_count}/{PROTECTED_TARGET} "
                "条 protected 帧。请将车辆置于 READY 模式（混动已启动）后重新采集。"),
  }
