"""Hermes / OpenClaw style memory protocol — in-chat tools + post-chat closed loop."""

from __future__ import annotations

import json
import re
import time
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
  from openpilot.common.params import Params

from ai.core.llm.client import AIConfig, chat_completion_collect
from ai.tools.domains.core.daily_memory import append_daily_memory

_EXTRACT_SYSTEM = """You are the memory curator for an openpilot OP Agent (Hermes / OpenClaw style).
Given a short conversation excerpt, output JSON only:
{
  "skip": false,
  "reason": "why skip if true",
  "daily_bullets": ["concise bullet for today's log"],
  "memory_sections": [{"section": "## 长期事实|## 已解决问题|## 待跟进|## 禁忌与边界", "content": "markdown bullets"}],
  "user_sections": [{"section": "## 称呼与语言|## 车辆与设备|## 工作流偏好", "content": "markdown bullets"}],
  "notes": ["optional short note for structured memory store"]
}
Rules:
- skip=true for greetings, thanks, or no durable facts.
- Never store API keys, passwords, or full addresses.
- Prefer Chinese when user wrote Chinese.
- daily_bullets: what happened THIS session (tuning, diagnosis, decisions).
- memory_sections: stable facts worth months (vehicle quirks, fixed bugs).
- user_sections: preferences and profile updates only when clearly stated."""

_TRIVIAL_RE = re.compile(
  r"^(hi|hello|hey|thanks|thank you|ok|okay|yes|no|好|谢谢|嗯|在吗|你好)[\s!.?。！？]*$",
  re.I,
)

_LAST_EXTRACT: dict[str, float] = {}
_DEDUP_SEC = 45


def _message_text(content: Any) -> str:
  if isinstance(content, str):
    return content
  if isinstance(content, list):
    parts = []
    for p in content:
      if isinstance(p, dict) and p.get("type") == "text":
        parts.append(str(p.get("text") or ""))
    return " ".join(parts)
  return str(content or "")


def conversation_tail(messages: list[dict[str, Any]], *, max_messages: int = 8) -> list[dict[str, Any]]:
  conv = [m for m in messages if m.get("role") in ("user", "assistant")]
  tail = conv[-max_messages:]
  out: list[dict[str, Any]] = []
  for m in tail:
    text = _message_text(m.get("content")).strip()
    if not text and m.get("role") == "assistant":
      continue
    out.append({"role": m.get("role"), "content": text[:2500]})
  return out


def should_skip_auto_extract(messages: list[dict[str, Any]], *, session_id: str = "") -> str | None:
  tail = conversation_tail(messages, max_messages=4)
  if len(tail) < 2:
    return "too_short"
  last_user = ""
  for m in reversed(tail):
    if m.get("role") == "user":
      last_user = str(m.get("content") or "").strip()
      break
  if not last_user:
    return "empty_user"
  if _TRIVIAL_RE.match(last_user):
    return "trivial"
  if len(last_user) < 4:
    return "empty_user"
  sid = session_id or "default"
  now = time.time()
  if now - _LAST_EXTRACT.get(sid, 0) < _DEDUP_SEC:
    return "dedup"
  return None


def apply_memory_payload(
  params: Any,
  data: dict[str, Any],
  *,
  session_id: str = "",
) -> dict[str, Any]:
  applied: dict[str, Any] = {"daily": False, "memory": [], "user": [], "notes": 0}
  if data.get("skip"):
    return {"ok": True, "skipped": True, "reason": data.get("reason"), "applied": applied}

  bullets = data.get("daily_bullets") or []
  if bullets:
    res = append_daily_memory(bullets=bullets, session_id=session_id, title="对话")
    applied["daily"] = bool(res.get("ok"))

  memory_sections = data.get("memory_sections") or []
  user_sections = data.get("user_sections") or []
  if memory_sections or user_sections:
    from ai.tools.domains.platform.workspace_enrich import update_workspace_file

  for item in memory_sections[:4]:
    section = str(item.get("section") or "").strip()
    content = str(item.get("content") or "").strip()
    if not section or not content:
      continue
    res = update_workspace_file(params, key="memory", content=content, merge_section=section)
    if res.get("ok"):
      applied["memory"].append(section)

  for item in user_sections[:3]:
    section = str(item.get("section") or "").strip()
    content = str(item.get("content") or "").strip()
    if not section or not content:
      continue
    res = update_workspace_file(params, key="user", content=content, merge_section=section)
    if res.get("ok"):
      applied["user"].append(section)

  for note in (data.get("notes") or [])[:3]:
    text = str(note or "").strip()
    if text:
      from ai.tools.domains.core.memory_store import append_note
      append_note(params, text, tags=["memory-protocol", f"session:{session_id[:12]}"] if session_id else ["memory-protocol"])
      applied["notes"] += 1

  return {"ok": True, "skipped": False, "applied": applied}


async def extract_and_persist_session_memory(
  params: Any,
  messages: list[dict[str, Any]],
  *,
  config: AIConfig,
  session_id: str = "",
) -> dict[str, Any]:
  """Post-chat Hermes-style memory extraction (LLM → daily + MEMORY + USER)."""
  if not config.is_configured:
    return {"ok": False, "error": "AI not configured"}

  skip_reason = should_skip_auto_extract(messages, session_id=session_id)
  if skip_reason:
    return {"ok": True, "skipped": True, "reason": skip_reason}

  tail = conversation_tail(messages)
  transcript = "\n".join(f"{m['role']}: {m['content']}" for m in tail)
  user_msg = json.dumps({"session_id": session_id, "transcript": transcript}, ensure_ascii=False)

  content, _, err = await chat_completion_collect(
    config,
    [
      {"role": "system", "content": _EXTRACT_SYSTEM},
      {"role": "user", "content": user_msg},
    ],
    max_tokens=1200,
    temperature=0.2,
    timeout_total=60,
  )
  if err or not (content or "").strip():
    return {"ok": False, "error": err or "empty extract"}

  text = content.strip()
  if text.startswith("```"):
    text = text.split("\n", 1)[-1]
    if text.endswith("```"):
      text = text[:-3]
  try:
    data = json.loads(text)
  except json.JSONDecodeError:
    return {"ok": False, "error": "invalid JSON from extractor", "raw": text[:500]}

  if not isinstance(data, dict):
    return {"ok": False, "error": "extractor returned non-object"}

  result = apply_memory_payload(params, data, session_id=session_id)
  if session_id and not result.get("skipped"):
    _LAST_EXTRACT[session_id] = time.time()
  return result


def memory_protocol_prompt_block() -> str:
  """Pinned instructions (also in memory-protocol SKILL.md)."""
  lines = [
    "# Memory protocol (mandatory when durable facts appear)",
    "- **Daily wiki page**: `workspace/memory/YYYY-MM-DD.md` + auto `INDEX.md` — injected each turn; use `read_daily_memory` for full day.",
    "- **Daily log**: `append_daily_memory` — session events (also auto after chat).",
    "- **Long-term**: `update_workspace_file` key=memory — stable facts in MEMORY.md sections.",
    "- **Profile**: `update_workspace_file` key=user or `update_user_profile` — preferences & vehicle.",
    "- **Quick notes**: `update_agent_memory` — short structured notes in Params.",
    "- Before ending a substantive reply, persist anything the user would expect you to remember next time.",
    "- Do not duplicate: if you already wrote memory tools this turn, skip unless new facts appeared.",
  ]
  return "\n".join(lines)
