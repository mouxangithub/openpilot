"""Platform extensions — sessions, MCP, learned skills, user profile, toolsets."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

from openpilot.common.params import Params

from ai.mcp.host import call_mcp_tool, discover_mcp_tools, get_mcp_prompt, list_mcp_servers, read_mcp_resource, upsert_mcp_server
from ai.tools.domains.platform.session_index import (
  get_session_history,
  list_sessions_brief,
  rebuild_from_params,
  search_sessions,
)
from ai.tools.domains.platform.skill_learning import approve_learned_skill, list_learned_skills, propose_learned_skill
from ai.tools.domains.platform.skill_evolution import analyze_execution_traces, evolution_status, evolve_skill_proposal
from ai.tools.domains.platform.platform_backup import (
  backup_manifest,
  build_platform_bundle,
  export_platform_bundle,
  restore_platform_bundle,
)
from ai.tools.domains.platform.workspace_enrich import (
  bootstrap_workspace_templates,
  enrichment_prompt_block,
  update_workspace_file as enrich_update_workspace,
  workspace_health,
)
from ai.tools.domains.platform.scheduler import (
  cancel_scheduled_task,
  list_scheduled_tasks,
  schedule_task,
)
from ai.tools.toolsets import list_toolsets
from ai.tools.domains.core.daily_memory import (
  append_daily_memory,
  list_daily_memory_files,
  read_daily_memory,
  read_recent_daily_memories,
)
from ai.common.memory_backend import append_unified_memory
from ai.tools.domains.platform.audit_cover import wrap_with_audit
from ai.tools.domains.devops.github_actions_tools import trigger_github_workflow
from ai.core.wspace.store import read_workspace_file, write_workspace_file

PLATFORM_TOOL_META: dict[str, dict[str, Any]] = {
  "sessions_list": {"label": "会话列表", "group": "read", "default_enabled": True, "driving": True},
  "sessions_history": {"label": "会话历史", "group": "read", "default_enabled": True, "driving": True},
  "sessions_send": {"label": "跨会话投递", "group": "write", "default_enabled": True, "driving": True},
  "search_past_conversations": {"label": "搜索历史对话", "group": "read", "default_enabled": True, "driving": True},
  "reindex_session_search": {"label": "重建会话索引", "group": "config", "default_enabled": True, "driving": True},
  "list_toolsets": {"label": "工具集列表", "group": "read", "default_enabled": True, "driving": True},
  "list_mcp_servers": {"label": "MCP 服务列表", "group": "read", "default_enabled": True, "driving": True},
  "manage_mcp_server": {"label": "管理 MCP 服务", "group": "config", "default_enabled": True, "driving": True},
  "call_mcp_tool": {"label": "调用 MCP 工具", "group": "read", "default_enabled": True, "driving": True},
  "read_mcp_resource": {"label": "读取 MCP resource", "group": "read", "default_enabled": True, "driving": True},
  "get_mcp_prompt": {"label": "获取 MCP prompt", "group": "read", "default_enabled": True, "driving": True},
  "discover_mcp_tools": {"label": "发现 MCP 工具", "group": "read", "default_enabled": True, "driving": True},
  "list_learned_skills": {"label": "已学技能列表", "group": "read", "default_enabled": True, "driving": True},
  "propose_learned_skill": {"label": "提议新技能", "group": "memory", "default_enabled": True, "driving": True},
  "approve_learned_skill": {"label": "批准技能", "group": "config", "default_enabled": True, "driving": True},
  "get_user_profile": {"label": "用户画像", "group": "read", "default_enabled": True, "driving": True},
  "update_user_profile": {"label": "更新用户画像", "group": "memory", "default_enabled": True, "driving": True},
  "update_workspace_file": {"label": "更新工作区文件", "group": "memory", "default_enabled": True, "driving": True},
  "workspace_health": {"label": "工作区健康检查", "group": "read", "default_enabled": True, "driving": True},
  "bootstrap_workspace": {"label": "初始化工作区模板", "group": "config", "default_enabled": True, "driving": True},
  "append_daily_memory": {"label": "写入当日记忆", "group": "memory", "default_enabled": True, "driving": True},
  "read_daily_memory": {"label": "读取当日记忆", "group": "read", "default_enabled": True, "driving": True},
  "list_daily_memory": {"label": "列出每日记忆文件", "group": "read", "default_enabled": True, "driving": True},
  "append_unified_memory": {"label": "统一写入记忆", "group": "memory", "default_enabled": True, "driving": True},
  "schedule_task": {"label": "创建定时任务", "group": "config", "default_enabled": True, "driving": True},
  "list_scheduled_tasks": {"label": "列出定时任务", "group": "read", "default_enabled": True, "driving": True},
  "cancel_scheduled_task": {"label": "取消定时任务", "group": "config", "default_enabled": True, "driving": True},
  "finish_session": {"label": "结束并总结会话", "group": "memory", "default_enabled": True, "driving": True},
  "run_ci_workflow": {"label": "触发 CI 工作流", "group": "config", "default_enabled": True, "driving": True},
  "export_platform_backup": {"label": "导出平台备份", "group": "config", "default_enabled": True, "driving": True},
  "restore_platform_backup": {"label": "恢复平台备份", "group": "config", "default_enabled": True, "driving": True},
  "analyze_execution_traces": {"label": "分析执行轨迹", "group": "read", "default_enabled": True, "driving": True},
  "evolve_skill_proposal": {"label": "进化技能提案", "group": "memory", "default_enabled": True, "driving": True},
  "load_skill": {"label": "按需加载技能", "group": "read", "default_enabled": True, "driving": True},
  "run_evolution_pipeline": {"label": "运行进化管线", "group": "config", "default_enabled": True, "driving": True},
  "run_gepa_evolution": {"label": "GEPA 技能进化", "group": "config", "default_enabled": True, "driving": True},
  "run_workflow": {"label": "运行 WorkflowEngine workflow", "group": "config", "default_enabled": True, "driving": True},
  "list_tool_desc_overrides": {"label": "工具描述覆盖", "group": "read", "default_enabled": True, "driving": True},
}

PLATFORM_SCHEMAS: list[dict[str, Any]] = [
  {"type": "function", "function": {"name": "sessions_list", "description": "List recent chat sessions with id, title, message count.", "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}, "required": []}}},
  {"type": "function", "function": {"name": "sessions_history", "description": "Read message history for a session id.", "parameters": {"type": "object", "properties": {"session_id": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["session_id"]}}},
  {"type": "function", "function": {"name": "sessions_send", "description": "Append a note to another session as assistant context (stored in memory + notification).", "parameters": {"type": "object", "properties": {"session_id": {"type": "string"}, "message": {"type": "string"}}, "required": ["session_id", "message"]}}},
  {"type": "function", "function": {"name": "search_past_conversations", "description": "Full-text search across past chat sessions.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"]}}},
  {"type": "function", "function": {"name": "reindex_session_search", "description": "Rebuild FTS index from device session store.", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "list_toolsets", "description": "List available toolset groups (driving_readonly, offroad_full, etc.).", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "list_mcp_servers", "description": "List configured MCP server bridges.", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "manage_mcp_server", "description": "Add or update an MCP stdio server config.", "parameters": {"type": "object", "properties": {"id": {"type": "string"}, "name": {"type": "string"}, "command": {"type": "string"}, "args": {"type": "array", "items": {"type": "string"}}, "enabled": {"type": "boolean"}}, "required": ["id", "command"]}}},
  {"type": "function", "function": {"name": "discover_mcp_tools", "description": "Call MCP tools/list for a server and cache tool names.", "parameters": {"type": "object", "properties": {"server_id": {"type": "string"}}, "required": ["server_id"]}}},
  {"type": "function", "function": {"name": "call_mcp_tool", "description": "Invoke a tool on a configured MCP server.", "parameters": {"type": "object", "properties": {"server_id": {"type": "string"}, "tool_name": {"type": "string"}, "arguments": {"type": "object"}}, "required": ["server_id", "tool_name"]}}},
  {"type": "function", "function": {"name": "read_mcp_resource", "description": "Read a resource from a configured MCP server.", "parameters": {"type": "object", "properties": {"server_id": {"type": "string"}, "uri": {"type": "string"}}, "required": ["server_id", "uri"]}}},
  {"type": "function", "function": {"name": "get_mcp_prompt", "description": "Get a prompt template from a configured MCP server.", "parameters": {"type": "object", "properties": {"server_id": {"type": "string"}, "name": {"type": "string"}, "arguments": {"type": "object"}}, "required": ["server_id", "name"]}}},
  {"type": "function", "function": {"name": "list_learned_skills", "description": "List agent-proposed learned skills.", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "propose_learned_skill", "description": "Save a reusable skill draft from a completed workflow.", "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "body": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}}, "required": ["title", "body"]}}},
  {"type": "function", "function": {"name": "approve_learned_skill", "description": "Approve a pending learned skill for future prompts.", "parameters": {"type": "object", "properties": {"skill_id": {"type": "string"}}, "required": ["skill_id"]}}},
  {"type": "function", "function": {"name": "get_user_profile", "description": "Read USER.md profile and vehicle profile.", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "update_user_profile", "description": "Update USER.md preferences text.", "parameters": {"type": "object", "properties": {"content": {"type": "string"}, "append": {"type": "boolean"}}, "required": ["content"]}}},
  {"type": "function", "function": {"name": "update_workspace_file", "description": "Update any workspace markdown (user/memory/soul/agents/tools/heartbeat). Use when enriching sparse workspace files.", "parameters": {"type": "object", "properties": {"key": {"type": "string"}, "content": {"type": "string"}, "append": {"type": "boolean"}, "merge_section": {"type": "string"}}, "required": ["key", "content"]}}},
  {"type": "function", "function": {"name": "workspace_health", "description": "Check which workspace files are sparse and need AI enrichment.", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "bootstrap_workspace", "description": "Write structured templates for empty/sparse workspace files.", "parameters": {"type": "object", "properties": {"force": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "append_daily_memory", "description": "Append bullets to today's daily log (workspace/memory/YYYY-MM-DD.md). Use for session events per memory-protocol.", "parameters": {"type": "object", "properties": {"bullets": {"type": "array", "items": {"type": "string"}}, "title": {"type": "string"}}, "required": ["bullets"]}}},
  {"type": "function", "function": {"name": "read_daily_memory", "description": "Read daily memory markdown for a date (default today).", "parameters": {"type": "object", "properties": {"date": {"type": "string", "description": "YYYY-MM-DD"}}, "required": []}}},
  {"type": "function", "function": {"name": "list_daily_memory", "description": "List recent daily memory journal files.", "parameters": {"type": "object", "properties": {"days": {"type": "integer"}}, "required": []}}},
  {"type": "function", "function": {"name": "append_unified_memory", "description": "Persist an observation to both short-term notes and long-term daily memory.", "parameters": {"type": "object", "properties": {"text": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}, "session_id": {"type": "string"}, "title": {"type": "string"}}, "required": ["text"]}}},
  {"type": "function", "function": {"name": "schedule_task", "description": "Create or update a scheduled task. Trigger can be interval, on_offroad, on_ignition, on_wifi, daily_at, or rrule (with payload.rrule).", "parameters": {"type": "object", "properties": {"task_id": {"type": "string"}, "name": {"type": "string"}, "action": {"type": "string"}, "trigger": {"type": "string"}, "interval_minutes": {"type": "integer"}, "payload": {"type": "object"}, "enabled": {"type": "boolean"}}, "required": ["name", "action"]}}},
  {"type": "function", "function": {"name": "list_scheduled_tasks", "description": "List scheduled tasks with next run and last result.", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "cancel_scheduled_task", "description": "Cancel a scheduled task by id.", "parameters": {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]}}},
  {"type": "function", "function": {"name": "finish_session", "description": "Summarize a session and persist key takeaways to unified memory.", "parameters": {"type": "object", "properties": {"session_id": {"type": "string"}, "title": {"type": "string"}, "evolve": {"type": "boolean"}}, "required": ["session_id"]}}},
  {"type": "function", "function": {"name": "run_ci_workflow", "description": "Trigger a GitHub Actions workflow dispatch. Set confirm=true to actually dispatch.", "parameters": {"type": "object", "properties": {"repo_url": {"type": "string"}, "workflow": {"type": "string"}, "ref": {"type": "string"}, "confirm": {"type": "boolean"}}, "required": ["workflow"]}}},
  {"type": "function", "function": {"name": "export_platform_backup", "description": "Export memory, sessions, skills, MCP, workspace to a JSON backup file.", "parameters": {"type": "object", "properties": {"include_secrets": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "restore_platform_backup", "description": "Restore platform state from backup bundle (confirm required).", "parameters": {"type": "object", "properties": {"bundle": {"type": "object"}, "mode": {"type": "string", "enum": ["merge", "replace"]}, "sections": {"type": "array", "items": {"type": "string"}}, "confirm": {"type": "boolean"}}, "required": ["bundle"]}}},
  {"type": "function", "function": {"name": "analyze_execution_traces", "description": "Mine recent sessions for failures and corrections (Hermes-style trace collection).", "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}, "required": []}}},
  {"type": "function", "function": {"name": "evolve_skill_proposal", "description": "Draft an improved learned skill from execution traces with LLM reflection and Pareto selection.", "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "trace_session_id": {"type": "string"}, "focus": {"type": "string"}, "body": {"type": "string"}, "use_llm": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "load_skill", "description": "Progressive disclosure: load full SKILL.md body for a skill id from registry.", "parameters": {"type": "object", "properties": {"skill_id": {"type": "string"}}, "required": ["skill_id"]}}},
  {"type": "function", "function": {"name": "run_evolution_pipeline", "description": "Run built-in Hermes evolution pipeline.", "parameters": {"type": "object", "properties": {"session_id": {"type": "string"}, "focus": {"type": "string"}}, "required": []}}},
  {"type": "function", "function": {"name": "run_gepa_evolution", "description": "Run built-in Hermes GEPA skill evolution (eval dataset + reflective mutate + constraints). Requires approval.", "parameters": {"type": "object", "properties": {"skill_id": {"type": "string"}, "eval_source": {"type": "string", "enum": ["sessiondb", "synthetic", "golden", "trace"]}, "focus": {"type": "string"}, "iterations": {"type": "integer"}}, "required": ["skill_id"]}}},
  {"type": "function", "function": {"name": "run_workflow", "description": "Run a WorkflowEngine definition by id or inline definition.", "parameters": {"type": "object", "properties": {"workflow_id": {"type": "string"}, "definition": {"type": "object"}, "inputs": {"type": "object"}}, "required": []}}},
  {"type": "function", "function": {"name": "list_tool_desc_overrides", "description": "List evolved tool description overrides applied to tool schemas.", "parameters": {"type": "object", "properties": {}, "required": []}}},
]


def make_platform_handlers(
  *,
  params: Params,
  stationary_check=None,
  needs_confirm=None,
) -> dict[str, Callable[..., Any]]:
  p = params

  def _confirm(kind: str, args: dict[str, Any], hint: str = "Set confirm=true to proceed.") -> dict[str, Any] | None:
    """Return a needs_confirmation response if confirm gate is required, else None."""
    if needs_confirm is None:
      return None
    if args.get("confirm") is False or str(args.get("confirm", "")).lower() in ("0", "false", "no"):
      if needs_confirm():
        return {"ok": True, "needs_confirmation": True, "hint": hint}
    return None

  def _stationary(kind: str) -> dict[str, Any] | None:
    """Return a stationary-required error if the write guard blocks, else None."""
    if stationary_check is None:
      return None
    return stationary_check(kind)

  def h_sessions_list(args: dict[str, Any]) -> dict[str, Any]:
    return list_sessions_brief(p, limit=int(args.get("limit") or 20))

  def h_sessions_history(args: dict[str, Any]) -> dict[str, Any]:
    return get_session_history(p, str(args.get("session_id") or ""), limit=int(args.get("limit") or 40))

  def h_sessions_send(args: dict[str, Any]) -> dict[str, Any]:
    sid = str(args.get("session_id") or "")
    msg = str(args.get("message") or "").strip()
    if not sid or not msg:
      return {"ok": False, "error": "session_id and message required"}
    guard = _confirm("sessions_send", args)
    if guard:
      return guard
    append_note(p, f"[会话 {sid[:8]}] {msg}", tags=["sessions_send", f"session:{sid[:12]}"])
    try:
      from ai.tools.domains.platform.notifications import push_notification
      push_notification("跨会话消息", msg[:200], level="info")
    except Exception:
      pass
    return {"ok": True, "sessionId": sid, "delivered": "memory+notification"}

  def h_search_past(args: dict[str, Any]) -> dict[str, Any]:
    return search_sessions(str(args.get("query") or ""), limit=int(args.get("limit") or 8))

  def h_reindex_sessions(_a: dict[str, Any]) -> dict[str, Any]:
    return rebuild_from_params(p)

  def h_list_toolsets(_a: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "toolsets": list_toolsets()}

  def h_list_mcp(_a: dict[str, Any]) -> dict[str, Any]:
    return list_mcp_servers(p)

  def h_manage_mcp(args: dict[str, Any]) -> dict[str, Any]:
    return upsert_mcp_server(p, args)

  async def h_discover_mcp(args: dict[str, Any]) -> dict[str, Any]:
    return await discover_mcp_tools(p, str(args.get("server_id") or ""))

  async def h_call_mcp(args: dict[str, Any]) -> dict[str, Any]:
    return await call_mcp_tool(
      p,
      server_id=str(args.get("server_id") or ""),
      tool_name=str(args.get("tool_name") or ""),
      arguments=args.get("arguments") if isinstance(args.get("arguments"), dict) else {},
    )

  async def h_read_mcp_resource(args: dict[str, Any]) -> dict[str, Any]:
    return await read_mcp_resource(
      p,
      server_id=str(args.get("server_id") or ""),
      uri=str(args.get("uri") or ""),
      session_id=str(args.get("session_id") or args.get("sessionId") or ""),
    )

  async def h_get_mcp_prompt(args: dict[str, Any]) -> dict[str, Any]:
    return await get_mcp_prompt(
      p,
      server_id=str(args.get("server_id") or ""),
      name=str(args.get("name") or ""),
      arguments=args.get("arguments") if isinstance(args.get("arguments"), dict) else {},
      session_id=str(args.get("session_id") or args.get("sessionId") or ""),
    )

  def h_list_learned(_a: dict[str, Any]) -> dict[str, Any]:
    return list_learned_skills(p)

  def h_propose_learned(args: dict[str, Any]) -> dict[str, Any]:
    return propose_learned_skill(
      p,
      title=str(args.get("title") or ""),
      body=str(args.get("body") or ""),
      tags=args.get("tags"),
    )

  def h_approve_learned(args: dict[str, Any]) -> dict[str, Any]:
    stationary = _stationary("approve_learned_skill")
    if stationary:
      return stationary
    return approve_learned_skill(p, str(args.get("skill_id") or ""))

  def h_get_user_profile(_a: dict[str, Any]) -> dict[str, Any]:
    mem = get_memory(p)
    return {
      "ok": True,
      "userMd": read_workspace_file("user"),
      "vehicleProfile": mem.get("vehicle_profile") or {},
      "notesCount": len(mem.get("notes") or []),
    }

  def h_update_user_profile(args: dict[str, Any]) -> dict[str, Any]:
    content = str(args.get("content") or "").strip()
    if not content:
      return {"ok": False, "error": "content required"}
    guard = _confirm("update_user_profile", args)
    if guard:
      return guard
    if args.get("append"):
      prev = read_workspace_file("user")
      content = (prev + "\n\n" + content).strip() if prev else content
    write_workspace_file("user", content)
    return {"ok": True, "chars": len(content)}

  def h_update_workspace(args: dict[str, Any]) -> dict[str, Any]:
    guard = _confirm("update_workspace_file", args)
    if guard:
      return guard
    return enrich_update_workspace(
      p,
      key=str(args.get("key") or ""),
      content=str(args.get("content") or ""),
      append=bool(args.get("append")),
      merge_section=str(args.get("merge_section") or ""),
    )

  def h_workspace_health(_a: dict[str, Any]) -> dict[str, Any]:
    return workspace_health()

  def h_bootstrap_workspace(args: dict[str, Any]) -> dict[str, Any]:
    return bootstrap_workspace_templates(force=bool(args.get("force")))

  def h_append_daily_memory(args: dict[str, Any]) -> dict[str, Any]:
    bullets = args.get("bullets") or []
    if isinstance(bullets, str):
      bullets = [bullets]
    return append_daily_memory(
      bullets=bullets,
      session_id=str(args.get("session_id") or ""),
      title=str(args.get("title") or ""),
    )

  def h_read_daily_memory(args: dict[str, Any]) -> dict[str, Any]:
    from ai.tools.domains.core.daily_memory import read_daily_index, refresh_daily_index
    from datetime import date as date_cls
    raw = str(args.get("date") or "").strip()
    day = None
    if raw:
      try:
        day = date_cls.fromisoformat(raw)
      except ValueError:
        return {"ok": False, "error": "date must be YYYY-MM-DD"}
    refresh_daily_index()
    content = read_daily_memory(day)
    return {
      "ok": True,
      "date": raw or "today",
      "content": content,
      "index": read_daily_index(),
      "files": list_daily_memory_files(days=int(args.get("days") or 14)),
    }

  def h_list_daily_memory(args: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "files": list_daily_memory_files(days=int(args.get("days") or 14))}

  def h_append_unified_memory(args: dict[str, Any]) -> dict[str, Any]:
    text = str(args.get("text") or "").strip()
    if not text:
      return {"ok": False, "error": "text required"}
    return append_unified_memory(
      text,
      params=p,
      tags=args.get("tags") if isinstance(args.get("tags"), list) else [],
      session_id=str(args.get("session_id") or ""),
      title=str(args.get("title") or ""),
    )

  def h_schedule_task(args: dict[str, Any]) -> dict[str, Any]:
    spec = {
      "task_id": args.get("task_id") or args.get("id"),
      "name": args.get("name"),
      "action": args.get("action"),
      "trigger": args.get("trigger", "interval"),
      "interval_minutes": args.get("interval_minutes"),
      "payload": args.get("payload") if isinstance(args.get("payload"), dict) else {},
      "enabled": bool(args.get("enabled", True)),
    }
    spec = {k: v for k, v in spec.items() if v is not None}
    return schedule_task(p, spec)

  def h_list_scheduled_tasks(_a: dict[str, Any]) -> dict[str, Any]:
    return list_scheduled_tasks(p)

  def h_cancel_scheduled_task(args: dict[str, Any]) -> dict[str, Any]:
    return cancel_scheduled_task(p, str(args.get("task_id") or ""))

  def h_finish_session(args: dict[str, Any]) -> dict[str, Any]:
    session_id = str(args.get("session_id") or "").strip()
    if not session_id:
      return {"ok": False, "error": "session_id required"}
    history = get_session_history(p, session_id, limit=40)
    if not history.get("ok"):
      return history
    messages = history.get("messages") or []
    summary = " ".join(
      [f"{m.get('role', '?')}:{str(m.get('content', ''))[:80]}" for m in messages[-6:]]
    )
    title = str(args.get("title") or f"session summary {session_id[:8]}").strip()
    memory = append_unified_memory(
      f"Session {session_id[:8]} summary: {summary}",
      params=p,
      tags=["session_summary", f"session:{session_id[:12]}"],
      session_id=session_id,
      title=title,
    )
    traces = analyze_execution_traces(p, limit=8) if args.get("evolve") else {"ok": True, "traces": []}
    return {
      "ok": True,
      "sessionId": session_id,
      "messages": len(messages),
      "memory": memory,
      "traces": traces.get("traces") or [],
    }

  def h_run_ci_workflow(args: dict[str, Any]) -> dict[str, Any]:
    return trigger_github_workflow(
      repo_url=str(args.get("repo_url") or ""),
      workflow=str(args.get("workflow") or ""),
      ref=str(args.get("ref") or "master-c3"),
      confirm=bool(args.get("confirm")),
      params=p,
    )

  def h_export_backup(args: dict[str, Any]) -> dict[str, Any]:
    return export_platform_bundle(p, include_secrets=bool(args.get("include_secrets")))

  def h_restore_backup(args: dict[str, Any]) -> dict[str, Any]:
    bundle = args.get("bundle")
    if not isinstance(bundle, dict):
      return {"ok": False, "error": "bundle object required"}
    stationary = _stationary("restore_platform_backup")
    if stationary:
      return stationary
    guard = _confirm("restore_platform_backup", args)
    if guard:
      return guard
    return restore_platform_bundle(
      p,
      bundle,
      mode=str(args.get("mode") or "merge"),
      sections=args.get("sections") if isinstance(args.get("sections"), list) else None,
      confirm=bool(args.get("confirm")),
    )

  def h_analyze_traces(args: dict[str, Any]) -> dict[str, Any]:
    return analyze_execution_traces(p, limit=int(args.get("limit") or 8))

  async def h_evolve_skill(args: dict[str, Any]) -> dict[str, Any]:
    return await evolve_skill_proposal(
      p,
      title=str(args.get("title") or ""),
      trace_session_id=str(args.get("trace_session_id") or ""),
      focus=str(args.get("focus") or ""),
      body=str(args.get("body") or ""),
      use_llm=bool(args.get("use_llm", True)),
    )

  def h_load_skill(args: dict[str, Any]) -> dict[str, Any]:
    from ai.skills.loader import load_skill_body_by_id
    return load_skill_body_by_id(str(args.get("skill_id") or ""))

  async def h_run_gepa_evolution(args: dict[str, Any]) -> dict[str, Any]:
    from ai.evolution.config import EvolutionRunConfig
    from ai.evolution.gepa_engine import evolve_skill_gepa
    from ai.tools.domains.platform.skill_evolution import analyze_execution_traces
    skill_id = str(args.get("skill_id") or args.get("skillId") or "memory-protocol")
    run = EvolutionRunConfig.from_params(
      skill_id=skill_id,
      focus=str(args.get("focus") or ""),
      eval_source=str(args.get("eval_source") or "sessiondb"),
    )
    if args.get("iterations"):
      run.iterations = int(args["iterations"])
    traces = analyze_execution_traces(p, limit=12)
    return await evolve_skill_gepa(p, skill_id=skill_id, run=run, traces=traces.get("traces") or [])

  async def h_run_evolution_pipeline(args: dict[str, Any]) -> dict[str, Any]:
    from ai.core.runtime.evolution_pipeline import run_evolution_pipeline_manual
    return await run_evolution_pipeline_manual(
      p,
      session_id=str(args.get("session_id") or ""),
      focus=str(args.get("focus") or ""),
    )

  def h_list_tool_desc(_a: dict[str, Any]) -> dict[str, Any]:
    from ai.tools.domains.platform.tool_desc_store import list_tool_desc_overrides
    return list_tool_desc_overrides(p)

  async def h_run_workflow(args: dict[str, Any]) -> dict[str, Any]:
    import asyncio
    from ai.core.workflow import WorkflowEngine
    definition = args.get("definition") or {}
    if not isinstance(definition, dict) or not definition.get("id"):
      stored = _workflow_engine_definitions().get(str(args.get("workflow_id") or ""))
      if stored is None:
        return {"ok": False, "error": "workflow definition or workflow_id required"}
      definition = stored
    stationary = _stationary("run_workflow")
    if stationary:
      return stationary
    engine = WorkflowEngine()
    cancel_event = asyncio.Event()
    # T-P0.5: stable adapter — build the handler map once per run instead of
    # rebuilding make_handlers() on every TOOL step.
    # T-P1.6: share the cancel_event so engine.cancel()/dispose() can abort
    # slow tool calls cooperatively.
    try:
      from ai.core.workflow.tool_adapter import WorkflowToolAdapter
      from ai.tools.agent_tools import make_handlers
      adapter = WorkflowToolAdapter.from_factory(
        lambda: make_handlers(params=p, get_state_reader=_workflow_state_reader),
        cancel_event=cancel_event,
      )
      engine.set_tool_runner(adapter.run)
    except Exception:
      engine.set_tool_runner(lambda name, a: _dispatch_workflow_tool(name, a, p))
    result = await engine.run(definition, dict(args.get("inputs") or {}), cancel_event=cancel_event)
    if result.ok:
      from ai.core.errors import ok_result
      return ok_result(output=result.output, workflow_error=result.error.value, logs=result.logs[-20:])
    from ai.core.errors import ERR_DEPENDENCY_UNAVAILABLE, tool_error
    return tool_error(
      result.message or "workflow failed",
      code=ERR_DEPENDENCY_UNAVAILABLE,
      details={"workflow_error": result.error.value, "logs": result.logs[-20:]},
    )

  return {
    "sessions_list": h_sessions_list,
    "sessions_history": h_sessions_history,
    "sessions_send": h_sessions_send,
    "search_past_conversations": h_search_past,
    "reindex_session_search": h_reindex_sessions,
    "list_toolsets": h_list_toolsets,
    "list_mcp_servers": h_list_mcp,
    "manage_mcp_server": h_manage_mcp,
    "discover_mcp_tools": h_discover_mcp,
    "call_mcp_tool": h_call_mcp,
    "read_mcp_resource": h_read_mcp_resource,
    "get_mcp_prompt": h_get_mcp_prompt,
    "list_learned_skills": h_list_learned,
    "propose_learned_skill": h_propose_learned,
    "approve_learned_skill": h_approve_learned,
    "get_user_profile": h_get_user_profile,
    "update_user_profile": h_update_user_profile,
    "update_workspace_file": h_update_workspace,
    "workspace_health": h_workspace_health,
    "bootstrap_workspace": h_bootstrap_workspace,
    "append_daily_memory": h_append_daily_memory,
    "read_daily_memory": h_read_daily_memory,
    "list_daily_memory": h_list_daily_memory,
    "append_unified_memory": h_append_unified_memory,
    "schedule_task": h_schedule_task,
    "list_scheduled_tasks": h_list_scheduled_tasks,
    "cancel_scheduled_task": h_cancel_scheduled_task,
    "finish_session": h_finish_session,
    "run_ci_workflow": h_run_ci_workflow,
    "export_platform_backup": h_export_backup,
    "restore_platform_backup": h_restore_backup,
    "analyze_execution_traces": h_analyze_traces,
    "evolve_skill_proposal": h_evolve_skill,
    "load_skill": h_load_skill,
    "run_evolution_pipeline": h_run_evolution_pipeline,
    "run_gepa_evolution": h_run_gepa_evolution,
    "run_workflow": h_run_workflow,
    "list_tool_desc_overrides": h_list_tool_desc,
  }
  return wrap_with_audit(handlers)


def _workflow_engine_definitions() -> dict[str, dict[str, Any]]:
  """Return a small in-memory registry of WorkflowEngine definitions.

  Currently loads from workspace ``workflows/engine_definitions.json`` if
  present; otherwise returns an empty dict so callers can pass ``definition``
  directly to the ``run_workflow`` tool.
  """
  from ai.system.paths import workspace_path
  from pathlib import Path
  path = workspace_path("workflows", mkdir=True) / "engine_definitions.json"
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
      return {k: v for k, v in data.items() if isinstance(v, dict)}
  except Exception:
    pass
  return {}


async def _dispatch_workflow_tool(name: str, args: dict[str, Any], params: Params) -> dict[str, Any]:
  """Dispatch a tool call from within a WorkflowEngine TOOL step."""
  from ai.tools.agent_tools import make_handlers
  handlers = make_handlers(get_state_reader=_workflow_state_reader)
  handler = handlers.get(name)
  if handler is None:
    return {"ok": False, "error": f"tool '{name}' not found"}
  if asyncio.iscoroutinefunction(handler):
    return await handler(args)
  return handler(args)


def _workflow_state_reader():
  """Minimal state-reader shim for make_handlers inside workflow runs."""
  from types import SimpleNamespace
  return SimpleNamespace(update=lambda timeout=0: SimpleNamespace(is_driving=False))
