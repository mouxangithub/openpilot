"""Sidecar subprocess — isolated event loop for tool activity (WorkBuddy s06)."""

from __future__ import annotations

import json
import multiprocessing as mp
import time
from pathlib import Path
from typing import Any

from ai.system.paths import workspace_path

_WORKER: mp.Process | None = None
_EVENT_QUEUE: mp.Queue | None = None
_STARTED = False
_LOG_PATH: Path | None = None


def _sidecar_log_path() -> Path:
  global _LOG_PATH
  if _LOG_PATH is None:
    _LOG_PATH = workspace_path("sidecar_events.jsonl", mkdir=True)
  return _LOG_PATH


def _worker_main(event_queue: mp.Queue) -> None:
  path = _sidecar_log_path()
  while True:
    try:
      item = event_queue.get(timeout=5.0)
    except Exception:
      continue
    if item is None:
      break
    if not isinstance(item, dict):
      continue
    try:
      entry = {**item, "worker_ts": int(time.time() * 1000)}
      with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except OSError:
      pass


def start_sidecar_process() -> bool:
  """Spawn sidecar worker if not running. Returns True if started or already up."""
  global _WORKER, _EVENT_QUEUE, _STARTED
  if _STARTED and _WORKER and _WORKER.is_alive():
    return True
  try:
    ctx = mp.get_context("spawn")
    _EVENT_QUEUE = ctx.Queue(maxsize=500)
    _WORKER = ctx.Process(
      target=_worker_main,
      args=(_EVENT_QUEUE,),
      name="op-sidecar",
      daemon=True,
    )
    _WORKER.start()
    _STARTED = True
    return True
  except Exception:
    _STARTED = False
    return False


def stop_sidecar_process() -> None:
  global _WORKER, _EVENT_QUEUE, _STARTED
  if _EVENT_QUEUE is not None:
    try:
      _EVENT_QUEUE.put_nowait(None)
    except Exception:
      pass
  if _WORKER is not None:
    try:
      _WORKER.join(timeout=2.0)
      if _WORKER.is_alive():
        _WORKER.terminate()
    except Exception:
      pass
  _WORKER = None
  _EVENT_QUEUE = None
  _STARTED = False


def enqueue_sidecar_event(event: dict[str, Any]) -> bool:
  """Push event to sidecar subprocess queue. Falls back silently if unavailable."""
  if not _STARTED or _EVENT_QUEUE is None:
    if not start_sidecar_process():
      return False
  try:
    _EVENT_QUEUE.put_nowait(event)
    return True
  except Exception:
    return False


def sidecar_status() -> dict[str, Any]:
  alive = bool(_WORKER and _WORKER.is_alive())
  return {
    "ok": True,
    "running": alive,
    "pid": _WORKER.pid if alive and _WORKER else None,
    "logPath": str(_sidecar_log_path()),
    "isolated": alive,
  }
