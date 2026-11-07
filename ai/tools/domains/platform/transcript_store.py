"""Per-session JSONL transcript — WorkBuddy s09 crash recovery."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ai.system.paths import workspace_path

_MAX_EVENTS_PER_SESSION = 2000
_TRANSCRIPT_TYPES = frozenset({
  "user", "content", "reasoning", "tool_call", "tool_result",
  "error", "usage", "canvas", "orchestration_start", "agent_status",
  "prompt_budget", "done",
})


def transcript_dir() -> Path:
  return workspace_path("transcripts", mkdir=True)


def transcript_path(session_id: str) -> Path:
  sid = (session_id or "global").replace("/", "_").replace("\\", "_")[:96]
  return transcript_dir() / f"{sid}.jsonl"


def append_event(
  session_id: str,
  event: dict[str, Any],
  *,
  job_id: str = "",
) -> None:
  """Append one SSE-style event to session transcript (append-only JSONL)."""
  if not session_id:
    return
  etype = str(event.get("type") or "")
  if etype and etype not in _TRANSCRIPT_TYPES:
    return
  entry: dict[str, Any] = {
    "ts": int(time.time() * 1000),
    "type": etype,
    "sessionId": session_id,
    "jobId": job_id or None,
  }
  for key in ("delta", "name", "id", "agentId", "ok", "error", "usage", "budget"):
    if key in event:
      entry[key] = event[key]
  if event.get("artifact"):
    art = event["artifact"]
    entry["artifact"] = {
      "id": art.get("id"),
      "kind": art.get("kind"),
      "title": art.get("title"),
      "sourceTool": art.get("sourceTool"),
    }
  path = transcript_path(session_id)
  try:
    with path.open("a", encoding="utf-8") as f:
      f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    _trim_if_needed(path)
  except OSError:
    pass


def list_events(
  session_id: str,
  *,
  limit: int = 200,
  offset: int = 0,
) -> dict[str, Any]:
  limit = max(1, min(int(limit), 500))
  offset = max(0, int(offset))
  path = transcript_path(session_id)
  if not path.is_file():
    return {"ok": True, "events": [], "count": 0, "path": str(path)}
  lines: list[str] = []
  try:
    with path.open(encoding="utf-8") as f:
      lines = [ln.strip() for ln in f.readlines() if ln.strip()]
  except OSError as e:
    return {"ok": False, "error": str(e)}
  total = len(lines)
  slice_lines = lines[offset: offset + limit] if offset else lines[-limit:]
  events: list[dict[str, Any]] = []
  for line in slice_lines:
    try:
      events.append(json.loads(line))
    except json.JSONDecodeError:
      continue
  return {
    "ok": True,
    "events": events,
    "count": len(events),
    "total": total,
    "path": str(path),
  }


def recover_partial(session_id: str) -> dict[str, Any]:
  """Rebuild partial assistant text + tool calls from transcript after crash."""
  data = list_events(session_id, limit=500)
  if not data.get("ok"):
    return data
  events = data.get("events") or []
  content_parts: list[str] = []
  reasoning_parts: list[str] = []
  tool_calls: list[dict[str, Any]] = []
  last_tools: dict[str, dict[str, Any]] = {}
  for ev in events:
    et = ev.get("type")
    if et == "content" and ev.get("delta"):
      content_parts.append(str(ev["delta"]))
    elif et == "reasoning" and ev.get("delta"):
      reasoning_parts.append(str(ev["delta"]))
    elif et == "tool_call":
      tid = str(ev.get("id") or "")
      last_tools[tid] = {
        "id": tid,
        "name": ev.get("name", ""),
        "arguments": ev.get("arguments", ""),
        "agentId": ev.get("agentId"),
      }
    elif et == "tool_result":
      tid = str(ev.get("id") or "")
      if tid in last_tools:
        last_tools[tid]["result"] = ev.get("result")
        tool_calls.append(last_tools.pop(tid))
  return {
    "ok": True,
    "sessionId": session_id,
    "content": "".join(content_parts),
    "reasoning": "".join(reasoning_parts),
    "toolCalls": tool_calls,
    "eventCount": len(events),
    "recoverable": bool(content_parts or tool_calls or reasoning_parts),
  }


def _trim_if_needed(path: Path) -> None:
  try:
    with path.open(encoding="utf-8") as f:
      lines = f.readlines()
    if len(lines) <= _MAX_EVENTS_PER_SESSION:
      return
    trimmed = lines[-_MAX_EVENTS_PER_SESSION:]
    with path.open("w", encoding="utf-8") as f:
      f.writelines(trimmed)
  except OSError:
    pass
