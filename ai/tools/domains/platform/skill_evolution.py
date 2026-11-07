"""Hermes-inspired skill evolution — trace mining, LLM reflection, Pareto selection."""

from __future__ import annotations

import re
import time
from typing import Any

from openpilot.common.params import Params

from ai.core.llm.client import AIConfig
from ai.tools.domains.platform.session_store import get_sessions
from ai.tools.domains.platform.skill_learning import _load as _load_learned, propose_learned_skill
from ai.tools.domains.platform.skill_evaluation import pick_best_candidate

_ERROR_PATTERNS = (
  re.compile(r"\b(error|failed|failure|exception|traceback)\b", re.I),
  re.compile(r"工具.*失败|执行失败|无法|报错"),
)
_RETRY_PATTERNS = (
  re.compile(r"\b(retry|again|let me try)\b", re.I),
  re.compile(r"再试|重试|再来一次"),
)
_CORRECTION_PATTERNS = (
  re.compile(r"\b(no,|not that|wrong|incorrect|instead)\b", re.I),
  re.compile(r"不对|不是|错了|应该"),
)


def _msg_text(msg: dict[str, Any]) -> str:
  content = msg.get("content")
  if isinstance(content, str):
    return content
  if isinstance(content, list):
    parts = []
    for p in content:
      if isinstance(p, dict) and p.get("type") == "text":
        parts.append(str(p.get("text") or ""))
    return " ".join(parts)
  return ""


def _scan_session(session: dict[str, Any]) -> dict[str, Any]:
  signals: list[str] = []
  tool_errors: list[str] = []
  user_corrections: list[str] = []
  messages = session.get("messages") or []
  prev_user = ""
  for msg in messages:
    role = msg.get("role")
    text = _msg_text(msg)
    if role == "user":
      if any(p.search(text) for p in _CORRECTION_PATTERNS):
        user_corrections.append(text[:300])
      prev_user = text
    if role == "assistant":
      if any(p.search(text) for p in _ERROR_PATTERNS):
        signals.append("assistant_error_mention")
      if any(p.search(text) for p in _RETRY_PATTERNS):
        signals.append("retry")
      if msg.get("tool_calls"):
        for tc in msg.get("tool_calls") or []:
          fn = (tc.get("function") or {}).get("name") or ""
          if fn:
            signals.append(f"tool:{fn}")
    tr = msg.get("tool_results") or {}
    if isinstance(tr, dict):
      for name, result in tr.items():
        rs = str(result or "")
        if any(p.search(rs) for p in _ERROR_PATTERNS):
          tool_errors.append(f"{name}: {rs[:200]}")
  title = session.get("title") or session.get("id") or "session"
  score = len(tool_errors) * 3 + len(user_corrections) * 2 + (1 if "retry" in signals else 0)
  return {
    "sessionId": session.get("id"),
    "title": title,
    "score": score,
    "signals": list(dict.fromkeys(signals))[:12],
    "toolErrors": tool_errors[:6],
    "userCorrections": user_corrections[:4],
    "lastUser": prev_user[:400],
  }


def analyze_execution_traces(params: Params | None = None, *, limit: int = 8) -> dict[str, Any]:
  """Mine recent sessions for failure / correction signals (GEPA trace-collection phase)."""
  params = params or Params()
  sessions = (get_sessions(params).get("sessions") or [])[:limit]
  traces = [_scan_session(s) for s in sessions]
  traces.sort(key=lambda t: t.get("score", 0), reverse=True)
  hot = [t for t in traces if t.get("score", 0) > 0]
  return {
    "ok": True,
    "traces": traces,
    "hotspots": hot[:5],
    "hint": "Use evolve_skill_proposal on a hotspot to draft an improved learned skill.",
  }


def _template_body(hotspot: dict[str, Any] | None, focus: str) -> tuple[str, str]:
  if hotspot:
    title = f"改进：{hotspot.get('title', 'workflow')[:40]}"
  else:
    title = "通用工作流改进"
  lines = ["# 进化技能草案", "", "基于近期会话执行轨迹自动生成，请审核后批准。", ""]
  if focus:
    lines.append(f"## 聚焦\n{focus}\n")
  if hotspot:
    lines.append("## 观测到的信号")
    for sig in hotspot.get("signals") or []:
      lines.append(f"- {sig}")
    if hotspot.get("toolErrors"):
      lines.append("\n## 工具错误")
      for err in hotspot["toolErrors"]:
        lines.append(f"- {err}")
    if hotspot.get("userCorrections"):
      lines.append("\n## 用户纠正")
      for c in hotspot["userCorrections"]:
        lines.append(f"- {c}")
    lines.append("\n## 建议步骤")
    lines.append("1. 复现失败路径并确认根因")
    lines.append("2. 在工具调用前增加前置检查")
    lines.append("3. 失败时给出可操作的回退方案")
  else:
    lines.append("暂无显著失败信号；可手动补充工作流步骤。")
  return title, "\n".join(lines)


async def evolve_skill_proposal(
  params: Params,
  *,
  title: str = "",
  trace_session_id: str = "",
  focus: str = "",
  body: str = "",
  use_llm: bool = True,
  config: AIConfig | None = None,
  candidate_count: int = 3,
  skill_id: str = "",
  eval_source: str = "",
  use_gepa: bool | None = None,
) -> dict[str, Any]:
  """Propose an evolved skill via GEPA (built-in) or legacy Pareto reflection."""
  from ai.common.evolution_config import evolution_gepa_enabled

  traces = analyze_execution_traces(params, limit=12)
  hotspot = None
  if trace_session_id:
    for t in traces.get("traces") or []:
      if t.get("sessionId") == trace_session_id:
        hotspot = t
        break
  if hotspot is None:
    hotspots = traces.get("hotspots") or []
    hotspot = hotspots[0] if hotspots else None

  sid = (skill_id or focus or "").strip()
  if not sid and hotspot:
    for sig in hotspot.get("signals") or []:
      if str(sig).startswith("tool:"):
        sid = "sp-tuning"
        break
  if not sid:
    sid = "memory-protocol"

  if body:
    use_gepa = False

  if (use_gepa if use_gepa is not None else evolution_gepa_enabled()) and use_llm:
    from ai.evolution.config import EvolutionRunConfig
    from ai.evolution.gepa_engine import evolve_skill_gepa
    run = EvolutionRunConfig.from_params(
      skill_id=sid,
      focus=focus,
      trace_session_id=trace_session_id,
      eval_source=eval_source or "sessiondb",
    )
    gepa_res = await evolve_skill_gepa(
      params,
      skill_id=sid,
      run=run,
      config=config,
      traces=traces.get("traces") or [],
      hotspot=hotspot,
    )
    if gepa_res.get("ok") or gepa_res.get("skillId"):
      return gepa_res

  candidates: list[dict[str, Any]] = []
  reflection_meta: dict[str, Any] = {}

  if body:
    candidates.append({"title": title or "技能草案", "body": body, "hotspot": hotspot, "variant": "manual"})
  elif use_llm and hotspot:
    from ai.tools.domains.platform.evolution_reflect import generate_skill_variants
    variants = await generate_skill_variants(
      params,
      hotspot,
      count=max(1, candidate_count),
      focus=focus,
    )
    for v in variants:
      if v.get("body"):
        candidates.append(v)
    reflection_meta["llm"] = True
  else:
    t, b = _template_body(hotspot, focus)
    candidates.append({"title": title or t, "body": b, "hotspot": hotspot, "variant": "template"})

  best = pick_best_candidate(candidates)
  if not best:
    return {"ok": False, "error": "no candidates generated"}

  final_title = title or best.get("title") or "进化技能"
  final_body = str(best.get("body") or "")
  scores = best.get("scores") or {}
  final_body += f"\n\n---\n_evolved_at: {int(time.time())}_ | variant={best.get('variant')} | pareto={scores}_\n"

  workspace_applied: list[str] = []
  if use_llm and hotspot:
    from ai.tools.domains.platform.evolution_reflect import reflect_on_trace
    from ai.tools.domains.platform.workspace_enrich import update_workspace_file
    ref = await reflect_on_trace(params, hotspot, focus=focus, config=config)
    for upd in (ref.get("workspace_updates") or [])[:3]:
      key = str(upd.get("key") or "memory")
      section = str(upd.get("section") or "")
      content = str(upd.get("content") or "").strip()
      if content:
        res = update_workspace_file(params, key=key, content=content, merge_section=section or "")
        if res.get("ok"):
          workspace_applied.append(key)

  skill_res = propose_learned_skill(
    params,
    title=final_title,
    body=final_body,
    tags=["evolved", "trace-mined", str(best.get("variant") or "v1")],
    auto_approve=False,
  )
  return {
    **skill_res,
    "paretoScores": scores,
    "variant": best.get("variant"),
    "candidates": len(candidates),
    "workspaceApplied": workspace_applied,
    "reflection": reflection_meta,
  }


def evolve_skill_proposal_sync(
  params: Params,
  **kwargs: Any,
) -> dict[str, Any]:
  """Sync wrapper for tool handlers."""
  import asyncio
  try:
    loop = asyncio.get_running_loop()
  except RuntimeError:
    return asyncio.run(evolve_skill_proposal(params, **kwargs))
  # Running loop: schedule is unsafe from sync context — use template path
  kwargs["use_llm"] = False
  return asyncio.run(evolve_skill_proposal(params, **kwargs))


def evolution_status(params: Params | None = None) -> dict[str, Any]:
  params = params or Params()
  learned = _load_learned(params)
  pending = [s for s in learned if s.get("status") == "pending"]
  evolved = [s for s in learned if "evolved" in (s.get("tags") or [])]
  traces = analyze_execution_traces(params, limit=6)
  from ai.common.evolution_config import evolution_settings
  from ai.tools.domains.platform.tool_desc_store import list_tool_desc_overrides
  from ai.core.runtime.evolution_pipeline import pipeline_log

  from ai.evolution.gepa_engine import gepa_status
  from ai.common.evolution_config import evolution_gepa_enabled
  return {
    "ok": True,
    "pendingSkills": len(pending),
    "evolvedSkills": len(evolved),
    "hotspots": len(traces.get("hotspots") or []),
    "learnedTotal": len(learned),
    "settings": evolution_settings(),
    "gepa": gepa_status(),
    "gepaEnabled": evolution_gepa_enabled(),
    "toolDescOverrides": list_tool_desc_overrides(params).get("count", 0),
    "recentPipeline": pipeline_log(params, limit=3).get("entries", []),
  }
