"""API handlers — sessions."""

from ai.server.handlers._api_common import *  # noqa: F403
from ai.server.handlers.chat_handlers import _session_log_path

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


async def api_session_log(request: web.Request) -> web.Response:
  """GET /api/ai/sessions/{session_id}/log - return durable session event log."""
  session_id = request.match_info.get("session_id", "").strip()
  if not session_id:
    return _json_response({"ok": False, "error": "session_id required"}, status=400)
  log_path = _session_log_path(session_id)
  events: list[dict[str, Any]] = []
  if log_path and os.path.isfile(log_path):
    try:
      with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
          line = line.strip()
          if not line:
            continue
          try:
            events.append(json.loads(line))
          except json.JSONDecodeError:
            continue
    except Exception as e:
      return _json_response({"ok": False, "error": f"Failed to read log: {e}"}, status=500)
  return _json_response({"ok": True, "sessionId": session_id, "events": events})


async def api_session_repair(request: web.Request) -> web.Response:
  """POST /api/ai/sessions/{id}/repair - deterministic repair of a corrupt log tail."""
  session_id = request.match_info.get("session_id", "").strip()
  if not session_id:
    return _json_response({"ok": False, "error": "session_id required"}, status=400)
  log_path = _session_log_path(session_id)
  if not log_path or not os.path.isfile(log_path):
    return _json_response({"ok": False, "error": "no persisted log for session"}, status=404)
  try:
    from ai.core.session.log import SessionLog
    from ai.core.session.repair import repair_session_log
    log = SessionLog(session_id, persist_path=log_path, load_persisted=True)
    repaired = repair_session_log(log)
    log.close()
    return _json_response({"ok": True, "sessionId": session_id, "repaired": [event.to_dict() for event in repaired]})
  except Exception as e:
    return _json_response({"ok": False, "error": str(e)}, status=500)


def reconstruct_domain_state(events: list[Any]) -> dict[str, Any]:
  """Fold-first reconstruction of goal/plan/todo from session events.

  Prefers ``<domain>/change`` events produced by the G2 projection
  (store mutations → SessionLog.append_domain_event, replayed via
  folds.fold_domain_events). Legacy logs without domain events fall
  back to the TOOL_CALL/TOOL_RESULT heuristic: the tool name lives on
  TOOL_CALL while the result payload lives on TOOL_RESULT, correlated
  by call id.
  """
  try:
    from ai.core.session.folds import fold_domain_events
    folded = fold_domain_events(events)
  except Exception:
    folded = {"goal": None, "plan": None, "todo": None}
  if any(folded.get(k) is not None for k in ("goal", "plan", "todo")):
    return folded

  from ai.core.session.log import EventType
  name_by_call: dict[str, str] = {}
  result_by_call: dict[str, dict] = {}
  for ev in events:
    data = ev.data if isinstance(ev.data, dict) else {}
    if ev.type == EventType.TOOL_CALL:
      cid = str(data.get("callId") or "")
      if cid:
        name_by_call[cid] = str(data.get("name") or "")
    elif ev.type == EventType.TOOL_RESULT:
      cid = str(data.get("tool_call_id") or "")
      if cid:
        try:
          payload = json.loads(data.get("content", "{}")) if isinstance(data.get("content"), str) else data.get("result")
        except (json.JSONDecodeError, TypeError):
          payload = None
        if isinstance(payload, dict):
          result_by_call[cid] = payload
  reconstructed = {"goal": None, "plan": None, "todo": None}
  for cid, name in name_by_call.items():
    payload = result_by_call.get(cid)
    if payload is None:
      continue
    if name.startswith("goal_") and payload.get("goal") is not None:
      reconstructed["goal"] = payload["goal"]
    elif name.startswith("plan_") and payload.get("plan") is not None:
      reconstructed["plan"] = payload["plan"]
    elif name.startswith("todo_") and isinstance(payload, dict):
      reconstructed["todo"] = payload
  return reconstructed


async def api_session_resume(request: web.Request) -> web.Response:
  """POST /api/ai/sessions/{id}/resume - replay persisted events to rebuild context."""
  session_id = request.match_info.get("session_id", "").strip()
  if not session_id:
    return _json_response({"ok": False, "error": "session_id required"}, status=400)
  log_path = _session_log_path(session_id)
  if not log_path or not os.path.isfile(log_path):
    return _json_response({"ok": False, "error": "no persisted log for session"}, status=404)
  try:
    from ai.core.session.log import SessionLog
    log = SessionLog(session_id, persist_path=log_path, load_persisted=True)
    replayed = len(log.events)
    interrupted = []
    call_ids: set[str] = set()
    result_ids: set[str] = set()
    for ev in log.events:
      data = ev.data if isinstance(ev.data, dict) else {}
      if ev.type.value == "tool/call":
        cid = str(data.get("callId") or "")
        if cid:
          call_ids.add(cid)
      elif ev.type.value == "tool/result":
        cid = str(data.get("tool_call_id") or "")
        if cid:
          result_ids.add(cid)
    reconstructed = reconstruct_domain_state(log.events)
    interrupted = sorted(call_ids - result_ids)
    from ai.core.session.repair import repair_session_log
    repaired_events = repair_session_log(log)
    log.close()
    return _json_response({
      "ok": True,
      "sessionId": session_id,
      "replayedEvents": replayed,
      "reconstructed": reconstructed,
      "interrupted": interrupted,
      "repaired": [event.to_dict() for event in repaired_events],
    })
  except Exception as e:
    return _json_response({"ok": False, "error": str(e)}, status=500)


async def api_session_fork(request: web.Request) -> web.Response:
  """POST /api/ai/sessions/{id}/fork - branch a persisted transcript at a point.

  Body:
    - up_to_seq (int): fork up to this event sequence (inclusive by default).
    - inclusive (bool): whether to include the event at up_to_seq.
    - count (int): alternative to up_to_seq; take the first ``count`` events.

  Returns the forked prefix as ``events`` (list of event dicts).
  """
  session_id = request.match_info.get("session_id", "").strip()
  if not session_id:
    return _json_response({"ok": False, "error": "session_id required"}, status=400)
  log_path = _session_log_path(session_id)
  if not log_path or not os.path.isfile(log_path):
    return _json_response({"ok": False, "error": "no persisted log for session"}, status=404)
  try:
    body = await request.json()
  except json.JSONDecodeError:
    body = {}
  if not isinstance(body, dict):
    body = {}
  try:
    from ai.core.session.replay import events_to_dicts, fork_transcript, fork_transcript_by_index
    count = body.get("count")
    if count is not None:
      try:
        events = fork_transcript_by_index(log_path, int(count))
      except Exception as e:
        return _json_response({"ok": False, "error": f"fork by index failed: {e}"}, status=400)
    else:
      up_to_seq = body.get("up_to_seq") or body.get("upToSeq")
      if up_to_seq is None:
        return _json_response({"ok": False, "error": "up_to_seq or count required"}, status=400)
      try:
        inclusive = bool(body.get("inclusive", True))
        events = fork_transcript(log_path, int(up_to_seq), inclusive=inclusive)
      except Exception as e:
        return _json_response({"ok": False, "error": f"fork failed: {e}"}, status=400)
    return _json_response({
      "ok": True,
      "sessionId": session_id,
      "count": len(events),
      "events": events_to_dicts(events),
    })
  except Exception as e:
    return _json_response({"ok": False, "error": str(e)}, status=500)


def _session_manager_for_request(request: web.Request) -> Any:
  """Return a SessionManager scoped to the request's workspace."""
  try:
    from ai.system.paths import workspace_path
    from ai.core.session.manager import SessionManager
    cwd = str(workspace_path("", mkdir=True))
    return SessionManager(cwd)
  except Exception as exc:
    raise RuntimeError(f"session manager unavailable: {exc}") from exc


def _ensure_manager_session(manager: Any, session_id: str) -> Any:
  """Ensure SessionManager knows about a session.

  If the session record does not exist in SessionManager storage but a
  durable chat log exists at the chat log path, adopt it so pause/dispose
  can operate on chat-created sessions.
  """
  record = manager.storage.load_session(session_id)
  if record is not None:
    return record
  log_path = _session_log_path(session_id)
  if log_path and os.path.isfile(log_path):
    return manager.adopt_session(session_id)
  return None


async def api_session_pause(request: web.Request) -> web.Response:
  """POST /api/ai/sessions/{id}/pause - pause session processing."""
  session_id = request.match_info.get("session_id", "").strip()
  if not session_id:
    return _json_response({"ok": False, "error": "session_id required"}, status=400)
  try:
    manager = _session_manager_for_request(request)
    _ensure_manager_session(manager, session_id)
    record = manager.pause_session(session_id)
    if record is None:
      return _json_response({"ok": False, "error": "session not found"}, status=404)
    return _json_response({
      "ok": True,
      "sessionId": session_id,
      "state": "paused",
      "record": record.to_dict(),
    })
  except Exception as e:
    return _json_response({"ok": False, "error": str(e)}, status=500)


async def api_session_dispose(request: web.Request) -> web.Response:
  """POST /api/ai/sessions/{id}/dispose - dispose session resources."""
  session_id = request.match_info.get("session_id", "").strip()
  if not session_id:
    return _json_response({"ok": False, "error": "session_id required"}, status=400)
  try:
    manager = _session_manager_for_request(request)
    _ensure_manager_session(manager, session_id)
    ok = manager.dispose_session(session_id)
    if not ok:
      return _json_response({"ok": False, "error": "session not found"}, status=404)
    return _json_response({
      "ok": True,
      "sessionId": session_id,
      "state": "disposed",
    })
  except Exception as e:
    return _json_response({"ok": False, "error": str(e)}, status=500)
