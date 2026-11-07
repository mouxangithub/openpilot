"""WorkBuddy harness API — transcript, audit, config."""

from __future__ import annotations

from aiohttp import web

from openpilot.common.params import Params

from ai.common.storage import read_param, read_param_bool, write_param, write_param_bool
from ai.tools.domains.platform.audit_store import list_audit_trail, verify_audit_chain
from ai.tools.domains.platform.transcript_store import list_events, recover_partial
from ai.tools.deferred_loading import deferred_loading_enabled
from ai.tools.result_externalize import externalize_enabled, threshold_bytes
from ai.common.model_tier import normalize_tier


async def api_harness_config(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  params: Params = request.app.get("params") or Params()
  if request.method == "GET":
    return json_response({
      "ok": True,
      "deferredTools": deferred_loading_enabled(params),
      "externalizeResults": externalize_enabled(params),
      "externalizeThreshold": threshold_bytes(params),
      "modelTier": normalize_tier(str(read_param(params, "ai_model_tier", "auto") or "auto")),
    })
  try:
    body = await request.json()
  except Exception:
    return json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  if not isinstance(body, dict):
    body = {}
  if "deferredTools" in body:
    write_param_bool(params, "ai_deferred_tools", bool(body["deferredTools"]))
  if "externalizeResults" in body:
    write_param_bool(params, "ai_externalize_results", bool(body["externalizeResults"]))
  if "externalizeThreshold" in body:
    try:
      val = max(1024, min(int(body["externalizeThreshold"]), 512_000))
      write_param(params, "ai_externalize_threshold", str(val))
    except (TypeError, ValueError):
      pass
  if "modelTier" in body:
    write_param(params, "ai_model_tier", normalize_tier(str(body["modelTier"])))
  return json_response({
    "ok": True,
    "deferredTools": deferred_loading_enabled(params),
    "externalizeResults": externalize_enabled(params),
    "externalizeThreshold": threshold_bytes(params),
    "modelTier": normalize_tier(str(read_param(params, "ai_model_tier", "auto") or "auto")),
  })


async def api_audit_trail(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  limit = int(request.query.get("limit", "50") or "50")
  tool = str(request.query.get("tool") or "").strip()
  since_ms = int(request.query.get("since") or request.query.get("sinceMs") or "0" or "0")
  if tool or since_ms > 0:
    from ai.tools.domains.platform.harness_db import query_audit
    data = query_audit(limit=limit, tool=tool, since_ms=since_ms)
    chain = verify_audit_chain(limit=min(limit, 200))
    data["chain"] = chain
    data["chain_ok"] = chain.get("ok") and not chain.get("broken")
    return json_response(data)
  data = list_audit_trail(limit=limit)
  chain = verify_audit_chain(limit=min(limit, 200))
  data["chain"] = chain
  return json_response(data)


async def api_usage_summary(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  group_by = str(request.query.get("groupBy") or "model").strip()
  since_ts = int(request.query.get("since") or "0" or "0")
  limit = int(request.query.get("limit", "20") or "20")
  from ai.tools.domains.platform.harness_db import query_usage_summary
  return json_response(query_usage_summary(group_by=group_by, since_ts=since_ts, limit=limit))


async def api_profile_sync(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  from ai.tools.domains.platform.profile_sync import (
    build_manifest,
    get_stored_manifest,
    merge_remote_manifest,
  )
  params: Params = request.app.get("params") or Params()
  if request.method == "GET":
    return json_response({
      "ok": True,
      "manifest": build_manifest(params),
      "stored": get_stored_manifest(params),
    })
  try:
    body = await request.json()
  except Exception:
    return json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  if not isinstance(body, dict):
    body = {}
  remote = body.get("manifest") or body
  mode = str(body.get("mode") or "merge")
  return json_response(merge_remote_manifest(params, remote, mode=mode))


async def api_workflows_custom(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  from ai.tools.domains.platform.workflow_custom import load_custom, save_custom, list_all_workflows
  from ai.tools.domains.platform.workflow_graph import load_graphs, save_graphs
  if request.method == "GET":
    return json_response({
      "ok": True,
      "custom": load_custom(),
      "graphs": load_graphs(),
      "all": list_all_workflows(),
    })
  try:
    body = await request.json()
  except Exception:
    return json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  workflows = body.get("workflows") if isinstance(body, dict) else None
  graphs = body.get("graphs") if isinstance(body, dict) else None
  results: dict[str, Any] = {}
  if workflows is not None:
    if not isinstance(workflows, dict):
      return json_response({"ok": False, "error": "workflows object required"}, status=400)
    results["workflows"] = save_custom(workflows)
  if graphs is not None:
    if not isinstance(graphs, dict):
      return json_response({"ok": False, "error": "graphs object required"}, status=400)
    results["graphs"] = save_graphs(graphs)
  ok = all(r.get("ok", True) for r in results.values())
  return json_response({"ok": ok, "results": results}, status=200 if ok else 400)


async def api_workflow_step(request: web.Request) -> web.Response:
  """POST /api/ai/workflows/{workflow_id}/step — advance or execute a graph workflow step."""
  from ai.server.deps import json_response
  from ai.tools.domains.platform.workflow_graph import run_graph_workflow_step, graph_workflow_requires_tools

  workflow_id = request.match_info.get("workflow_id", "").strip()
  if not workflow_id:
    return json_response({"ok": False, "error": "workflow_id required"}, status=400)

  if request.method == "GET":
    return json_response(graph_workflow_requires_tools(workflow_id))

  try:
    body = await request.json()
  except Exception:
    body = {}
  if not isinstance(body, dict):
    body = {}
  action = str(body.get("action") or "step").strip()
  node_id = str(body.get("nodeId") or body.get("node_id") or "").strip() or None
  inputs = body.get("inputs") if isinstance(body.get("inputs"), dict) else None
  return json_response(await run_graph_workflow_step(workflow_id, action, node_id=node_id, inputs=inputs))


async def api_transcript(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  session_id = str(
    request.query.get("sessionId") or request.query.get("session_id") or ""
  ).strip()
  if not session_id:
    return json_response({"ok": False, "error": "sessionId required"}, status=400)
  if request.path.endswith("/recover"):
    return json_response(recover_partial(session_id))
  limit = int(request.query.get("limit", "200") or "200")
  offset = int(request.query.get("offset", "0") or "0")
  return json_response(list_events(session_id, limit=limit, offset=offset))


def _workspace_dir() -> str:
  from ai.system.paths import workspace_path
  return str(workspace_path("", mkdir=True))


def _goal_store():
  from ai.goal.store import get_goal_store, set_goal_base_dir
  from ai.system.paths import workspace_path
  set_goal_base_dir(workspace_path("ai_goals", mkdir=True))
  return get_goal_store()


def _plan_store():
  from ai.plan.store import get_plan_store, set_plan_base_dir
  from ai.system.paths import workspace_path
  set_plan_base_dir(workspace_path("ai_plans", mkdir=True))
  return get_plan_store()


def _todo_store():
  from ai.todo.store import get_todo_store, set_todo_base_dir
  from ai.system.paths import workspace_path
  set_todo_base_dir(workspace_path("ai_todos", mkdir=True))
  return get_todo_store()


async def api_goals(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  store = _goal_store()
  if request.method == "GET":
    current = store.get()
    return json_response({"ok": True, "goal": current.to_dict() if current else None})
  try:
    body = await request.json()
  except Exception:
    return json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  op = str(body.get("operation", "create")).strip()
  try:
    if op == "create":
      view = store.create(body)
      return json_response({"ok": True, "goal": view.to_dict()})
    if op == "edit":
      view = store.edit(body.get("ref", {}), body.get("request", {}))
      return json_response({"ok": True, "goal": view.to_dict()})
    if op == "pause":
      view = store.pause(body.get("ref", {}))
      return json_response({"ok": True, "goal": view.to_dict()})
    if op == "resume":
      view = store.resume(body.get("ref", {}))
      return json_response({"ok": True, "goal": view.to_dict()})
    if op == "complete":
      view = store.complete(body.get("ref", {}))
      return json_response({"ok": True, "goal": view.to_dict()})
    if op == "block":
      view = store.block(body.get("ref", {}), body.get("reason", {}))
      return json_response({"ok": True, "goal": view.to_dict()})
    if op == "clear":
      ref = store.clear(body.get("ref", {}))
      return json_response({"ok": True, "ref": ref.to_dict()})
    return json_response({"ok": False, "error": f"unknown operation {op}"}, status=400)
  except Exception as e:
    if hasattr(e, "to_dict"):
      return json_response(e.to_dict(), status=409)
    return json_response({"ok": False, "error": str(e)}, status=500)


async def api_plans(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  store = _plan_store()
  if request.method == "GET":
    plan_id = str(request.query.get("planId") or request.query.get("plan_id") or "").strip()
    if plan_id:
      plan = store.get(plan_id)
      return json_response({"ok": True, "plan": plan.to_dict() if plan else None})
    return json_response({"ok": True, "plans": [p.to_dict() for p in store.list_all()]})
  try:
    body = await request.json()
  except Exception:
    return json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  op = str(body.get("operation", "create")).strip()
  try:
    if op == "create":
      plan = store.create(
        title=str(body.get("title", "")),
        steps=body.get("steps"),
        goal_id=body.get("goalId") or body.get("goal_id"),
        metadata=body.get("metadata"),
      )
      return json_response({"ok": True, "plan": plan.to_dict()})
    if op == "update":
      plan = store.update(str(body.get("planId") or body.get("plan_id") or ""), body.get("patch", {}))
      return json_response({"ok": True, "plan": plan.to_dict()})
    if op == "delete":
      ok = store.delete(str(body.get("planId") or body.get("plan_id") or ""))
      return json_response({"ok": ok})
    if op == "activate":
      plan = store.activate(str(body.get("planId") or body.get("plan_id") or ""))
      return json_response({"ok": True, "plan": plan.to_dict()})
    if op == "pause":
      plan = store.pause(str(body.get("planId") or body.get("plan_id") or ""))
      return json_response({"ok": True, "plan": plan.to_dict()})
    if op == "complete":
      plan = store.complete(str(body.get("planId") or body.get("plan_id") or ""))
      return json_response({"ok": True, "plan": plan.to_dict()})
    if op == "cancel":
      plan = store.cancel(str(body.get("planId") or body.get("plan_id") or ""))
      return json_response({"ok": True, "plan": plan.to_dict()})
    if op == "step_status":
      plan = store.set_step_status(
        str(body.get("planId") or body.get("plan_id") or ""),
        str(body.get("stepId") or body.get("step_id") or ""),
        str(body.get("status", "")),
      )
      return json_response({"ok": True, "plan": plan.to_dict()})
    if op == "mode":
      projection = store.set_mode(bool(body.get("active", False)))
      return json_response({"ok": True, "mode": projection.to_dict()})
    return json_response({"ok": False, "error": f"unknown operation {op}"}, status=400)
  except Exception as e:
    return json_response({"ok": False, "error": str(e)}, status=500)


async def api_todos(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  store = _todo_store()
  if request.method == "GET":
    return json_response({"ok": True, **store.get()})
  try:
    body = await request.json()
  except Exception:
    return json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  try:
    op = str(body.get("operation", "write")).strip()
    if op == "write":
      result = store.write(
        body.get("todos", []),
        allow_parallel=bool(body.get("allowParallel", True)),
        metadata=body.get("metadata"),
      )
      return json_response({"ok": True, **result})
    if op == "clear":
      result = store.clear()
      return json_response({"ok": True, **result})
    return json_response({"ok": False, "error": f"unknown operation {op}"}, status=400)
  except ValueError as e:
    return json_response({"ok": False, "error": str(e)}, status=400)
  except Exception as e:
    return json_response({"ok": False, "error": str(e)}, status=500)


async def api_subagents(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  from ai.subagent.pool import get_subagent_pool
  from ai.server.handlers.chat_handlers import _chat_tools_for_body

  params: Params = request.app.get("params") or Params()
  pool = get_subagent_pool(max_concurrency=4, params=params)
  if request.method == "GET":
    task_id = str(request.query.get("taskId") or request.query.get("task_id") or "").strip()
    if task_id:
      task = pool.get_task(task_id)
      result = pool.get_result(task_id)
      return json_response({
        "ok": True,
        "task": task.to_dict() if task else None,
        "result": result.to_dict() if result else None,
      })
    return json_response({"ok": True, "tasks": [t.to_dict() for t in pool.list_tasks()]})

  try:
    body = await request.json()
  except Exception:
    return json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  op = str(body.get("operation", "run")).strip()
  try:
    if op == "run":
      agent_id = str(body.get("agentId") or body.get("agent_id") or "devops").strip()
      prompt = str(body.get("prompt", "")).strip()
      if not prompt:
        return json_response({"ok": False, "error": "prompt required"}, status=400)
      task = pool.create_task(
        agent_id=agent_id,
        prompt=prompt,
        session_id=str(body.get("sessionId") or body.get("session_id") or ""),
        workflow=str(body.get("workflow", "")),
        tools=body.get("tools"),
        output_schema=body.get("outputSchema") or body.get("output_schema"),
        parent_id=body.get("parentId") or body.get("parent_id"),
        depth=int(body.get("depth", 0)),
        max_depth=int(body.get("maxDepth", body.get("max_depth", 3))),
        metadata=body.get("metadata"),
      )
      run_body = {
        "messages": [{"role": "user", "content": prompt}],
        "sessionId": task.session_id or f"sub-{task.id}",
        "_agent_route": {"agent_id": agent_id, "agentId": agent_id, "workflow_id": task.workflow},
      }
      tools, max_tool_rounds = _chat_tools_for_body(run_body)
      result = await pool.run(
        task,
        params=params,
        tools=tools,
        max_tool_rounds=max_tool_rounds,
      )
      return json_response({"ok": result.ok, "task": task.to_dict(), "result": result.to_dict()})
    if op == "cancel":
      ok = pool.cancel(str(body.get("taskId") or body.get("task_id") or ""))
      return json_response({"ok": ok})
    return json_response({"ok": False, "error": f"unknown operation {op}"}, status=400)
  except Exception as e:
    return json_response({"ok": False, "error": str(e)}, status=500)
