"""Deferred tool loading — WorkBuddy-style ToolSearch + load_tool."""

from __future__ import annotations

import re
from typing import Any

from ai.common.storage import read_param_bool

_META_TOOLS = frozenset({"search_tools", "load_tool"})

# High-frequency tools always exposed without load_tool.
_CORE_TOOLS = frozenset({
  "search_tools",
  "load_tool",
  "get_vehicle_state",
  "get_full_vehicle_state",
  "read_params",
  "list_sp_settings",
  "search_knowledge_base",
  "list_knowledge_docs",
  "get_agent_memory",
  "grep_log",
  "read_manager_log",
  "read_onroad_events",
  "run_shell_command",
  "read_file",
  "list_directory",
  "trip_review",
  "list_drive_routes",
  "diff_params",
  "snapshot_tune_state",
})

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)

# session_key -> loaded tool names (beyond core/meta)
_loaded_by_session: dict[str, set[str]] = {}
# session_key -> full catalog {name: schema}
_catalog_by_session: dict[str, dict[str, dict[str, Any]]] = {}


def deferred_loading_enabled(params: Any = None) -> bool:
  return read_param_bool(params, "ai_deferred_tools", True)


def session_key(session_id: str = "", job_id: str = "") -> str:
  sid = (session_id or job_id or "").strip()
  return sid or "__default__"


def reset_session(key: str) -> None:
  _loaded_by_session.pop(key, None)
  _catalog_by_session.pop(key, None)


def set_session_catalog(
  key: str,
  tools: list[dict[str, Any]] | None,
) -> None:
  if not tools:
    _catalog_by_session.pop(key, None)
    return
  catalog: dict[str, dict[str, Any]] = {}
  for tool in tools:
    fn = tool.get("function") or {}
    name = str(fn.get("name") or "").strip()
    if name:
      catalog[name] = tool
  _catalog_by_session[key] = catalog
  _loaded_by_session.setdefault(key, set())


def get_loaded_tools(key: str) -> set[str]:
  return _loaded_by_session.setdefault(key, set())


def mark_tools_loaded(key: str, names: list[str]) -> list[str]:
  loaded = get_loaded_tools(key)
  catalog = _catalog_by_session.get(key) or {}
  added: list[str] = []
  for raw in names:
    name = str(raw or "").strip()
    if not name or name in _META_TOOLS:
      continue
    if name not in catalog:
      continue
    if name not in loaded:
      loaded.add(name)
      added.append(name)
  return added


def meta_tool_schemas() -> list[dict[str, Any]]:
  return [
    {
      "type": "function",
      "function": {
        "name": "search_tools",
        "description": (
          "Search the tool catalog by keyword. Returns name + short description. "
          "Call load_tool to activate tools before use."
        ),
        "parameters": {
          "type": "object",
          "properties": {
            "query": {"type": "string", "description": "Keywords describing the capability needed"},
            "limit": {"type": "integer", "description": "Max results (default 15, max 30)"},
          },
          "required": ["query"],
        },
      },
    },
    {
      "type": "function",
      "function": {
        "name": "load_tool",
        "description": (
          "Activate one or more tools for this session so they appear in your tool list. "
          "Always load before calling specialized tools."
        ),
        "parameters": {
          "type": "object",
          "properties": {
            "tools": {
              "type": "array",
              "items": {"type": "string"},
              "description": "Exact tool names from search_tools",
            },
          },
          "required": ["tools"],
        },
      },
    },
  ]


def _tokens(text: str) -> set[str]:
  return {t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 1}


def search_tools_in_catalog(
  catalog: dict[str, dict[str, Any]],
  *,
  query: str,
  limit: int = 15,
) -> list[dict[str, str]]:
  q_tokens = _tokens(query)
  limit = max(1, min(int(limit or 15), 30))
  scored: list[tuple[float, str, str]] = []
  for name, schema in catalog.items():
    if name in _META_TOOLS:
      continue
    fn = schema.get("function") or {}
    desc = str(fn.get("description") or "")
    hay = _tokens(f"{name} {desc}".replace("_", " "))
    score = 0.0
    if q_tokens:
      overlap = len(q_tokens & hay)
      score += overlap * 10.0
      for qt in q_tokens:
        if qt in name.replace("_", ""):
          score += 6.0
    else:
      score = 1.0
    if score > 0:
      scored.append((score, name, desc[:160]))
  scored.sort(key=lambda x: (-x[0], x[1]))
  return [{"name": n, "description": d} for _, n, d in scored[:limit]]


def apply_deferred_filter(
  tools: list[dict[str, Any]] | None,
  key: str,
  params: Any = None,
) -> list[dict[str, Any]] | None:
  """Return reduced tool list: meta + core + session-loaded tools."""
  if not tools:
    return tools
  if not deferred_loading_enabled(params):
    return tools

  catalog = {t["function"]["name"]: t for t in tools if t.get("function", {}).get("name")}
  set_session_catalog(key, tools)
  loaded = get_loaded_tools(key)

  keep: list[dict[str, Any]] = []
  seen: set[str] = set()
  for schema in meta_tool_schemas():
    name = schema["function"]["name"]
    if name not in seen:
      keep.append(schema)
      seen.add(name)

  for name in sorted(_CORE_TOOLS | loaded):
    if name in catalog and name not in seen:
      keep.append(catalog[name])
      seen.add(name)

  return keep or None


def resolve_active_tools(
  tools: list[dict[str, Any]] | None,
  key: str,
  params: Any = None,
) -> list[dict[str, Any]] | None:
  """Re-apply deferred filter each chat round (picks up newly loaded tools)."""
  return apply_deferred_filter(tools, key, params)


def handle_search_tools(args: dict[str, Any], *, session_id: str = "", job_id: str = "") -> dict[str, Any]:
  key = session_key(session_id, job_id)
  catalog = _catalog_by_session.get(key)
  if not catalog:
    return {"ok": False, "error": "Tool catalog not initialized for this session."}
  query = str(args.get("query") or "").strip()
  limit = int(args.get("limit") or 15)
  hits = search_tools_in_catalog(catalog, query=query, limit=limit)
  loaded = sorted(get_loaded_tools(key) | _CORE_TOOLS)
  return {
    "ok": True,
    "query": query,
    "count": len(hits),
    "tools": hits,
    "already_loaded": loaded,
    "hint": "Call load_tool with exact names before using specialized tools.",
  }


def handle_load_tool(args: dict[str, Any], *, session_id: str = "", job_id: str = "") -> dict[str, Any]:
  key = session_key(session_id, job_id)
  catalog = _catalog_by_session.get(key)
  if not catalog:
    return {"ok": False, "error": "Tool catalog not initialized for this session."}
  names = args.get("tools") or []
  if isinstance(names, str):
    names = [names]
  added = mark_tools_loaded(key, list(names))
  unknown = [str(n) for n in names if str(n).strip() and str(n).strip() not in catalog and str(n).strip() not in _META_TOOLS]
  return {
    "ok": True,
    "loaded": added,
    "already_loaded": sorted(get_loaded_tools(key)),
    "unknown": unknown,
    "active_count": len(resolve_active_tools(list(catalog.values()), key) or []),
  }
