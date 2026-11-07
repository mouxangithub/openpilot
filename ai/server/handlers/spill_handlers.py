"""API handlers — spill long-context management."""

from __future__ import annotations

from typing import Any

from ai.server.handlers._api_common import *  # noqa: F403


async def api_spill(request: web.Request) -> web.Response:
  """GET: global spill stats. POST: run spill on a message list."""
  manager: Any = request.app["spill_manager"]

  if request.method == "GET":
    return _json_response({
      "ok": True,
      "summaryCount": len(manager.summaries),
      "config": {
        "maxInlineTokens": manager.max_inline_tokens,
        "reserveTokens": manager.reserve_tokens,
        "keepRecentTurns": manager.keep_recent_turns,
        "maxTurnsBeforeSpill": manager.max_turns_before_spill,
      },
    })

  try:
    body = await request.json()
  except json.JSONDecodeError:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)

  messages = body.get("messages") or []
  session_id = str(body.get("sessionId") or body.get("session_id") or "").strip()
  force = bool(body.get("force"))
  action = str(body.get("action") or "spill").strip().lower()

  if action == "status":
    return _json_response({"ok": True, "status": manager.status(messages)})

  try:
    compacted = await manager.spill(messages, session_id=session_id, force=force)
  except Exception as e:
    cloudlog.error(f"aid: spill failed: {e}")
    return _json_response({"ok": False, "error": str(e)}, status=500)

  return _json_response({
    "ok": True,
    "messages": compacted,
    "status": manager.status(compacted),
  })


async def api_spill_recall(request: web.Request) -> web.Response:
  """Recall one spilled summary by locator."""
  locator = request.query.get("locator", "")
  if not locator:
    return _json_response({"ok": False, "error": "locator is required"}, status=400)
  manager: Any = request.app["spill_manager"]
  try:
    text = await manager.store.get_text(locator)
  except Exception as e:
    return _json_response({"ok": False, "error": str(e)}, status=500)
  if text is None:
    return _json_response({"ok": False, "error": "summary not found"}, status=404)
  return _json_response({"ok": True, "locator": locator, "summary": text})
