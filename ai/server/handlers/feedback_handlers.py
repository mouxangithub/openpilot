"""API handlers for chat message feedback."""

from __future__ import annotations

import json

from aiohttp import web
from openpilot.common.swaglog import cloudlog

from ai.server.handlers._api_common import *  # noqa: F403
from ai.tools.feedback_store import clear_feedback, list_feedback, record_feedback


async def api_feedback(request: web.Request) -> web.Response:
  if request.method == "GET":
    try:
      limit = int(request.query.get("limit", "50"))
    except (TypeError, ValueError):
      limit = 50
    return _json_response(list_feedback(_PARAMS, limit=limit))

  try:
    body = await request.json()
  except json.JSONDecodeError:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)

  if not isinstance(body, dict):
    return _json_response({"ok": False, "error": "Invalid body"}, status=400)

  rating = body.get("rating")
  if rating is None or rating == "":
    result = clear_feedback(
      _PARAMS,
      session_id=str(body.get("sessionId") or body.get("session_id") or ""),
      message_index=body.get("messageIndex", body.get("message_index")),
    )
    if result.get("ok"):
      cloudlog.info(
        f"aid: feedback cleared session={body.get('sessionId')} idx={body.get('messageIndex')}"
      )
    return _json_response(result, status=200 if result.get("ok") else 400)

  result = record_feedback(_PARAMS, body)
  if result.get("ok"):
    cloudlog.info(
      f"aid: feedback {body.get('rating')} session={body.get('sessionId')} "
      f"idx={body.get('messageIndex')} reason={body.get('reason') or '-'}"
    )
  return _json_response(result, status=200 if result.get("ok") else 400)
