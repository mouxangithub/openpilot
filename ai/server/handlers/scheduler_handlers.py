"""API handlers — scheduler."""

from ai.server.handlers._api_common import *  # noqa: F403

async def api_scheduler(request: web.Request) -> web.Response:
  if request.method == "GET":
    return _json_response(list_tasks(_PARAMS))
  try:
    body = await request.json()
  except json.JSONDecodeError:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  if body.get("nl") or body.get("natural_language"):
    from ai.tools.scheduler import upsert_task_from_nl
    text = str(body.get("nl") or body.get("natural_language") or "")
    return _json_response(upsert_task_from_nl(_PARAMS, text))
  op = body.get("operation", "upsert")
  if op == "remove":
    return _json_response(remove_task(_PARAMS, str(body.get("task_id", ""))))
  return _json_response(upsert_task(
    _PARAMS,
    task_id=body.get("task_id"),
    name=str(body.get("name", "")),
    action=str(body.get("action", "read_last_log")),
    interval_minutes=int(body.get("interval_minutes", 60)),
    enabled=bool(body.get("enabled", True)),
    payload=body.get("payload"),
    trigger=str(body.get("trigger", "interval")),
  ))

async def api_write_confirm(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except json.JSONDecodeError:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  state = _get_state_reader().update(timeout=0)
  allowed, reason = is_action_allowed("write_param", state, admin=is_admin_mode(_PARAMS))
  if not allowed:
    return _json_response({"ok": False, "error": reason}, status=403)
  pending_id = str(body.get("pending_id", ""))
  if not pending_id:
    return _json_response({"ok": False, "error": "pending_id required"}, status=400)
  return _json_response(confirm_pending(_PARAMS, pending_id))

async def api_write_pending(request: web.Request) -> web.Response:
  return _json_response(list_pending(_PARAMS))


_AGENT_SCHEDULER = None


async def api_agent_schedule(request: web.Request) -> web.Response:
  """Isolated G6 agent-level schedule endpoints, separate from the Web scheduler.

  Supports:
    GET  ?agent_id=<id>            -> list schedules
    POST {agent_id, spec, payload} -> schedule (spec: 'at HH:MM' | 'cron ...' | 'every <n><s|m|h|d>')
    POST {op: 'cancel', job_id}    -> cancel a schedule
  """
  try:
    from ai.tools.domains.agent_scheduler import AgentScheduler, ERR_SCHEDULE_INVALID
  except Exception as e:
    return _json_response({"ok": False, "error_code": ERR_SCHEDULE_INVALID, "message": str(e)}, status=500)
  global _AGENT_SCHEDULER
  if _AGENT_SCHEDULER is None:
    _AGENT_SCHEDULER = AgentScheduler()
  scheduler = _AGENT_SCHEDULER
  if request.method == "GET":
    agent_id = str(request.query.get("agent_id") or "").strip()
    if not agent_id:
      return _json_response({"ok": False, "error_code": "INVALID_INPUT", "message": "agent_id required"}, status=400)
    return _json_response({"ok": True, "data": scheduler.list(agent_id)})
  try:
    body = await request.json()
  except Exception:
    return _json_response({"ok": False, "error_code": "INVALID_INPUT", "message": "invalid JSON"}, status=400)
  op = str(body.get("op") or "").strip()
  if op == "cancel":
    job_id = str(body.get("job_id") or "").strip()
    if not job_id:
      return _json_response({"ok": False, "error_code": "INVALID_INPUT", "message": "job_id required"}, status=400)
    return _json_response({"ok": scheduler.cancel(job_id)})
  agent_id = str(body.get("agent_id") or "").strip()
  spec = str(body.get("spec") or "").strip()
  if not agent_id or not spec:
    return _json_response({"ok": False, "error_code": "INVALID_INPUT", "message": "agent_id and spec required"}, status=400)
  result = scheduler.schedule(agent_id, spec, body.get("payload") if isinstance(body.get("payload"), dict) else {})
  status = 400 if not result.get("ok") else 200
  return _json_response(result, status=status)
