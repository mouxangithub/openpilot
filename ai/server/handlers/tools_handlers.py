"""API handlers — tools."""

from ai.server.handlers._api_common import *  # noqa: F403

async def api_tools_meta(request: web.Request) -> web.Response:
  return _json_response({"ok": True, "tools": tool_meta_for_host(), "hostEnvironment": get_host_environment()})

async def api_workflows(request: web.Request) -> web.Response:
  return _json_response({"ok": True, "workflows": list_workflows()})

async def api_tune_passport(request: web.Request) -> web.Response:
  from ai.tools.tune_passport_store import list_tune_passport
  limit = int(request.query.get("limit", "30"))
  return _json_response(list_tune_passport(limit=limit))

async def api_tune_compare(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except json.JSONDecodeError:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  route_a = str(body.get("route_a") or "").strip()
  route_b = str(body.get("route_b") or "").strip()
  if not route_a or not route_b:
    return _json_response({"ok": False, "error": "route_a and route_b required"}, status=400)
  label_a = str(body.get("label_a") or "before")
  label_b = str(body.get("label_b") or "after")
  with_scores = bool(body.get("with_scores", True))
  from ai.tools.route_analysis_tools import compare_tune_ab
  compare = compare_tune_ab(route_a, route_b, label_a=label_a, label_b=label_b)
  if not compare.get("ok"):
    return _json_response(compare, status=400)
  out: dict[str, Any] = {"ok": True, "compare": compare}
  if with_scores:
    from ai.tools.route_scoring_tools import score_tune_session
    session = score_tune_session(route_a, route_b)
    out["session"] = session
  return _json_response(out)
