"""API handlers — sessions."""

from ai.server.handlers._api_common import *  # noqa: F403

async def api_sessions(request: web.Request) -> web.Response:
  if request.method == "GET":
    session_id = (request.query.get("session_id") or request.query.get("session") or "").strip()
    compact = request.query.get("compact", "1") in ("1", "true", "yes")
    loop = asyncio.get_running_loop()
    from ai.server.thread_pools import io_executor
    from ai.tools.session_store import get_session_by_id, get_sessions

    pool = io_executor()
    if session_id:
      result = await loop.run_in_executor(pool, lambda: get_session_by_id(_PARAMS, session_id))
      return _json_response(result)
    result = await loop.run_in_executor(pool, lambda: get_sessions(_PARAMS, compact=compact))
    return _json_response(result)
  try:
    body = await request.json()
  except json.JSONDecodeError:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  result = save_sessions(_PARAMS, body)
  try:
    await broadcast_sessions(_PARAMS)
  except Exception as e:
    cloudlog.warning(f"aid: broadcast_sessions failed: {e}")
  return _json_response(result)

async def api_pc_sessions(request: web.Request) -> web.Response:
  try:
    from ai.tools.pc_dev_tools import pc_list_tool_sessions
    return _json_response(pc_list_tool_sessions(limit=int(request.query.get("limit", "20"))))
  except Exception as e:
    return _json_response({"ok": False, "error": str(e)})
