"""Post-chat evolution pipeline — workspace, skills, tool descriptions."""

from __future__ import annotations

import json
import time
from typing import Any

from openpilot.common.params import Params

from ai.core.llm.client import AIConfig
from ai.server.deps import read_ai_config
from ai.common.evolution_config import (
  evolution_auto_propose,
  evolution_auto_memory,
  evolution_auto_workspace,
  evolution_candidate_count,
  evolution_enabled,
  evolution_llm_reflect,
  evolution_tool_desc,
)
from ai.common.storage import read_param, write_param

_PIPELINE_LOG_KEY = "ai_evolution_pipeline_log"
_MAX_LOG = 20


def _append_log(params: Params, entry: dict[str, Any]) -> None:
  try:
    raw = read_param(params, _PIPELINE_LOG_KEY)
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="replace")
    items = json.loads(raw) if raw else []
    if not isinstance(items, list):
      items = []
  except Exception:
    items = []
  items.insert(0, {**entry, "at": int(time.time())})
  write_param(params, _PIPELINE_LOG_KEY, json.dumps(items[:_MAX_LOG], ensure_ascii=False))


def pipeline_log(params: Params | None = None, *, limit: int = 10) -> dict[str, Any]:
  params = params or Params()
  try:
    raw = read_param(params, _PIPELINE_LOG_KEY)
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="replace")
    items = json.loads(raw) if raw else []
  except Exception:
    items = []
  return {"ok": True, "entries": items[:limit]}


async def run_post_chat_pipeline(
  params: Params,
  *,
  session_id: str = "",
  last_user_text: str = "",
  recent_messages: list[dict[str, Any]] | None = None,
  config: AIConfig | None = None,
) -> dict[str, Any]:
  """Hermes closed-loop: after each chat, enrich workspace + memory + skills/tools."""
  if not evolution_enabled():
    return {"ok": True, "skipped": True, "reason": "evolution disabled"}

  cfg = config or read_ai_config(params)
  result: dict[str, Any] = {"ok": True, "steps": []}

  from ai.tools.skill_evolution import analyze_execution_traces, evolve_skill_proposal

  if evolution_auto_workspace():
    from ai.tools.workspace_enrich import bootstrap_workspace_templates, workspace_health
    health = workspace_health()
    if health.get("needsEnrichment"):
      boot = bootstrap_workspace_templates(force=False)
      result["steps"].append({"workspace_bootstrap": boot.get("written", [])})

  if evolution_auto_memory() and recent_messages and evolution_llm_reflect() and cfg.is_configured:
    from ai.tools.memory_protocol import extract_and_persist_session_memory
    mem = await extract_and_persist_session_memory(
      params,
      recent_messages,
      config=cfg,
      session_id=session_id,
    )
    result["steps"].append({"memory_extract": mem})
    try:
      from ai.tools.daily_memory import prune_old_daily_files
      prune_old_daily_files(keep_days=30)
    except Exception:
      pass

  traces = analyze_execution_traces(params, limit=8)
  hotspots = traces.get("hotspots") or []
  result["hotspots"] = len(hotspots)

  if hotspots and evolution_auto_propose():
    evo = await evolve_skill_proposal(
      params,
      trace_session_id=str(hotspots[0].get("sessionId") or ""),
      use_llm=evolution_llm_reflect() and cfg.is_configured,
      config=cfg,
      candidate_count=evolution_candidate_count(),
    )
    result["steps"].append({"skill_evolution": evo})

  if hotspots and evolution_tool_desc() and cfg.is_configured:
    tool_step = await _maybe_evolve_tool_descriptions(params, hotspots[0], config=cfg)
    if tool_step:
      result["steps"].append({"tool_desc": tool_step})

  _append_log(params, {
    "sessionId": session_id,
    "userPreview": (last_user_text or "")[:120],
    "steps": result.get("steps"),
    "hotspots": result.get("hotspots"),
  })
  return result


async def _maybe_evolve_tool_descriptions(
  params: Params,
  hotspot: dict[str, Any],
  *,
  config: AIConfig,
) -> dict[str, Any] | None:
  from ai.tools.evolution_reflect import reflect_on_trace
  from ai.tools.tool_desc_store import propose_tool_desc_from_trace, set_tool_desc_override

  errors = hotspot.get("toolErrors") or []
  if not errors:
    return None
  first = str(errors[0])
  tool_name = ""
  if ":" in first:
    tool_name = first.split(":", 1)[0].strip()

  reflection = await reflect_on_trace(params, hotspot, config=config)
  improvements = reflection.get("tool_improvements") or []
  applied: list[str] = []

  for imp in improvements[:3]:
    name = str(imp.get("tool") or tool_name or "").strip()
    addendum = str(imp.get("description_addendum") or "").strip()
    if not name or not addendum:
      continue
    proposal = propose_tool_desc_from_trace(
      params,
      tool_name=name,
      current_description=addendum,
      error_snippet=first[:200],
      reflection=str(reflection.get("root_cause") or ""),
    )
    if proposal.get("ok"):
      set_tool_desc_override(params, name, proposal["description"], source="evolution")
      applied.append(name)

  if not applied and tool_name:
    proposal = propose_tool_desc_from_trace(
      params,
      tool_name=tool_name,
      current_description="",
      error_snippet=first[:200],
      reflection=str(reflection.get("root_cause") or ""),
    )
    if proposal.get("ok"):
      set_tool_desc_override(params, tool_name, proposal["description"], source="evolution")
      applied.append(tool_name)

  return {"applied": applied} if applied else None


async def run_evolution_pipeline_manual(
  params: Params,
  *,
  session_id: str = "",
  focus: str = "",
  skill_id: str = "",
  eval_source: str = "sessiondb",
) -> dict[str, Any]:
  """Manual trigger from UI or tool — runs full GEPA when enabled."""
  cfg = read_ai_config(params)
  from ai.tools.skill_evolution import analyze_execution_traces, evolve_skill_proposal

  sid = (skill_id or focus or "memory-protocol").strip()
  traces = analyze_execution_traces(params, limit=12)
  hotspot = None
  for t in traces.get("traces") or []:
    if session_id and t.get("sessionId") == session_id:
      hotspot = t
      break

  evo = await evolve_skill_proposal(
    params,
    trace_session_id=session_id,
    focus=focus,
    skill_id=sid,
    eval_source=eval_source,
    use_llm=evolution_llm_reflect() and cfg.is_configured,
    config=cfg,
    candidate_count=evolution_candidate_count(),
    use_gepa=True,
  )
  return {"ok": True, "evolution": evo, "skillId": sid}
