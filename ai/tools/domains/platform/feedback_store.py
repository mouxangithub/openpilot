"""Persist chat message feedback (thumbs up/down + dislike reasons)."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from openpilot.common.params import Params

from ai.common.storage import read_param, write_param

FEEDBACK_KEY = "ai_message_feedback"
MAX_ENTRIES = 500
MAX_PREVIEW_CHARS = 400
MAX_COMMENT_CHARS = 500

VALID_RATINGS = frozenset({"up", "down"})
VALID_REASONS = frozenset({
  "misunderstanding",
  "context",
  "unclear",
  "code_error",
  "unprofessional",
  "code_format",
  "other",
})


def _empty_store() -> dict[str, Any]:
  return {
    "entries": [],
    "summary": {"up": 0, "down": 0, "by_reason": {}},
    "updatedAt": 0,
  }


def _clip(text: Any, limit: int = MAX_PREVIEW_CHARS) -> str:
  raw = str(text or "").strip()
  if len(raw) <= limit:
    return raw
  return f"{raw[: limit - 1]}…"


def _entry_key(session_id: str, message_index: int) -> str:
  return f"{session_id}::{message_index}"


def _rebuild_summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
  summary = {"up": 0, "down": 0, "by_reason": {}}
  for entry in entries:
    rating = entry.get("rating")
    if rating == "up":
      summary["up"] += 1
    elif rating == "down":
      summary["down"] += 1
      reason = str(entry.get("reason") or "").strip()
      if reason:
        by_reason = summary["by_reason"]
        by_reason[reason] = int(by_reason.get(reason, 0) or 0) + 1
  return summary


def load_feedback_store(params: Params) -> dict[str, Any]:
  try:
    raw = read_param(params, FEEDBACK_KEY)
    if not raw:
      return _empty_store()
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="replace")
    data = json.loads(raw)
    if not isinstance(data, dict):
      return _empty_store()
    entries = [e for e in (data.get("entries") or []) if isinstance(e, dict)]
    return {
      "entries": entries[-MAX_ENTRIES:],
      "summary": _rebuild_summary(entries),
      "updatedAt": int(data.get("updatedAt") or 0),
    }
  except Exception:
    return _empty_store()


def _save_store(params: Params, store: dict[str, Any]) -> None:
  store["summary"] = _rebuild_summary(store.get("entries") or [])
  store["updatedAt"] = int(time.time())
  write_param(params, FEEDBACK_KEY, json.dumps(store, ensure_ascii=False))


def list_feedback(params: Params, *, limit: int = 50) -> dict[str, Any]:
  store = load_feedback_store(params)
  limit = max(1, min(int(limit or 50), 200))
  entries = list(reversed(store.get("entries") or []))[:limit]
  return {
    "ok": True,
    "summary": store.get("summary") or _empty_store()["summary"],
    "entries": entries,
    "updatedAt": store.get("updatedAt") or 0,
  }


def clear_feedback(params: Params, *, session_id: str, message_index: int) -> dict[str, Any]:
  session_id = str(session_id or "").strip()
  if not session_id:
    return {"ok": False, "error": "session_id required"}
  try:
    message_index = int(message_index)
  except (TypeError, ValueError):
    return {"ok": False, "error": "message_index invalid"}

  store = load_feedback_store(params)
  key = _entry_key(session_id, message_index)
  entries = [e for e in store.get("entries") or [] if _entry_key(str(e.get("session_id") or ""), int(e.get("message_index") or -1)) != key]
  store["entries"] = entries[-MAX_ENTRIES:]
  _save_store(params, store)
  return {"ok": True, "cleared": True, "summary": store["summary"]}


def record_feedback(params: Params, payload: dict[str, Any]) -> dict[str, Any]:
  session_id = str(payload.get("session_id") or payload.get("sessionId") or "").strip()
  if not session_id:
    return {"ok": False, "error": "session_id required"}

  try:
    message_index = int(payload.get("message_index", payload.get("messageIndex")))
  except (TypeError, ValueError):
    return {"ok": False, "error": "message_index invalid"}

  rating = str(payload.get("rating") or "").strip().lower()
  if rating not in VALID_RATINGS:
    return {"ok": False, "error": "rating must be up or down"}

  reason = str(payload.get("reason") or "").strip().lower()
  comment = _clip(payload.get("comment"), MAX_COMMENT_CHARS)
  if rating == "down":
    if reason not in VALID_REASONS:
      return {"ok": False, "error": "reason required for negative feedback"}
    if reason == "other" and not comment:
      return {"ok": False, "error": "comment required when reason is other"}

  entry = {
    "id": str(payload.get("id") or f"fb_{uuid.uuid4().hex[:12]}"),
    "session_id": session_id,
    "message_index": message_index,
    "rating": rating,
    "reason": reason if rating == "down" else None,
    "comment": comment if rating == "down" and comment else None,
    "resolved_model": _clip(payload.get("resolved_model") or payload.get("resolvedModel"), 120),
    "message_preview": _clip(payload.get("message_preview") or payload.get("messagePreview")),
    "user_preview": _clip(payload.get("user_preview") or payload.get("userPreview")),
    "created_at": int(time.time()),
  }

  store = load_feedback_store(params)
  key = _entry_key(session_id, message_index)
  entries = [e for e in store.get("entries") or [] if _entry_key(str(e.get("session_id") or ""), int(e.get("message_index") or -1)) != key]
  entries.append(entry)
  store["entries"] = entries[-MAX_ENTRIES:]
  _save_store(params, store)
  return {"ok": True, "entry": entry, "summary": store["summary"]}
