"""Harness model tools: goal, plan, todo, subagent, lsp, python and workflow.

All handlers are wired to the existing `ai.goal`, `ai.plan`, `ai.todo`,
`ai.subagent`, `ai.lsp`, `ai.mcp` and `ai.sandbox` modules. No stub /
unavailable / constant-success handlers remain — every tool performs a real
call and returns a structured `{ok, error?}` (or entity) result.
"""
from __future__ import annotations

import asyncio  # noqa: F401
from typing import Any

from ai.goal.models import CreateGoalRequest, EditGoalRequest, GoalRef
from ai.system.paths import workspace_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _error(message: str, *, code: str = "TOOL_ERROR", retryable: bool = False) -> dict[str, Any]:
  from ai.core.errors import tool_error
  return tool_error(message, code=code, retryable=retryable)


def _goal_store():
  from ai.goal.store import get_goal_store, set_goal_base_dir
  set_goal_base_dir(workspace_path("ai_goals", mkdir=True))
  return get_goal_store()


def _plan_store():
  from ai.plan.store import get_plan_store, set_plan_base_dir
  set_plan_base_dir(workspace_path("ai_plans", mkdir=True))
  return get_plan_store()


def _todo_store():
  from ai.todo.store import get_todo_store, set_todo_base_dir
  set_todo_base_dir(workspace_path("ai_todos", mkdir=True))
  return get_todo_store()


def _ref(args: dict[str, Any]) -> GoalRef:
  ref = args.get("ref") or args
  if isinstance(ref, dict):
    return GoalRef.from_dict(ref)
  return GoalRef(id=str(ref), revision=1)


def _bind_domain_sink(store: Any, domain: str) -> None:
  """Bind the current session log as a domain-event sink (G2/U6).

  Reads the SessionLog injected through the pipeline ``session_ctx``
  ContextVar; when present, every successful store mutation emits a
  ``<domain>/change`` event so goal/plan/todo state is replayable from
  the session log. No-op outside a session (legacy HTTP/CLI callers).
  """
  try:
    from ai.core.tools.pipeline import session_ctx
    log = session_ctx.get()
  except Exception:
    return
  if log is None:
    return

  def _sink(snapshot: Any, tombstone: bool = False) -> None:
    try:
      log.append_domain_event(domain, snapshot, tombstone=tombstone)
    except Exception:
      pass

  try:
    store.set_event_sink(_sink)
  except Exception:
    pass


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

def _f(name, description, properties, required=None):
  return {
    "type": "function",
    "function": {
      "name": name,
      "description": description,
      "parameters": {"type": "object", "properties": properties, "required": list(required or [])},
    },
  }


def harness_tool_schemas(params=None) -> list[dict[str, Any]]:
  ref_schema = {"type": "object", "properties": {"id": {"type": "string"}, "revision": {"type": "integer"}}}
  return [
    _f("goal_create", "创建会话目标", {"objective": {"type": "string"}, "maxGoalRounds": {"type": "integer"}}, ["objective"]),
    _f("goal_get", "读取当前会话目标", {}),
    _f("goal_edit", "编辑会话目标", {"ref": ref_schema, "objective": {"type": "string"}, "maxGoalRounds": {"type": "integer"}}, ["ref"]),
    _f("goal_pause", "暂停会话目标", {"ref": ref_schema}, ["ref"]),
    _f("goal_resume", "恢复会话目标", {"ref": ref_schema}, ["ref"]),
    _f("goal_complete", "完成会话目标", {"ref": ref_schema}, ["ref"]),
    _f("goal_block", "阻塞会话目标", {"ref": ref_schema, "reason": {"type": "object", "properties": {"code": {"type": "string"}, "message": {"type": "string"}}}}, ["ref", "reason"]),
    _f("plan_generate", "生成执行计划", {"title": {"type": "string"}, "steps": {"type": "array", "items": {"type": "object"}}, "goal_id": {"type": "string"}}, ["title"]),
    _f("plan_update", "更新计划", {"plan_id": {"type": "string"}, "patch": {"type": "object"}}, ["plan_id", "patch"]),
    _f("plan_activate", "激活计划", {"plan_id": {"type": "string"}}, ["plan_id"]),
    _f("plan_step_status", "设置步骤状态", {"plan_id": {"type": "string"}, "step_id": {"type": "string"}, "status": {"type": "string"}}, ["plan_id", "step_id", "status"]),
    _f("plan_complete", "完成计划", {"plan_id": {"type": "string"}}, ["plan_id"]),
    _f("todo_write", "写入待办事项", {"todos": {"type": "array", "items": {"type": "object"}}, "allowParallel": {"type": "boolean"}}),
    _f("todo_clear", "清理待办事项", {}),
    _f("todo_get", "读取待办事项", {}),
    _f("subagent_start", "启动子代理", {"agent_id": {"type": "string"}, "prompt": {"type": "string"}, "workflow": {"type": "string"}, "max_depth": {"type": "integer"}, "provider": {"type": "string", "enum": ["in-process"]}}, ["agent_id", "prompt"]),
    _f("subagent_start_many", "并行启动多个子代理（互相独立的批量任务）", {"tasks": {"type": "array", "items": {"type": "object"}}, "max_concurrency": {"type": "integer"}}, ["tasks"]),
    _f("subagent_query", "查询子代理状态", {"task_id": {"type": "string"}}, ["task_id"]),
    _f("subagent_cancel", "取消子代理", {"task_id": {"type": "string"}}, ["task_id"]),
    _f("subagent_report", "子代理向父会话提交结构化汇报", {"content": {"type": "string"}, "session_id": {"type": "string"}, "call_id": {"type": "string"}}, ["content"]),
    _f("lsp", "执行只读 LSP 查询（坐标 1-based UTF-16）", {
      "action": {"type": "string", "enum": ["goToDefinition", "findReferences", "goToImplementation", "hover"]},
      "uri": {"type": "string"},
      "line": {"type": "integer"},
      "character": {"type": "integer"},
      "workspaceRoot": {"type": "string"},
    }, ["action", "uri", "line", "character"]),
    _f("run_python_code", "在只读沙箱运行 Python（blocked os/subprocess imports）", {"code": {"type": "string"}, "timeout_s": {"type": "number"}}, ["code"]),
    _f("workflow_advance", "推进工作流节点（graph）", {
      "workflow_id": {"type": "string"},
      "node_id": {"type": "string"},
      "action": {"type": "string", "enum": ["step", "retry", "pause", "resume"]},
    }, ["workflow_id", "action"]),
    _f("mcp_discover", "发现已授权 MCP 服务工具", {"server_id": {"type": "string"}}, ["server_id"]),
  ]


# ---------------------------------------------------------------------------
# Tool metadata (T-P0.3)
# ---------------------------------------------------------------------------
# Module-level metadata so toolset/permission/Web-panel logic can reason about
# harness tools from a stable constant instead of a dynamic function. Kept in
# sync with ``harness_tool_schemas``. ``group`` follows the same taxonomy used
# by ``TOOL_META`` (read/write/agent/coding/mcp).
HARNESS_TOOL_META: dict[str, dict[str, Any]] = {
  "goal_create": {"label": "创建目标", "group": "agent", "default_enabled": True, "driving": True},
  "goal_get": {"label": "读取目标", "group": "agent", "default_enabled": True, "driving": True},
  "goal_edit": {"label": "编辑目标", "group": "agent", "default_enabled": True, "driving": True},
  "goal_pause": {"label": "暂停目标", "group": "agent", "default_enabled": True, "driving": True},
  "goal_resume": {"label": "恢复目标", "group": "agent", "default_enabled": True, "driving": True},
  "goal_complete": {"label": "完成目标", "group": "agent", "default_enabled": True, "driving": True},
  "goal_block": {"label": "阻塞目标", "group": "agent", "default_enabled": True, "driving": True},
  "plan_generate": {"label": "生成计划", "group": "agent", "default_enabled": True, "driving": True},
  "plan_update": {"label": "更新计划", "group": "agent", "default_enabled": True, "driving": True},
  "plan_activate": {"label": "激活计划", "group": "agent", "default_enabled": True, "driving": True},
  "plan_step_status": {"label": "步骤状态", "group": "agent", "default_enabled": True, "driving": True},
  "plan_complete": {"label": "完成计划", "group": "agent", "default_enabled": True, "driving": True},
  "todo_write": {"label": "写入待办", "group": "agent", "default_enabled": True, "driving": True},
  "todo_clear": {"label": "清理待办", "group": "agent", "default_enabled": True, "driving": True},
  "todo_get": {"label": "读取待办", "group": "agent", "default_enabled": True, "driving": True},
  "subagent_start": {"label": "启动子代理", "group": "agent", "default_enabled": True, "driving": True},
  "subagent_start_many": {"label": "批量启动子代理", "group": "agent", "default_enabled": True, "driving": True},
  "subagent_query": {"label": "查询子代理", "group": "agent", "default_enabled": True, "driving": True},
  "subagent_cancel": {"label": "取消子代理", "group": "agent", "default_enabled": True, "driving": True},
  "subagent_report": {"label": "子代理汇报", "group": "agent", "default_enabled": True, "driving": True},
  "lsp": {"label": "LSP 查询", "group": "coding", "default_enabled": True, "driving": True},
  "run_python_code": {"label": "运行 Python", "group": "coding", "default_enabled": True, "driving": True},
  "workflow_advance": {"label": "推进工作流", "group": "agent", "default_enabled": True, "driving": True},
  "schedule_create": {"label": "创建定时任务", "group": "write", "default_enabled": True, "driving": True},
  "schedule_list": {"label": "定时任务列表", "group": "read", "default_enabled": True, "driving": True},
  "schedule_delete": {"label": "删除定时任务", "group": "write", "default_enabled": True, "driving": True},
  "mcp_discover": {"label": "发现 MCP 工具", "group": "mcp", "default_enabled": True, "driving": True},
}


# ---------------------------------------------------------------------------
# Goal handlers
# ---------------------------------------------------------------------------

def _h_goal_create(a: dict[str, Any]) -> dict[str, Any]:
  try:
    store = _goal_store()
    _bind_domain_sink(store, "goal")
    view = store.create(CreateGoalRequest(
      objective=str(a.get("objective", "")),
      max_goal_rounds=a.get("maxGoalRounds"),
    ))
    return {"ok": True, "goal": view.to_dict()}
  except Exception as exc:
    return _error(str(exc))


def _h_goal_get(_a: dict[str, Any]) -> dict[str, Any]:
  try:
    view = _goal_store().get()
    return {"ok": True, "goal": view.to_dict() if view else None}
  except Exception as exc:
    return _error(str(exc))


def _h_goal_edit(a: dict[str, Any]) -> dict[str, Any]:
  try:
    store = _goal_store()
    _bind_domain_sink(store, "goal")
    view = store.edit(_ref(a), EditGoalRequest(
      objective=a.get("objective"),
      max_goal_rounds=a.get("maxGoalRounds"),
    ))
    return {"ok": True, "goal": view.to_dict()}
  except Exception as exc:
    return _error(str(exc))


def _h_goal_pause(a: dict[str, Any]) -> dict[str, Any]:
  try:
    store = _goal_store()
    _bind_domain_sink(store, "goal")
    return {"ok": True, "goal": store.pause(_ref(a)).to_dict()}
  except Exception as exc:
    return _error(str(exc))


def _h_goal_resume(a: dict[str, Any]) -> dict[str, Any]:
  try:
    store = _goal_store()
    _bind_domain_sink(store, "goal")
    return {"ok": True, "goal": store.resume(_ref(a)).to_dict()}
  except Exception as exc:
    return _error(str(exc))


def _h_goal_complete(a: dict[str, Any]) -> dict[str, Any]:
  try:
    store = _goal_store()
    _bind_domain_sink(store, "goal")
    return {"ok": True, "goal": store.complete(_ref(a)).to_dict()}
  except Exception as exc:
    return _error(str(exc))


def _h_goal_block(a: dict[str, Any]) -> dict[str, Any]:
  try:
    store = _goal_store()
    _bind_domain_sink(store, "goal")
    view = store.block(_ref(a), dict(a.get("reason") or {}))
    return {"ok": True, "goal": view.to_dict()}
  except Exception as exc:
    return _error(str(exc))


# ---------------------------------------------------------------------------
# Plan handlers
# ---------------------------------------------------------------------------

def _h_plan_generate(a: dict[str, Any]) -> dict[str, Any]:
  try:
    store = _plan_store()
    _bind_domain_sink(store, "plan")
    plan = store.create(
      title=str(a.get("title", "")),
      steps=a.get("steps") or [],
      goal_id=a.get("goal_id") or a.get("goalId"),
    )
    return {"ok": True, "plan": plan.to_dict()}
  except Exception as exc:
    return _error(str(exc))


def _h_plan_update(a: dict[str, Any]) -> dict[str, Any]:
  try:
    store = _plan_store()
    _bind_domain_sink(store, "plan")
    plan = store.update(str(a.get("plan_id", "")), dict(a.get("patch") or {}))
    return {"ok": True, "plan": plan.to_dict()}
  except Exception as exc:
    return _error(str(exc))


def _h_plan_activate(a: dict[str, Any]) -> dict[str, Any]:
  try:
    store = _plan_store()
    _bind_domain_sink(store, "plan")
    return {"ok": True, "plan": store.activate(str(a.get("plan_id", ""))).to_dict()}
  except Exception as exc:
    return _error(str(exc))


def _h_plan_step_status(a: dict[str, Any]) -> dict[str, Any]:
  try:
    store = _plan_store()
    _bind_domain_sink(store, "plan")
    plan = store.set_step_status(
      str(a.get("plan_id", "")),
      str(a.get("step_id", "")),
      str(a.get("status", "")),
    )
    return {"ok": True, "plan": plan.to_dict()}
  except Exception as exc:
    return _error(str(exc))


def _h_plan_complete(a: dict[str, Any]) -> dict[str, Any]:
  try:
    store = _plan_store()
    _bind_domain_sink(store, "plan")
    return {"ok": True, "plan": store.complete(str(a.get("plan_id", ""))).to_dict()}
  except Exception as exc:
    return _error(str(exc))


# ---------------------------------------------------------------------------
# Todo handlers
# ---------------------------------------------------------------------------

def _h_todo_write(a: dict[str, Any]) -> dict[str, Any]:
  try:
    store = _todo_store()
    _bind_domain_sink(store, "todo")
    result = store.write(
      a.get("todos", []),
      allow_parallel=bool(a.get("allowParallel", True)),
      metadata=a.get("metadata"),
    )
    return {"ok": True, **result}
  except Exception as exc:
    return _error(str(exc))


def _h_todo_clear(_a: dict[str, Any]) -> dict[str, Any]:
  try:
    store = _todo_store()
    _bind_domain_sink(store, "todo")
    return {"ok": True, **store.clear()}
  except Exception as exc:
    return _error(str(exc))


def _h_todo_get(_a: dict[str, Any]) -> dict[str, Any]:
  try:
    return {"ok": True, **_todo_store().get()}
  except Exception as exc:
    return _error(str(exc))


# ---------------------------------------------------------------------------
# Subagent handlers (async — pool.run is a coroutine)
# ---------------------------------------------------------------------------

def _subagent_pool():
  from ai.subagent.pool import get_subagent_pool
  return get_subagent_pool()


def _session_log_from_ctx() -> Any:
  """Best-effort SessionLog from the pipeline session_ctx (subagent lineage)."""
  try:
    from ai.core.tools.pipeline import session_ctx
    return session_ctx.get()
  except Exception:
    return None


async def _h_subagent_start(a: dict[str, Any]) -> dict[str, Any]:
  try:
    pool = _subagent_pool()
    task = pool.create_task(
      agent_id=str(a.get("agent_id", "")),
      prompt=str(a.get("prompt", "")),
      workflow=str(a.get("workflow", "")),
      max_depth=int(a.get("max_depth", 3)),
      provider=str(a.get("provider", "in-process") or "in-process"),
    )
    if isinstance(a.get("output_schema"), dict):
      task.output_schema = a["output_schema"]
    if isinstance(a.get("tools"), list):
      task.tools = [str(t) for t in a["tools"]]
    result = await pool.run(task, params=None, tools=None, max_tool_rounds=24, session_log=_session_log_from_ctx())
    return {"ok": result.ok, "task": task.to_dict(), "result": result.to_dict()}
  except Exception as exc:
    return _error(str(exc))


async def _h_subagent_start_many(a: dict[str, Any]) -> dict[str, Any]:
  """Parallel fan-out of independent subagent tasks via the pool's gather."""
  try:
    raw_tasks = a.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
      return _error("subagent_start_many requires a non-empty tasks array")
    pool = _subagent_pool()
    tasks = []
    for t in raw_tasks:
      if not isinstance(t, dict):
        continue
      tasks.append(pool.create_task(
        agent_id=str(t.get("agent_id", "")),
        prompt=str(t.get("prompt", "")),
        workflow=str(t.get("workflow", "")),
        max_depth=int(t.get("max_depth", 3)),
        provider=str(t.get("provider", "in-process") or "in-process"),
      ))
    if not tasks:
      return _error("subagent_start_many: no valid tasks provided")
    results = await pool.run_many(tasks, params=None, tools=None, max_tool_rounds=24)
    payloads = [r.to_dict() if hasattr(r, "to_dict") else {"taskId": task.id, "ok": False, "error": str(r)} for r, task in zip(results, tasks)]
    ok = all(p.get("ok") for p in payloads)
    return {"ok": ok, "count": len(payloads), "results": payloads}
  except Exception as exc:
    return _error(str(exc))


def _h_subagent_report(a: dict[str, Any]) -> dict[str, Any]:
  """child -> parent structured report channel.

  A subagent can use this to return a concise structured result to the
  parent session (mirrors dsh ``tool-subagent-report``). The report is
  appended to the current session log as a surface event so the parent can
  reference it after the child completes.
  """
  try:
    content = a.get("content") or a.get("report") or a.get("summary")
    if not isinstance(content, str) or not content.strip():
      return _error("subagent_report requires a non-empty content/summary")
    session_id = str(a.get("session_id", "")).strip()
    from ai.core.session.log import EventType, SessionLog, SurfaceOp
    from ai.system.paths import workspace_path
    log = SessionLog(session_id, persist_path=workspace_path("ai_session_logs", mkdir=True) / f"{session_id}.jsonl" if session_id else None)
    log.append(
      EventType.TOOL_RESULT,
      {
        "tool_call_id": str(a.get("call_id", "") or "subagent_report"),
        "name": "subagent_report",
        "content": content,
      },
      surface_op=SurfaceOp.APPEND,
    )
    log.close()
    return {"ok": True, "reported": content[:500]}
  except Exception as exc:
    return _error(str(exc))


def _h_subagent_query(a: dict[str, Any]) -> dict[str, Any]:
  try:
    pool = _subagent_pool()
    task_id = str(a.get("task_id", ""))
    task = pool.get_task(task_id)
    result = pool.get_result(task_id)
    return {"ok": True, "task": task.to_dict() if task else None, "result": result.to_dict() if result else None}
  except Exception as exc:
    return _error(str(exc))


def _h_subagent_cancel(a: dict[str, Any]) -> dict[str, Any]:
  try:
    ok = _subagent_pool().cancel(str(a.get("task_id", "")))
    return {"ok": True, "cancelled": ok}
  except Exception as exc:
    return _error(str(exc))


# ---------------------------------------------------------------------------
# LSP handler (async)
# ---------------------------------------------------------------------------

_lsp_manager: Any = None


def set_lsp_manager(manager: Any) -> None:
  """Inject the shared LspServerManager owned by the app (app_factory)."""
  global _lsp_manager
  _lsp_manager = manager


def get_lsp_manager():
  global _lsp_manager
  if _lsp_manager is None:
    from ai.lsp.server_manager import LspServerManager
    _lsp_manager = LspServerManager()
  return _lsp_manager


def _normalize_location(item: Any) -> dict[str, Any]:
  """Normalize an LSP Location to a renderable result dict (1-based)."""
  if isinstance(item, dict):
    uri = item.get("uri", "")
    rng = item.get("range") or {}
    start = rng.get("start") or {}
    line = int(start.get("line", 0)) + 1
    char = int(start.get("character", 0)) + 1
    return {"path": uri, "line": line, "character": char, "label": "", "detail": "", "snippet": ""}
  return {"path": "", "line": 0, "character": 0, "label": str(item), "detail": "", "snippet": ""}


def _normalize_diagnostic(item: Any, default_uri: str) -> dict[str, Any]:
  """Normalize an LSP Diagnostic to a renderable result dict (1-based)."""
  if not isinstance(item, dict):
    return {"path": default_uri, "line": 0, "character": 0, "label": str(item), "detail": "", "snippet": ""}
  rng = item.get("range") or {}
  start = rng.get("start") or {}
  line = int(start.get("line", 0)) + 1
  char = int(start.get("character", 0)) + 1
  severity = item.get("severity")
  severity_label = {1: "error", 2: "warning", 3: "info", 4: "hint"}.get(severity, "")
  message = str(item.get("message", ""))
  code = item.get("code", "")
  label = f"{severity_label or 'diagnostic'}: {message[:80]}"
  detail = f"{message}\ncode: {code}"
  return {"path": default_uri, "line": line, "character": char, "label": label, "detail": detail, "snippet": ""}


def _hover_contents(item: dict[str, Any]) -> str:
  contents = item.get("contents")
  if isinstance(contents, str):
    return contents
  if isinstance(contents, dict):
    return str(contents.get("value", ""))
  if isinstance(contents, list):
    parts = []
    for c in contents:
      if isinstance(c, str):
        parts.append(c)
      elif isinstance(c, dict):
        parts.append(str(c.get("value", "")))
    return "\n".join(parts)
  return ""


async def _h_lsp(a: dict[str, Any]) -> dict[str, Any]:
  """Run one routed LSP query with structured errors, 60s budget and caps."""
  from ai.lsp.errors import INVALID_RESPONSE, NO_PROVIDER, TIMEOUT, WORKSPACE_OUTSIDE, LspError
  action = str(a.get("action", ""))
  uri = str(a.get("uri", "")).strip()
  workspace_root = str(a.get("workspaceRoot") or workspace_path("", mkdir=True)).strip()
  line = int(a.get("line", 1))
  character = int(a.get("character", 1))
  line0 = max(0, line - 1)
  char0 = max(0, character - 1)
  if not uri:
    return LspError("lsp requires uri", INVALID_RESPONSE).to_dict()
  if action not in ("goToDefinition", "findReferences", "goToImplementation", "hover", "diagnostics", "rename"):
    return LspError(f"unsupported lsp action: {action}", INVALID_RESPONSE).to_dict()
  try:
    from urllib.parse import urlparse
    from urllib.request import url2pathname
    from pathlib import Path
    parsed = urlparse(uri)
    if parsed.scheme == "file":
      # url2pathname handles the Windows `file:///C:/...` form (which
      # Path('/C:/...') would otherwise mis-resolve) and percent-decoding.
      file_path = Path(url2pathname(parsed.path)).resolve()
      root_path = Path(workspace_root).resolve()
      try:
        file_path.relative_to(root_path)
      except ValueError:
        return LspError("file is outside workspaceRoot", WORKSPACE_OUTSIDE, {"uri": uri, "workspaceRoot": workspace_root}).to_dict()
  except Exception as exc:
    return LspError("invalid LSP URI", INVALID_RESPONSE, str(exc)).to_dict()

  manager = get_lsp_manager()
  client = manager.get_client(workspace_root)
  if client is None:
    return LspError(f"no LSP server for workspace '{workspace_root}'", NO_PROVIDER, {"workspaceRoot": workspace_root}).to_dict()
  new_name = str(a.get("newName") or a.get("new_name") or "").strip()
  try:
    if action == "goToDefinition":
      raw = await asyncio.wait_for(client.definition(uri, line0, char0), timeout=60.0)
      if not isinstance(raw, list):
        raise LspError("LSP definition response must be an array", INVALID_RESPONSE)
      results = [_normalize_location(x) for x in raw]
    elif action == "findReferences":
      raw = await asyncio.wait_for(client.references(uri, line0, char0), timeout=60.0)
      if not isinstance(raw, list):
        raise LspError("LSP references response must be an array", INVALID_RESPONSE)
      results = [_normalize_location(x) for x in raw]
    elif action == "goToImplementation":
      raw = await asyncio.wait_for(client.implementation(uri, line0, char0), timeout=60.0)
      if not isinstance(raw, list):
        raise LspError("LSP implementation response must be an array", INVALID_RESPONSE)
      results = [_normalize_location(x) for x in raw]
    elif action == "diagnostics":
      raw = await asyncio.wait_for(client.diagnostic(uri, line0, char0), timeout=60.0)
      if raw is not None and not isinstance(raw, dict):
        raise LspError("LSP diagnostics response must be an object or null", INVALID_RESPONSE)
      results = [_normalize_diagnostic(x, uri) for x in raw.get("items", [])] if raw else []
    elif action == "rename":
      if not new_name:
        return LspError("rename requires newName", INVALID_RESPONSE).to_dict()
      raw = await asyncio.wait_for(client.rename(uri, line0, char0, new_name), timeout=60.0)
      if raw is not None and not isinstance(raw, dict):
        raise LspError("LSP rename response must be a WorkspaceEdit or null", INVALID_RESPONSE)
      return {"ok": True, "action": action, "edit": raw}
    else:
      raw = await asyncio.wait_for(client.hover(uri, line0, char0), timeout=60.0)
      if raw is not None and not isinstance(raw, dict):
        raise LspError("LSP hover response must be an object or null", INVALID_RESPONSE)
      results = [] if not raw else [{"path": uri, "line": line, "character": character, "label": "", "detail": _hover_contents(raw), "snippet": ""}]
    truncated = len(results) > 100
    results = results[:100]
    payload = {"ok": True, "action": action, "results": results, "truncated": truncated}
    import json
    encoded = json.dumps(payload, ensure_ascii=False, default=str)
    if len(encoded) > 65536:
      payload["results"] = payload["results"][:max(1, len(payload["results"]) // 2)]
      payload["truncated"] = True
    return payload
  except asyncio.TimeoutError:
    return LspError("LSP query timed out after 60 seconds", TIMEOUT, {"action": action}).to_dict()
  except asyncio.CancelledError:
    try:
      await manager.stop_server(workspace_root)
    finally:
      raise
  except LspError as exc:
    return exc.to_dict()
  except Exception as exc:
    return LspError(f"LSP {action} failed", INVALID_RESPONSE, str(exc)).to_dict()


# ---------------------------------------------------------------------------
# Python runner (async)
# ---------------------------------------------------------------------------

async def _h_run_python_code(a: dict[str, Any]) -> dict[str, Any]:
  try:
    from ai.core.tools.sandbox_hooks import run_python_via_sandbox
    return await run_python_via_sandbox(str(a.get("code", "")), timeout=int(a.get("timeout_s", 10)), session_id=str(a.get("sessionId") or a.get("session_id") or ""), cwd=a.get("cwd"))
  except Exception as exc:
    return _error(str(exc))


# ---------------------------------------------------------------------------
# Workflow advance (async)
# ---------------------------------------------------------------------------

async def _h_workflow_advance(a: dict[str, Any]) -> dict[str, Any]:
  try:
    from ai.tools.domains.platform.workflow_graph import advance_graph_workflow
    workflow_id = str(a.get("workflow_id", ""))
    action = str(a.get("action", "step"))
    return advance_graph_workflow(workflow_id, action, a.get("node_id"))
  except Exception as exc:
    return _error(str(exc))


# ---------------------------------------------------------------------------
# MCP handlers
# ---------------------------------------------------------------------------

def _load_mcp_servers(params: Any) -> list[dict[str, Any]]:
  try:
    import json
    from ai.common.storage import read_param
    from ai.mcp.host import MCP_SERVERS_KEY
    raw = read_param(params, MCP_SERVERS_KEY)
    if not raw:
      return []
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="replace")
    data = json.loads(raw)
    return data if isinstance(data, list) else []
  except Exception:
    return []


async def _call_mcp_tool(server_id: str, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
  from ai.mcp.host import call_mcp_tool
  try:
    from openpilot.common.params import Params
    controls = {"sessionId", "session_id", "cwd", "timeout", "timeout_s"}
    payload = {k: v for k, v in args.items() if k not in controls}
    return await call_mcp_tool(Params(), server_id=server_id, tool_name=tool_name, arguments=payload, session_id=str(args.get("sessionId") or args.get("session_id") or ""))
  except Exception as exc:
    return _error(str(exc))


_mcp_handlers: dict[str, Any] = {}
_mcp_schemas: list[dict[str, Any]] = []


def _make_mcp_handler(server_id: str, tool_name: str):
  async def handler(args: dict[str, Any]) -> dict[str, Any]:
    return await _call_mcp_tool(server_id, tool_name, args)
  return handler


def _validate_mcp_tool(tool: Any) -> dict[str, Any] | None:
  if not isinstance(tool, dict) or not isinstance(tool.get("name"), str) or not tool["name"].strip():
    return None
  schema = tool.get("inputSchema") or {"type": "object", "properties": {}}
  if not isinstance(schema, dict) or schema.get("type") not in (None, "object"):
    return None
  return {"type": "function", "function": {"name": tool["name"].strip(), "description": str(tool.get("description") or ""), "parameters": schema}}


def register_mcp_handlers(handlers, params=None) -> None:
  """Namespace registered tools as ``mcp_<server>_<tool>`` (async) -> call_mcp_tool.

  Default-deny: only servers with ``enabled`` and a stored ``tools`` list are
  registered (visible to the LLM). A ``mcp_discover`` helper tool is registered
  so an authorized server's tools can be listed on demand.
  """
  global _mcp_handlers, _mcp_schemas
  servers = _load_mcp_servers(params)
  added: set[str] = set()
  _mcp_handlers = {}
  _mcp_schemas = []
  for server in servers:
    if not server.get("enabled", True):
      continue
    server_id = str(server.get("id") or "").strip()
    if not server_id:
      continue
    for tool in server.get("tools") or []:
      spec = tool if isinstance(tool, dict) else {"name": str(tool)}
      valid = _validate_mcp_tool(spec)
      if valid is None:
        continue
      name = valid["function"]["name"]
      handler_name = f"mcp__{server_id}__{name}"
      base = handler_name
      suffix = 1
      while handler_name in added:
        handler_name = f"{base}_{suffix}"
        suffix += 1
      added.add(handler_name)
      handler = _make_mcp_handler(server_id, name)
      handlers[handler_name] = handler
      _mcp_handlers[handler_name] = handler
      valid["function"]["name"] = handler_name
      _mcp_schemas.append(valid)
      from ai.tools.runtime_meta import register_tool_meta
      register_tool_meta(
        handler_name,
        label=valid["function"].get("description", name)[:40],
        description=valid["function"].get("description", ""),
        group="mcp",
      )
  if "mcp_discover" not in added:
    handlers["mcp_discover"] = _h_mcp_discover


async def _h_mcp_discover(a: dict[str, Any]) -> dict[str, Any]:
  server_id = str(a.get("server_id", "")).strip()
  if not server_id:
    return _error("mcp_discover requires server_id")
  try:
    from openpilot.common.params import Params
    from ai.mcp.host import discover_mcp_tools
    result = await discover_mcp_tools(Params(), server_id)
    if not isinstance(result, dict) or not result.get("ok"):
      return result if isinstance(result, dict) else _error("MCP discovery failed")
    tools = result.get("tools")
    if not isinstance(tools, list):
      return _error("MCP discovery returned malformed tools")
    discovered: list[dict[str, Any]] = []
    for tool in tools:
      spec = _validate_mcp_tool(tool)
      if spec is None:
        return _error("MCP discovery returned malformed tool schema")
      name = spec["function"]["name"]
      key = f"mcp__{server_id}__{name}"
      handler = _make_mcp_handler(server_id, name)
      _mcp_handlers[key] = handler
      spec["function"]["name"] = key
      _mcp_schemas.append(spec)
      discovered.append(spec)
      from ai.tools.runtime_meta import register_tool_meta
      register_tool_meta(
        key,
        label=spec["function"].get("description", name)[:40],
        description=spec["function"].get("description", ""),
        group="mcp",
      )
    return {**result, "tools": discovered}
  except Exception as exc:
    return _error(str(exc))


# ---------------------------------------------------------------------------
# Schedule handlers (agent-scoped durable reminders)
# ---------------------------------------------------------------------------

def _schedule_store():
  from ai.schedule.store import get_schedule_store
  return get_schedule_store()


def _bind_schedule_sink(store: Any) -> None:
  """Project schedule mutations into the session log as schedule/change."""
  try:
    from ai.core.tools.pipeline import session_ctx
    log = session_ctx.get()
  except Exception:
    return
  if log is None:
    return

  def _sink(payload: dict[str, Any]) -> None:
    try:
      from ai.core.session.log import EventType
      snapshot = payload.get("snapshot")
      tombstone = bool(payload.get("tombstone"))
      log.append(
        EventType.SCHEDULE_CHANGE,
        {"version": 1, "snapshot": snapshot, "tombstone": tombstone},
      )
    except Exception:
      pass

  try:
    store.set_event_sink(_sink)
  except Exception:
    pass


def _schedule_create_error(exc: Exception) -> dict[str, Any]:
  if hasattr(exc, "code"):
    return {"ok": False, "error": str(exc), "error_code": exc.code}
  return _error(str(exc))


def _h_schedule_create(a: dict[str, Any]) -> dict[str, Any]:
  """Create a reminder; exactly one of after_seconds / at / every_seconds."""
  try:
    store = _schedule_store()
    _bind_schedule_sink(store)
    selectors = [s for s in ("after_seconds", "at", "every_seconds") if a.get(s) is not None]
    if len(selectors) != 1:
      return {"ok": False, "error": "schedule_create accepts exactly one of after_seconds, at, or every_seconds.", "error_code": "invalid_rule"}
    from ai.schedule.store import ScheduleInputError
    try:
      if selectors[0] == "after_seconds":
        record = store.create_after(str(a.get("prompt", "")), a["after_seconds"])
      elif selectors[0] == "at":
        record = store.create_at(str(a.get("prompt", "")), str(a["at"]))
      else:
        record = store.create_every(str(a.get("prompt", "")), a["every_seconds"])
    except ScheduleInputError as exc:
      return _schedule_create_error(exc)
    return {"ok": True, "schedule": record.to_dict()}
  except Exception as exc:
    return _error(str(exc))


def _h_schedule_list(_a: dict[str, Any]) -> dict[str, Any]:
  try:
    store = _schedule_store()
    schedules = [r.to_dict() for r in store.list()]
    return {"ok": True, "schedules": schedules, "count": len(schedules)}
  except Exception as exc:
    return _error(str(exc))


def _h_schedule_delete(a: dict[str, Any]) -> dict[str, Any]:
  try:
    store = _schedule_store()
    _bind_schedule_sink(store)
    schedule_id = str(a.get("id", "")).strip()
    if not schedule_id:
      return {"ok": False, "error": "schedule_delete id must be non-empty without surrounding whitespace.", "error_code": "invalid_rule"}
    deleted = store.delete(schedule_id)
    if not deleted:
      return {"ok": False, "error": f"schedule not found: {schedule_id}", "error_code": "schedule_not_found", "id": schedule_id}
    return {"ok": True, "id": schedule_id, "deleted": True}
  except Exception as exc:
    return _schedule_create_error(exc)


# ---------------------------------------------------------------------------
# Registration entry points
# ---------------------------------------------------------------------------

def make_harness_handlers(*, params=None, get_state_reader=None, toolbox=None) -> dict[str, Any]:
  """Return a fresh dict of harness handlers (return-dict style, T-P0.1)."""
  handlers: dict[str, Any] = {
    "goal_create": _h_goal_create,
    "goal_get": _h_goal_get,
    "goal_edit": _h_goal_edit,
    "goal_pause": _h_goal_pause,
    "goal_resume": _h_goal_resume,
    "goal_complete": _h_goal_complete,
    "goal_block": _h_goal_block,
    "plan_generate": _h_plan_generate,
    "plan_update": _h_plan_update,
    "plan_activate": _h_plan_activate,
    "plan_step_status": _h_plan_step_status,
    "plan_complete": _h_plan_complete,
    "todo_write": _h_todo_write,
    "todo_clear": _h_todo_clear,
    "todo_get": _h_todo_get,
    "subagent_start": _h_subagent_start,
    "subagent_start_many": _h_subagent_start_many,
    "subagent_query": _h_subagent_query,
    "subagent_cancel": _h_subagent_cancel,
    "subagent_report": _h_subagent_report,
    "lsp": _h_lsp,
    "run_python_code": _h_run_python_code,
    "workflow_advance": _h_workflow_advance,
    "schedule_create": _h_schedule_create,
    "schedule_list": _h_schedule_list,
    "schedule_delete": _h_schedule_delete,
  }
  # G6: register agent-level at/cron/every/list/cancel tools (isolated from
  # the Web/platform scheduler above). Each closure drives its own in-memory
  # scheduler instance; failures surface as stable SCHEDULE_INVALID codes.
  try:
    from ai.tools.domains.agent_scheduler import register_agent_scheduler_tools
    register_agent_scheduler_tools(handlers)
  except Exception:
    pass
  return handlers


def register_harness_handlers(handlers, *, params=None, get_state_reader=None, toolbox=None) -> None:
  """Deprecated in-place variant; use :func:`make_harness_handlers`.

  Kept as a thin adapter so existing callers (e.g. ``agent_tools.make_handlers``)
  keep working during the migration to the return-dict style.
  """
  handlers.update(
    make_harness_handlers(
      params=params,
      get_state_reader=get_state_reader,
      toolbox=toolbox,
    )
  )
