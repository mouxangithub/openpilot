"""Optional Web session sync to device Params."""

from __future__ import annotations

import json
import time
from typing import Any

from openpilot.common.params import Params

SESSIONS_KEY = "ai_web_sessions"
MAX_SESSIONS = 30
MAX_MESSAGES_PER_SESSION = 100


def _load(params: Params) -> dict[str, Any]:
  try:
    raw = params.get(SESSIONS_KEY)
    if not raw:
      return {"sessions": [], "activeId": None}
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="replace")
    data = json.loads(raw)
    if not isinstance(data, dict):
      return {"sessions": [], "activeId": None}
    return data
  except Exception:
    return {"sessions": [], "activeId": None}


def _session_has_content(session: dict[str, Any]) -> bool:
  for msg in session.get("messages") or []:
    if not isinstance(msg, dict):
      continue
    role = msg.get("role")
    content = msg.get("content")
    if role == "user":
      if isinstance(content, str) and content.strip():
        return True
      if isinstance(content, list):
        for part in content:
          if isinstance(part, dict) and part.get("type") in ("text", "image_url"):
            if part.get("type") == "text" and str(part.get("text", "")).strip():
              return True
            if part.get("type") == "image_url":
              return True
    if role == "assistant":
      if isinstance(content, str) and content.strip():
        return True
      if msg.get("tool_calls"):
        return True
      if str(msg.get("reasoning_content") or "").strip():
        return True
  return False


def get_sessions(params: Params | None = None) -> dict[str, Any]:
  params = params or Params()
  data = _load(params)
  sessions = [s for s in (data.get("sessions") or []) if _session_has_content(s)]
  active_id = data.get("activeId")
  if active_id and not any(s.get("id") == active_id for s in sessions):
    active_id = sessions[0].get("id") if sessions else None
  data["sessions"] = sessions
  data["activeId"] = active_id
  if "savedAt" not in data:
    data["savedAt"] = 0
  data["ok"] = True
  return data


def save_sessions(params: Params, payload: dict[str, Any]) -> dict[str, Any]:
  sessions = payload.get("sessions") or []
  if not isinstance(sessions, list):
    return {"ok": False, "error": "sessions must be a list"}
  trimmed = []
  for s in sessions[:MAX_SESSIONS]:
    msgs = (s.get("messages") or [])[-MAX_MESSAGES_PER_SESSION:]
    if not msgs:
      continue
    updated_at = s.get("updatedAt")
    try:
      updated_at = int(updated_at) if updated_at is not None else int(time.time())
    except (TypeError, ValueError):
      updated_at = int(time.time())
    entry = {**s, "messages": msgs, "updatedAt": updated_at}
    if not _session_has_content(entry):
      continue
    trimmed.append(entry)
  trimmed.sort(key=lambda x: x.get("updatedAt") or 0, reverse=True)
  active_id = payload.get("activeId")
  if active_id and not any(s.get("id") == active_id for s in trimmed):
    active_id = trimmed[0].get("id") if trimmed else None
  data = {
    "sessions": trimmed,
    "activeId": active_id,
    "savedAt": int(time.time()),
  }
  params.put(SESSIONS_KEY, json.dumps(data, ensure_ascii=False))
  return {"ok": True, "count": len(trimmed), "activeId": active_id, "savedAt": data["savedAt"]}
