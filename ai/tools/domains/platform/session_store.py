"""Optional Web session sync to device Params."""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from openpilot.common.params import Params

from ai.common.storage import read_param, write_param

SESSIONS_KEY = "ai_web_sessions"
MAX_SESSIONS = 50
MAX_MESSAGES_PER_SESSION = 200
_SESSION_WRITE_LOCK = threading.Lock()
_STATE_VERSION = 0
_LOAD_CACHE: tuple[int, dict[str, Any]] | None = None
_RESPONSE_CACHE: tuple[int, bool, dict[str, Any]] | None = None


def _invalidate_load_cache() -> None:
  global _LOAD_CACHE, _RESPONSE_CACHE
  _LOAD_CACHE = None
  _RESPONSE_CACHE = None


def session_state_version() -> int:
  return _STATE_VERSION


def _sync_state_version_from_data(data: dict[str, Any]) -> None:
  global _STATE_VERSION
  persisted = int(data.get("stateVersion") or data.get("savedAt") or 0)
  if persisted > _STATE_VERSION:
    _STATE_VERSION = persisted


def _load(params: Params) -> dict[str, Any]:
  global _LOAD_CACHE
  try:
    raw = read_param(params, SESSIONS_KEY)
    if not raw:
      return {"sessions": [], "activeId": None}
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="replace")
    version_hint = hash(raw) & 0x7FFFFFFF
    if _LOAD_CACHE is not None and _LOAD_CACHE[0] == version_hint:
      return _LOAD_CACHE[1]
    data = json.loads(raw)
    if not isinstance(data, dict):
      return {"sessions": [], "activeId": None}
    _sync_state_version_from_data(data)
    _LOAD_CACHE = (version_hint, data)
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


def _session_quick_has_content(session: dict[str, Any]) -> bool:
  msgs = session.get("messages") or []
  if not msgs:
    return bool(session.get("hasContent")) or int(session.get("messageCount") or 0) > 0
  if len(msgs) <= 2:
    return _session_has_content(session)
  for msg in (msgs[0], msgs[-1], msgs[len(msgs) // 2]):
    if not isinstance(msg, dict):
      continue
    role = msg.get("role")
    if role not in ("user", "assistant"):
      continue
    content = msg.get("content")
    if isinstance(content, str) and content.strip():
      return True
    if role == "assistant" and (msg.get("tool_calls") or str(msg.get("reasoning_content") or "").strip()):
      return True
  return _session_has_content(session)


def _session_created_at(session: dict[str, Any]) -> int:
  created = session.get("createdAt")
  if created is not None:
    try:
      val = int(created)
      if val > 0:
        return val
    except (TypeError, ValueError):
      pass
  sid = str(session.get("id") or "")
  if sid.startswith("s_"):
    parts = sid.split("_", 2)
    if len(parts) >= 2:
      try:
        val = int(parts[1], 36)
        if val > 10**11:
          return val
      except ValueError:
        pass
  try:
    return int(session.get("updatedAt") or 0)
  except (TypeError, ValueError):
    return 0


def _session_compact(session: dict[str, Any]) -> dict[str, Any]:
  msgs = session.get("messages") or []
  return {
    "id": session.get("id"),
    "title": session.get("title"),
    "createdAt": session.get("createdAt") or _session_created_at(session),
    "updatedAt": session.get("updatedAt"),
    "mode": session.get("mode"),
    "messageCount": len(msgs),
    "hasContent": True,
    "messages": [],
  }


def get_session_by_id(params: Params | None, session_id: str) -> dict[str, Any]:
  params = params or Params()
  data = _load(params)
  sid = (session_id or "").strip()
  if not sid:
    return {"ok": False, "error": "session_id required"}
  for session in data.get("sessions") or []:
    if session.get("id") == sid and _session_has_content(session):
      return {"ok": True, "session": session}
  return {"ok": False, "error": "session not found"}


def get_sessions(params: Params | None = None, *, compact: bool = False) -> dict[str, Any]:
  global _RESPONSE_CACHE
  params = params or Params()
  data = _load(params)
  version = int(data.get("stateVersion") or data.get("savedAt") or 0)
  if (
    _RESPONSE_CACHE is not None
    and _RESPONSE_CACHE[0] == version
    and _RESPONSE_CACHE[1] == compact
  ):
    return dict(_RESPONSE_CACHE[2])

  sessions = [s for s in (data.get("sessions") or []) if _session_quick_has_content(s)]
  active_id = data.get("activeId")
  if active_id and not any(s.get("id") == active_id for s in sessions):
    active_id = sessions[0].get("id") if sessions else None
  if compact and sessions:
    compact_sessions: list[dict[str, Any]] = []
    for session in sessions:
      if session.get("id") == active_id:
        compact_sessions.append(session)
      else:
        compact_sessions.append(_session_compact(session))
    sessions = compact_sessions
  data["sessions"] = sessions
  data["activeId"] = active_id
  if "savedAt" not in data:
    data["savedAt"] = 0
  data["stateVersion"] = int(data.get("stateVersion") or _STATE_VERSION or data.get("savedAt") or 0)
  data["ok"] = True
  if compact:
    data["compact"] = True
  _RESPONSE_CACHE = (version, compact, data)
  return dict(data)


def save_sessions(params: Params, payload: dict[str, Any]) -> dict[str, Any]:
  global _STATE_VERSION
  with _SESSION_WRITE_LOCK:
    existing = _load(params)
    _sync_state_version_from_data(existing)
    sessions = payload.get("sessions") or []
    if not isinstance(sessions, list):
      return {"ok": False, "error": "sessions must be a list"}
    trimmed = []
    seen_ids: set[str] = set()
    for s in sessions[:MAX_SESSIONS]:
      sid = str(s.get("id") or "").strip()
      if sid and sid in seen_ids:
        continue
      msgs = (s.get("messages") or [])[-MAX_MESSAGES_PER_SESSION:]
      if not msgs:
        continue
      updated_at = s.get("updatedAt")
      try:
        updated_at = int(updated_at) if updated_at is not None else int(time.time())
      except (TypeError, ValueError):
        updated_at = int(time.time())
      created_at = s.get("createdAt")
      try:
        created_at = int(created_at) if created_at is not None else _session_created_at(s)
      except (TypeError, ValueError):
        created_at = _session_created_at(s)
      entry = {k: v for k, v in {**s, "messages": msgs, "updatedAt": updated_at, "createdAt": created_at}.items() if k != "activeJobId"}
      if not _session_has_content(entry):
        continue
      trimmed.append(entry)
      if sid:
        seen_ids.add(sid)
    trimmed.sort(key=_session_created_at, reverse=True)
    if "activeId" in payload:
      active_id = payload.get("activeId")
    else:
      active_id = existing.get("activeId")
    if active_id and not any(s.get("id") == active_id for s in trimmed):
      active_id = trimmed[0].get("id") if trimmed else None
    data = {
      "sessions": trimmed,
      "activeId": active_id,
      "savedAt": int(time.time()),
    }
    _STATE_VERSION += 1
    data["stateVersion"] = _STATE_VERSION
    _invalidate_load_cache()
    write_param(params, SESSIONS_KEY, json.dumps(data, ensure_ascii=False))
    try:
      from ai.tools.domains.platform.session_index import schedule_index_sessions
      schedule_index_sessions(trimmed)
    except Exception:
      pass
    return {
      "ok": True,
      "count": len(trimmed),
      "activeId": active_id,
      "savedAt": data["savedAt"],
      "stateVersion": data["stateVersion"],
    }
