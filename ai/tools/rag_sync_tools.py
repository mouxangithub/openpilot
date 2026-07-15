"""Sync built-in docs into RAG knowledge base."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai.system.paths import openpilot_root
from ai.tools.rag_store import upsert_document_sync

_DOC_GLOBS = (
  "ai/docs/*.md",
  "ai/skills/**/*.md",
  "docs/**/*.md",
)


def sync_knowledge_from_docs(
  params=None,
  *,
  max_files: int = 40,
  tag_prefix: str = "auto",
) -> dict[str, Any]:
  """Import markdown from repo into RAG (sync, no embedding)."""
  from openpilot.common.params import Params
  params = params or Params()
  root = openpilot_root()
  indexed = 0
  errors: list[str] = []
  seen: set[str] = set()

  for pattern in _DOC_GLOBS:
    for path in sorted(root.glob(pattern))[:max_files]:
      if not path.is_file() or path.suffix.lower() != ".md":
        continue
      rel = str(path.relative_to(root)).replace("\\", "/")
      if rel in seen:
        continue
      seen.add(rel)
      try:
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) < 80:
          continue
        doc_id = f"auto_{rel.replace('/', '_')[:80]}"
        tags = [tag_prefix, "docs"]
        if "skill" in rel.lower():
          tags.append("skill")
        if "dragonpilot" in rel.lower():
          tags.append("dragonpilot")
        res = upsert_document_sync(params, title=rel, text=text, tags=tags, doc_id=doc_id)
        if res.get("ok"):
          indexed += 1
        else:
          errors.append(f"{rel}: {res.get('error')}")
      except Exception as e:
        errors.append(f"{rel}: {e}")
      if indexed >= max_files:
        break
    if indexed >= max_files:
      break

  return {"ok": True, "indexed": indexed, "errors": errors[:5]}
