"""Web terminal OP chat — SSE stream (same engine as ``op chat``)."""

from __future__ import annotations

import json
from typing import Any

from aiohttp import web

from openpilot.common.swaglog import cloudlog

from ai.agents.orchestrator import run_chat_with_agents
from ai.core.chat.runner import ChatCancelled
from ai.server.deps import get_state_reader, get_tool_handlers, json_response, params, read_ai_config, sse
from ai.server.handlers.chat_handlers import _parse_chat_body, _prepare_chat_run


_PARAMS = params()


async def api_terminal_op(request: web.Request) -> web.Response:
  """POST JSON {messages, workflow?, consumerMode?, sessionId?} → SSE (op chat)."""
  try:
    body, config, err = await _parse_chat_body(request)
    if err is not None:
      return err
    assert body is not None and config is not None

    body.setdefault("source", "terminal-op")
    body.setdefault("tools", True)
    prep = _prepare_chat_run(body)
    run_body = {**body, "_config": config, "_agent_route": prep["route"]}
    if prep.get("orchestration_plan"):
      run_body["_orchestration_plan"] = prep["orchestration_plan"]

    async def stream_response() -> web.StreamResponse:
      response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
          "Content-Type": "text/event-stream; charset=utf-8",
          "Cache-Control": "no-cache",
          "X-OP-Agent": "terminal-op",
        },
      )
      await response.prepare(request)

      async def emit(event: dict[str, Any]) -> None:
        if event.get("type") == "tool_result":
          result = event.get("result") or {}
          if result.get("needs_confirmation") and result.get("pending_id"):
            try:
              from ai.tools.consumer_tools import enrich_write_preview
              preview = result.get("preview") or {}
              enriched = enrich_write_preview(preview)
              if enriched.get("consumer"):
                result = {**result, "consumer_preview": enriched["consumer"]}
                event = {**event, "result": result}
            except Exception:
              pass
        await response.write(sse(event))

      try:
        await run_chat_with_agents(
          run_body,
          _PARAMS,
          emit,
          get_state_reader=get_state_reader,
          get_tool_handlers=get_tool_handlers,
          tools=prep["tools"],
          max_tool_rounds=prep["max_tool_rounds"],
        )
      except ChatCancelled:
        await response.write(sse({"type": "done", "ok": False, "cancelled": True}))
      except Exception as e:
        cloudlog.error(f"aid: terminal op stream error: {e}")
        await response.write(sse({"type": "error", "error": str(e)}))
      await response.write_eof()
      return response

    return await stream_response()
  except Exception as e:
    cloudlog.error(f"aid: api_terminal_op error: {e}")
    return json_response({"ok": False, "error": str(e)}, status=500)


async def api_terminal_op_confirm(request: web.Request) -> web.Response:
  """Confirm pending write from terminal (after user types y)."""
  try:
    body = await request.json()
  except json.JSONDecodeError:
    body = {}
  if not isinstance(body, dict):
    body = {}
  pending_id = str(body.get("pending_id") or body.get("pendingId") or "").strip()
  if not pending_id:
    return json_response({"ok": False, "error": "pending_id required"}, status=400)
  from ai.tools.write_pending import confirm_pending
  result = confirm_pending(_PARAMS, pending_id)
  return json_response(result, status=200 if result.get("ok") else 400)
