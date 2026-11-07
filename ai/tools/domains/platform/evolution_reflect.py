"""LLM reflective analysis for evolution loop (GEPA-inspired, API-only)."""

from __future__ import annotations

import json
from typing import Any

from openpilot.common.params import Params

from ai.core.llm.client import AIConfig
from ai.core.llm.model_router import chat_completion_collect_with_failover


_REFLECT_SYSTEM = """You are an AI agent evolution analyst (Hermes/GEPA style).
Given execution trace signals from a driving-assistant chat session, output JSON only:
{
  "root_cause": "one paragraph",
  "skill_title": "short title",
  "skill_body": "markdown SKILL with ## sections and numbered steps",
  "tool_improvements": [{"tool": "name", "description_addendum": "text"}],
  "workspace_updates": [{"key": "user|memory|soul", "section": "## Title", "content": "bullet points"}]
}
Be specific to openpilot/Cabana/tuning context when relevant. No vehicle actuator commands."""


async def reflect_on_trace(
  params: Params,
  hotspot: dict[str, Any],
  *,
  focus: str = "",
  config: AIConfig | None = None,
) -> dict[str, Any]:
  from ai.server.deps import read_ai_config
  cfg = config or read_ai_config(params)
  if not cfg.is_configured:
    return {"ok": False, "error": "AI not configured for reflection"}

  payload = {
    "hotspot": hotspot,
    "focus": focus,
  }
  messages = [
    {"role": "system", "content": _REFLECT_SYSTEM},
    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
  ]
  content, _, _, err = await chat_completion_collect_with_failover(
    cfg, params, messages, max_tokens=2500, temperature=0.3,
  )
  if err:
    return {"ok": False, "error": err}

  text = (content or "").strip()
  if text.startswith("```"):
    text = text.split("\n", 1)[-1]
    if text.endswith("```"):
      text = text[:-3]
  try:
    data = json.loads(text)
  except json.JSONDecodeError:
    return {
      "ok": True,
      "parsed": False,
      "raw": text[:4000],
      "skill_title": hotspot.get("title", "workflow improvement")[:60],
      "skill_body": text,
      "tool_improvements": [],
      "workspace_updates": [],
    }

  from ai.common.consumer_lexicon import filter_consumer_language

  return {
    "ok": True,
    "parsed": True,
    "root_cause": data.get("root_cause", ""),
    "skill_title": filter_consumer_language(str(data.get("skill_title") or "")),
    "skill_body": filter_consumer_language(str(data.get("skill_body") or "")),
    "tool_improvements": data.get("tool_improvements") or [],
    "workspace_updates": data.get("workspace_updates") or [],
  }


async def generate_skill_variants(
  params: Params,
  hotspot: dict[str, Any],
  *,
  count: int = 3,
  focus: str = "",
) -> list[dict[str, Any]]:
  """Generate multiple skill candidates for Pareto selection."""
  base = await reflect_on_trace(params, hotspot, focus=focus)
  if not base.get("ok"):
    return [{"ok": False, "error": base.get("error"), "hotspot": hotspot}]

  title = base.get("skill_title") or f"改进：{hotspot.get('title', 'workflow')[:40]}"
  body = base.get("skill_body") or ""
  variants: list[dict[str, Any]] = [{
    "variant": "reflect",
    "title": title,
    "body": body,
    "hotspot": hotspot,
    "root_cause": base.get("root_cause", ""),
  }]

  if count <= 1:
    return variants

  # Lightweight mutations for Pareto diversity
  if body:
    variants.append({
      "variant": "checklist",
      "title": f"{title}（检查清单）",
      "body": _to_checklist(body, hotspot),
      "hotspot": hotspot,
    })
    variants.append({
      "variant": "concise",
      "title": f"{title}（精简）",
      "body": _concise(body),
      "hotspot": hotspot,
    })
  return variants[:count]


def _to_checklist(body: str, hotspot: dict[str, Any]) -> str:
  lines = ["## 前置检查", "- 确认车辆静止（写操作）", "- 确认工具可用"]
  if hotspot.get("toolErrors"):
    lines.append("## 常见错误与处理")
    for err in hotspot["toolErrors"][:4]:
      lines.append(f"- {err}")
  lines.append("## 执行步骤")
  for line in body.splitlines():
    if line.strip().startswith(("1.", "2.", "3.", "- ")):
      lines.append(line)
  return "\n".join(lines)


def _concise(body: str) -> str:
  parts = [ln for ln in body.splitlines() if ln.strip() and not ln.strip().startswith("#")]
  return "## 精简流程\n" + "\n".join(parts[:12])
