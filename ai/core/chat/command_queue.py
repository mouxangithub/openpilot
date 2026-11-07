"""Driving command queue — steer / followup / collect modes."""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, Awaitable, Callable

StartFn = Callable[[dict[str, Any]], Awaitable[str]]

_queues: dict[str, deque[dict[str, Any]]] = {}
_collect_buffers: dict[str, list[dict[str, Any]]] = {}
_locks: dict[str, asyncio.Lock] = {}
_modes: dict[str, str] = {}


def _key(session_id: str) -> str:
  return session_id or "__global__"


def _queue(session_id: str) -> deque[dict[str, Any]]:
  key = _key(session_id)
  if key not in _queues:
    _queues[key] = deque()
  return _queues[key]


def queue_depth(session_id: str) -> int:
  key = _key(session_id)
  mode = _modes.get(key, "followup")
  if mode == "collect":
    return len(_collect_buffers.get(key, []))
  return len(_queue(session_id))


def get_queue_mode(session_id: str) -> str:
  return _modes.get(_key(session_id), "steer")


def _has_running_job(session_id: str) -> bool:
  try:
    from ai.core.chat.jobs import list_active_jobs
    for j in list_active_jobs(session_id or None):
      if not session_id or j.get("sessionId") == session_id:
        return True
  except Exception:
    pass
  return False


def _merge_user_messages(bodies: list[dict[str, Any]]) -> dict[str, Any]:
  """Merge multiple queued bodies into one collect batch."""
  if not bodies:
    return {}
  if len(bodies) == 1:
    return bodies[0]
  base = {**bodies[-1]}
  merged_msgs: list[dict[str, Any]] = []
  for b in bodies:
    for m in b.get("messages") or []:
      if isinstance(m, dict):
        merged_msgs.append(m)
  base["messages"] = merged_msgs
  base["_collect_batch"] = len(bodies)
  return base


async def submit_chat_request(
  session_id: str,
  body: dict[str, Any],
  *,
  driving: bool,
  queue_mode: str,
  start_fn: StartFn,
  cancel_session_fn: Callable[[str], Awaitable[int]] | None = None,
) -> dict[str, Any]:
  """
  steer: cancel running job and start immediately.
  followup: FIFO queue, one job at a time.
  collect: batch messages while busy; drain merges into one user turn.
  """
  mode = (queue_mode or "steer").lower()
  if mode not in ("steer", "followup", "collect"):
    mode = "steer"
  key = _key(session_id)
  _modes[key] = mode

  if not driving:
    job_id = await start_fn(body)
    return {"action": "started", "jobId": job_id, "queueMode": mode, "queued": False}

  if mode == "steer":
    if cancel_session_fn:
      await cancel_session_fn(session_id)
    _collect_buffers.pop(key, None)
    _queue(session_id).clear()
    job_id = await start_fn(body)
    return {"action": "steered", "jobId": job_id, "queueMode": mode, "queued": False}

  if mode == "collect":
    buf = _collect_buffers.setdefault(key, [])
    buf.append(body)
    if _has_running_job(session_id):
      return {
        "action": "collected",
        "jobId": None,
        "queueMode": mode,
        "queued": True,
        "queuePosition": len(buf),
        "collectBatch": len(buf),
      }
    merged = _merge_user_messages(buf)
    count = len(buf)
    _collect_buffers[key] = []
    job_id = await start_fn(merged)
    return {"action": "started", "jobId": job_id, "queueMode": mode, "queued": False, "collectBatch": count}

  q = _queue(session_id)
  q.append(body)
  return {
    "action": "queued",
    "jobId": None,
    "queueMode": mode,
    "queued": True,
    "queuePosition": len(q),
  }


async def drain_session_queue(
  session_id: str,
  start_fn: StartFn,
) -> str | None:
  """Start next queued/collected request if any."""
  key = _key(session_id)
  lock = _locks.setdefault(key, asyncio.Lock())
  async with lock:
    mode = _modes.get(key, "followup")
    if mode == "collect":
      buf = _collect_buffers.get(key, [])
      if not buf:
        return None
      merged = _merge_user_messages(buf)
      _collect_buffers[key] = []
      return await start_fn(merged)
    q = _queue(session_id)
    if not q:
      return None
    body = q.popleft()
    return await start_fn(body)


def list_queued(session_id: str | None = None) -> list[dict[str, Any]]:
  out: list[dict[str, Any]] = []
  keys = {_key(session_id)} if session_id else set(_queues) | set(_collect_buffers)
  for sid in keys:
    mode = _modes.get(sid, "followup")
    if mode == "collect":
      depth = len(_collect_buffers.get(sid, []))
    else:
      depth = len(_queues.get(sid, deque()))
    if not depth:
      continue
    out.append({
      "sessionId": "" if sid == "__global__" else sid,
      "depth": depth,
      "mode": mode,
    })
  return out
