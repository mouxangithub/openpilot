"""Agent-proposed learned skills (Hermes-style procedural memory)."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from openpilot.common.params import Params

from ai.common.storage import read_param, write_param

LEARNED_KEY = "ai_learned_skills"
MAX_LEARNED = 24
_LEARNED_DIR = Path(__file__).resolve().parent.parent / "skills" / "learned"


def _slug(text: str) -> str:
  s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", (text or "").lower()).strip("-")
  return s[:48] or f"skill-{int(time.time())}"


def _load(params: Params) -> list[dict[str, Any]]:
  try:
    raw = read_param(params, LEARNED_KEY)
    if not raw:
      return []
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="replace")
    data = json.loads(raw)
    return data if isinstance(data, list) else []
  except Exception:
    return []


def _save(params: Params, items: list[dict[str, Any]]) -> None:
  write_param(params, LEARNED_KEY, json.dumps(items[:MAX_LEARNED], ensure_ascii=False))


def list_learned_skills(params: Params | None = None) -> dict[str, Any]:
  items = _load(params or Params())
  return {
    "ok": True,
    "skills": [
      {
        "id": s.get("id"),
        "title": s.get("title"),
        "status": s.get("status", "pending"),
        "createdAt": s.get("created_at"),
        "path": s.get("path"),
      }
      for s in items
    ],
  }


def propose_learned_skill(
  params: Params,
  *,
  title: str,
  body: str,
  tags: list[str] | None = None,
  auto_approve: bool = False,
) -> dict[str, Any]:
  title = (title or "").strip()
  body = (body or "").strip()
  if not title or not body:
    return {"ok": False, "error": "title and body required"}
  sid = _slug(title)
  items = _load(params)
  if any(s.get("id") == sid for s in items):
    sid = f"{sid}-{int(time.time())}"
  status = "approved" if auto_approve else "pending"
  _LEARNED_DIR.mkdir(parents=True, exist_ok=True)
  skill_dir = _LEARNED_DIR / sid
  skill_dir.mkdir(parents=True, exist_ok=True)
  md = f"---\nid: {sid}\ntitle: {title}\ntags: {','.join(tags or [])}\nstatus: {status}\n---\n\n{body}\n"
  path = skill_dir / "SKILL.md"
  path.write_text(md, encoding="utf-8")
  entry = {
    "id": sid,
    "title": title,
    "status": status,
    "tags": tags or [],
    "path": str(path.relative_to(_LEARNED_DIR.parent.parent)),
    "created_at": int(time.time()),
  }
  items.insert(0, entry)
  _save(params, items)
  return {"ok": True, "skill": entry}


def approve_learned_skill(params: Params, skill_id: str) -> dict[str, Any]:
  items = _load(params)
  for s in items:
    if s.get("id") == skill_id:
      s["status"] = "approved"
      _save(params, items)
      return {"ok": True, "skill": s}
  return {"ok": False, "error": "skill not found"}


def learned_skills_prompt(params: Params, *, limit: int = 3) -> str:
  items = [s for s in _load(params) if s.get("status") == "approved"][:limit]
  if not items:
    return ""
  lines = ["# Learned skills (user-approved)"]
  for s in items:
    p = Path(__file__).resolve().parent.parent / str(s.get("path", ""))
    if p.is_file():
      lines.append(p.read_text(encoding="utf-8", errors="replace")[:1500])
  return "\n\n".join(lines)
