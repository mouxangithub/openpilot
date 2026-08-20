"""Consumer-facing API handlers for OP Agent."""

from __future__ import annotations

from aiohttp import web

from ai.tools.consumer_tools import (
  consumer_bootstrap_payload,
  enrich_write_preview,
  preview_params_consumer,
  start_wizard_payload,
)
from ai.tools.consumer_wizards import list_consumer_wizards


async def api_consumer_wizards(_request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  return json_response({"ok": True, **consumer_bootstrap_payload()})


async def api_consumer_wizard_start(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  wizard_id = request.match_info.get("wizard_id", "")
  return json_response(start_wizard_payload(wizard_id))


async def api_consumer_lexicon(_request: web.Request) -> web.Response:
  from ai.common.consumer_lexicon import lexicon_snapshot
  from ai.server.deps import json_response
  limit = int(_request.query.get("limit", "80") or "80")
  return json_response(lexicon_snapshot(limit=min(limit, 200)))


async def api_consumer_preview_params(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  try:
    body = await request.json()
  except Exception:
    body = {}
  if not isinstance(body, dict):
    body = {}
  proposed = body.get("params") or body
  preview = body.get("preview")
  if preview and isinstance(preview, dict):
    return json_response(enrich_write_preview(preview))
  return json_response(preview_params_consumer(proposed if isinstance(proposed, dict) else {}))
