"""Background chat jobs — survive browser refresh/disconnect."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Callable

from openpilot.common.params import Params

from ai.chat_runner import ChatCancelled, run_chat_loop

_MAX_JOBS = 20
_JOB_TTL_SEC = 3600


class JobCancelled(Exception):
  pass


_jobs: dict[str, dict[str, Any]] = {}
_tasks: dict[str, asyncio.Task] = {}
_cancel_flags: dict[str, bool] = {}
_lock = asyncio.Lock()


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
  }
  _cancel_flags[job_id] = False
  async with _lock:
    _jobs[job_id] = job
    _prune_old_jobs()

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
      j["updatedAt"] = int(time.time())
      _apply_event_to_assistant(j["assistant"], event)
    try:
      from ai.sync_hub import notify_chat_event
      await notify_chat_event(job_id, job.get("sessionId") or "", event, j)
    except Exception:
      pass

  async def _run() -> None:
    run_body = {**body, "_config": config}
    try:
      result = await run_chat_loop(
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
        j["status"] = "done"
        j["resolvedModel"] = result.get("resolvedModel")
        j["updatedAt"] = int(time.time())
      try:
        from ai.sync_hub import notify_chat_status
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
        from ai.sync_hub import notify_chat_status
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
        from ai.sync_hub import notify_chat_status
        j = _jobs.get(job_id)
        if j:
          await notify_chat_status(job_id, j.get("sessionId") or "", j)
      except Exception:
        pass
    finally:
      _tasks.pop(job_id, None)

  _tasks[job_id] = asyncio.create_task(_run())
  try:
    from ai.sync_hub import notify_chat_status
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
  }


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
    from ai.sync_hub import notify_chat_status
    j = _jobs.get(job_id)
    if j:
      await notify_chat_status(job_id, j.get("sessionId") or "", j)
  except Exception:
    pass
  return True
