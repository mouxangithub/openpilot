"""Extra RAG documents from settings catalog + skills; version tracking."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from openpilot.common.params import Params

from ai.tools.rag_store import upsert_document_sync
from ai.system.paths import rag_seed_version_path

SEED_VERSION = 7


def _version_path() -> Path:
  p = rag_seed_version_path()
  p.parent.mkdir(parents=True, exist_ok=True)
  return p


def get_seed_version() -> int:
  try:
    data = json.loads(_version_path().read_text(encoding="utf-8"))
    return int(data.get("version", 0))
  except Exception:
    return 0


def set_seed_version(version: int) -> None:
  _version_path().write_text(
    json.dumps({"version": version, "at": int(time.time())}, ensure_ascii=False),
    encoding="utf-8",
  )


def _skills_digest() -> str:
  skills_dir = Path(__file__).resolve().parent.parent / "skills"
  parts: list[str] = []
  for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
    try:
      text = skill_md.read_text(encoding="utf-8", errors="replace")[:2500]
      parts.append(f"## {skill_md.parent.name}\n{text}")
    except OSError:
      continue
  return "\n\n".join(parts)[:11000]


def _settings_digest() -> str:
  try:
    from ai.tools.catalog_builder import build_merged_catalog
    cat = build_merged_catalog()
  except Exception:
    return ""
  lines = ["# Dragonpilot Params catalog (AI reference)\n"]
  for key in sorted(cat.keys())[:120]:
    meta = cat[key]
    if meta.get("tier", "").startswith("write_forbidden"):
      continue
    lines.append(f"- `{key}` ({meta.get('tier', '')}): {meta.get('summary', meta.get('title', ''))[:120]}")
  return "\n".join(lines)[:11000]


_EXTRA_DOCS: list[dict[str, Any]] = [
  {
    "id": "builtin_dp_settings_catalog",
    "title": "Dragonpilot 可调参数目录",
    "tags": ["dp", "settings", "params", "faq"],
    "refresh": True,
    "text_fn": _settings_digest,
  },
  {
    "id": "builtin_skills_digest",
    "title": "Agent 技能摘要",
    "tags": ["skills", "faq"],
    "refresh": True,
    "text_fn": _skills_digest,
  },
]


def ensure_extra_rag_docs(params: Params | None = None) -> dict[str, Any]:
  params = params or Params()
  current = get_seed_version()
  force = current < SEED_VERSION
  seeded = refreshed = 0
  errors: list[str] = []

  for doc in _EXTRA_DOCS:
    doc_id = doc["id"]
    should_write = force or doc.get("refresh")
    if not should_write:
      continue
    try:
      text = doc["text_fn"]() if callable(doc.get("text_fn")) else doc.get("text", "")
      if not text.strip():
        continue
      upsert_document_sync(
        params,
        title=doc["title"],
        text=text,
        tags=doc.get("tags"),
        doc_id=doc_id,
      )
      if force:
        seeded += 1
      else:
        refreshed += 1
    except Exception as e:
      errors.append(f"{doc_id}: {e}")

  if force and not errors:
    set_seed_version(SEED_VERSION)

  return {
    "ok": len(errors) == 0,
    "version": SEED_VERSION,
    "previous_version": current,
    "seeded": seeded,
    "refreshed": refreshed,
    "errors": errors[:5],
  }
