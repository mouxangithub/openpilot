"""Background chat jobs — survive browser refresh/disconnect."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Callable

from openpilot.common.params import Params

from ai.core.chat.runner import ChatCancelled, run_chat_loop
from ai.agents.orchestrator import run_chat_with_agents

_MAX_JOBS = 20
_JOB_TTL_SEC = 3600
_STUCK_WARN_SEC = 120
_MAX_EVENTS_PER_JOB = 500
_watchdog_task: asyncio.Task | None = None


class JobCancelled(Exception):
  pass


_jobs: dict[str, dict[str, Any]] = {}
_tasks: dict[str, asyncio.Task] = {}
_cancel_flags: dict[str, bool] = {}
_lock = asyncio.Lock()
_session_lanes: dict[str, asyncio.Lock] = {}
_idempotency: dict[str, tuple[str, int]] = {}
_IDEMPOTENCY_TTL_SEC = 120


def _new_job_id() -> str:
  return f"job_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"


def _apply_event_to_assistant(assistant: dict[str, Any], event: dict[str, Any]) -> None:
  et = event.get("type")
  if et == "content":
    assistant["content"] = (assistant.get("content") or "") + (event.get("delta") or "")
  elif et == "reasoning":
    assistant["reasoning_content"] = (assistant.get("reasoning_content") or "") + (event.get("delta") or "")
  elif et == "tool_call":
    tool_calls = assistant.setdefault("tool_calls", [])
    tid = event.get("id", "")
    if not any(tc.get("id") == tid for tc in tool_calls):
      tool_calls.append({
        "id": tid,
        "type": "function",
        "function": {"name": event.get("name", ""), "arguments": event.get("arguments", "")},
      })
  elif et == "tool_result":
    results = assistant.setdefault("tool_results", {})
    results[event.get("id", "")] = event.get("result")
  elif et == "error":
    assistant["content"] = event.get("error") or assistant.get("content") or ""


def _prune_old_jobs() -> None:
  if len(_jobs) <= _MAX_JOBS:
    return
  done = [
    (jid, j.get("updatedAt") or 0)
    for jid, j in _jobs.items()
    if j.get("status") in ("done", "error", "cancelled")
  ]
  done.sort(key=lambda x: x[1])
  for jid, _ in done[: max(0, len(_jobs) - _MAX_JOBS)]:
    if _jobs.get(jid, {}).get("status") == "running":
      continue
    _jobs.pop(jid, None)
    _cancel_flags.pop(jid, None)


async def start_chat_job(
  session_id: str,
  body: dict[str, Any],
  params: Params,
  *,
  get_state_reader: Callable,
  get_tool_handlers: Callable,
  tools: list[dict[str, Any]] | None,
  max_tool_rounds: int,
  config: Any,
) -> str:
  idem = str(body.get("idempotencyKey") or body.get("idempotency_key") or "").strip()
  if idem and session_id:
    cache_key = f"{session_id}:{idem}"
    now = int(time.time())
    async with _lock:
      expired = [k for k, v in _idempotency.items() if v[1] < now]
      for k in expired:
        _idempotency.pop(k, None)
      cached = _idempotency.get(cache_key)
      if cached:
        job_id, expires = cached
        if expires >= now and job_id in _jobs:
          return job_id

  job_id = _new_job_id()
  now = int(time.time())
  job = {
    "id": job_id,
    "sessionId": session_id or "",
    "status": "running",
    "events": [],
    "eventSeq": 0,
    "assistant": {
      "role": "assistant",
      "content": "",
      "reasoning_content": "",
      "tool_calls": [],
      "tool_results": {},
    },
    "createdAt": now,
    "updatedAt": now,
    "error": None,
    "resolvedModel": None,
    "runId": job_id,
    "lastEventAt": now,
    "queueMode": str(body.get("queueMode") or body.get("queue_mode") or ""),
  }
  _cancel_flags[job_id] = False
  async with _lock:
    _jobs[job_id] = job
    _prune_old_jobs()
    if idem and session_id:
      _idempotency[f"{session_id}:{idem}"] = (job_id, int(time.time()) + _IDEMPOTENCY_TTL_SEC)

  async def emit(event: dict[str, Any]) -> None:
    if _cancel_flags.get(job_id):
      raise JobCancelled()
    async with _lock:
      j = _jobs.get(job_id)
      if not j or j["status"] == "cancelled":
        raise JobCancelled()
      j["eventSeq"] += 1
      event = {**event, "_seq": j["eventSeq"]}
      j["events"].append(event)
      if len(j["events"]) > _MAX_EVENTS_PER_JOB:
        j["events"] = j["events"][-_MAX_EVENTS_PER_JOB:]
      j["updatedAt"] = int(time.time())
      j["lastEventAt"] = int(time.time())
      _apply_event_to_assistant(j["assistant"], event)
    try:
      from ai.core.sync.hub import notify_chat_event
      await notify_chat_event(job_id, job.get("sessionId") or "", event, j)
    except Exception:
      pass

  async def _run() -> None:
    lane_key = session_id or "__global__"
    lane = _session_lanes.setdefault(lane_key, asyncio.Lock())
    async with lane:
      run_body = {**body, "_config": config, "_job_id": job_id}
      try:
        await emit({
          "type": "lifecycle",
          "phase": "start",
          "runId": job_id,
          "jobId": job_id,
          "sessionId": session_id or "",
        })
        result = await run_chat_with_agents(
          run_body,
          params,
          emit,
          get_state_reader=get_state_reader,
          get_tool_handlers=get_tool_handlers,
          tools=tools,
          max_tool_rounds=max_tool_rounds,
          is_cancelled=lambda: bool(_cancel_flags.get(job_id)),
        )
        async with _lock:
          j = _jobs.get(job_id)
          if not j or j["status"] == "cancelled":
            return
          if result.get("ok") is False:
            j["status"] = "error"
            j["error"] = str(result.get("error") or "Chat failed")
          else:
            j["status"] = "done"
          j["resolvedModel"] = result.get("resolvedModel")
          j["updatedAt"] = int(time.time())
        try:
          from ai.core.sync.hub import notify_chat_status
          j = _jobs.get(job_id)
          if j:
            await notify_chat_status(job_id, j.get("sessionId") or "", j)
        except Exception:
          pass
      except (JobCancelled, ChatCancelled):
        async with _lock:
          j = _jobs.get(job_id)
          if j and j["status"] != "cancelled":
            j["status"] = "cancelled"
            j["updatedAt"] = int(time.time())
        try:
          from ai.core.sync.hub import notify_chat_status
          j = _jobs.get(job_id)
          if j:
            await notify_chat_status(job_id, j.get("sessionId") or "", j)
        except Exception:
          pass
      except Exception as e:
        try:
          await emit({"type": "error", "error": str(e)})
        except Exception:
          pass
        async with _lock:
          j = _jobs.get(job_id)
          if j:
            j["status"] = "error"
            j["error"] = str(e)
            j["updatedAt"] = int(time.time())
        try:
          from ai.core.sync.hub import notify_chat_status
          j = _jobs.get(job_id)
          if j:
            await notify_chat_status(job_id, j.get("sessionId") or "", j)
        except Exception:
          pass
      finally:
        _tasks.pop(job_id, None)
        try:
          await emit({
            "type": "lifecycle",
            "phase": "end",
            "runId": job_id,
            "jobId": job_id,
            "sessionId": session_id or "",
          })
        except Exception:
          pass
        try:
          from ai.core.chat.command_queue import drain_session_queue

          async def _start_queued(queued_body: dict[str, Any]) -> str:
            prep_tools = tools
            prep_rounds = max_tool_rounds
            return await start_chat_job(
              session_id,
              queued_body,
              params,
              get_state_reader=get_state_reader,
              get_tool_handlers=get_tool_handlers,
              tools=prep_tools,
              max_tool_rounds=prep_rounds,
              config=config,
            )

          await drain_session_queue(session_id, _start_queued)
        except Exception:
          pass

  _tasks[job_id] = asyncio.create_task(_run())
  try:
    from ai.core.sync.hub import notify_chat_status
    j = _jobs.get(job_id)
    if j:
      await notify_chat_status(job_id, session_id or "", j)
  except Exception:
    pass
  return job_id


def get_job(job_id: str, since: int = 0) -> dict[str, Any] | None:
  job = _jobs.get(job_id)
  if not job:
    return None
  now = int(time.time())
  if job["status"] != "running" and (now - (job.get("updatedAt") or now)) > _JOB_TTL_SEC:
    _jobs.pop(job_id, None)
    _cancel_flags.pop(job_id, None)
    return None
  events = [e for e in job["events"] if int(e.get("_seq") or 0) > since]
  return {
    "ok": True,
    "id": job_id,
    "status": job["status"],
    "sessionId": job["sessionId"],
    "events": events,
    "assistant": job["assistant"],
    "error": job.get("error"),
    "resolvedModel": job.get("resolvedModel"),
    "updatedAt": job["updatedAt"],
    "nextSince": job["eventSeq"],
    "runId": job_id,
    "lastEventAt": job.get("lastEventAt"),
  }


async def wait_for_job(job_id: str, timeout_ms: int = 60000) -> dict[str, Any] | None:
  deadline = time.time() + max(0, timeout_ms) / 1000.0
  while time.time() < deadline:
    snap = get_job(job_id)
    if not snap:
      return None
    if snap.get("status") in ("done", "error", "cancelled"):
      return snap
    await asyncio.sleep(0.2)
  return get_job(job_id)


async def cancel_jobs_for_session(session_id: str) -> int:
  cancelled = 0
  for jid, j in list(_jobs.items()):
    if j.get("status") != "running":
      continue
    if session_id and j.get("sessionId") != session_id:
      continue
    if await cancel_job(jid):
      cancelled += 1
  return cancelled


def _scan_stuck_jobs() -> list[dict[str, Any]]:
  now = int(time.time())
  stuck: list[dict[str, Any]] = []
  for jid, j in _jobs.items():
    if j.get("status") != "running":
      continue
    last = int(j.get("lastEventAt") or j.get("updatedAt") or 0)
    if now - last >= _STUCK_WARN_SEC:
      stuck.append({
        "jobId": jid,
        "sessionId": j.get("sessionId") or "",
        "idleSec": now - last,
        "runId": jid,
      })
  return stuck


async def stuck_job_watchdog_loop() -> None:
  from openpilot.common.swaglog import cloudlog
  warned: set[str] = set()
  while True:
    await asyncio.sleep(30)
    for item in _scan_stuck_jobs():
      jid = item["jobId"]
      if jid in warned:
        continue
      warned.add(jid)
      cloudlog.warning(
        f"aid: stuck chat job {jid} session={item['sessionId']} idle={item['idleSec']}s"
      )
      try:
        from ai.core.sync.hub import notify_lifecycle
        await notify_lifecycle(jid, item["sessionId"], "stuck", item)
      except Exception:
        pass
      j = _jobs.get(jid)
      if j and j.get("status") != "running":
        warned.discard(jid)


def ensure_stuck_watchdog() -> None:
  global _watchdog_task
  if _watchdog_task and not _watchdog_task.done():
    return
  _watchdog_task = asyncio.create_task(stuck_job_watchdog_loop())


def list_active_jobs(session_id: str | None = None) -> list[dict[str, Any]]:
  out = []
  for j in _jobs.values():
    if j.get("status") != "running":
      continue
    if session_id and j.get("sessionId") != session_id:
      continue
    out.append({
      "id": j["id"],
      "sessionId": j.get("sessionId") or "",
      "updatedAt": j.get("updatedAt") or 0,
    })
  out.sort(key=lambda x: x["updatedAt"], reverse=True)
  return out


async def cancel_job(job_id: str) -> bool:
  job = _jobs.get(job_id)
  if not job:
    return False
  _cancel_flags[job_id] = True
  task = _tasks.get(job_id)
  if task and not task.done():
    task.cancel()
  async with _lock:
    j = _jobs.get(job_id)
    if j:
      j["status"] = "cancelled"
      j["updatedAt"] = int(time.time())
  try:
    from ai.core.sync.hub import notify_chat_status
    j = _jobs.get(job_id)
    if j:
      await notify_chat_status(job_id, j.get("sessionId") or "", j)
  except Exception:
    pass
  return True
