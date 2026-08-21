"""Semantic search over agent memory notes (file-backed vectors)."""

from __future__ import annotations

import json
import math
from typing import Any

from ai.system.paths import workspace_path

_STORE = workspace_path("ai_memory_vectors.json", mkdir=True)


def _load() -> dict[str, Any]:
  if not _STORE.is_file():
    return {"chunks": []}
  try:
    data = json.loads(_STORE.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {"chunks": []}
  except Exception:
    return {"chunks": []}


def _save(data: dict[str, Any]) -> None:
  _STORE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _cosine(a: list[float], b: list[float]) -> float:
  if not a or not b or len(a) != len(b):
    return 0.0
  dot = sum(x * y for x, y in zip(a, b))
  na = math.sqrt(sum(x * x for x in a))
  nb = math.sqrt(sum(y * y for y in b))
  if na == 0 or nb == 0:
    return 0.0
  return dot / (na * nb)


async def index_memory_notes(params, embed_config=None) -> dict[str, Any]:
  """Embed recent memory notes into vector store."""
  from ai.tools.domains.core.memory_store import get_memory
  from ai.core.llm.embedding import embed_texts_with_failover, load_embedding_config_chain

  notes = (get_memory(params).get("notes") or [])[:40]
  if not notes:
    return {"ok": True, "indexed": 0}
  if not load_embedding_config_chain(params):
    return {"ok": False, "error": "embedding not configured"}

  texts = [(n.get("text") or "").strip() for n in notes]
  texts = [t for t in texts if t]
  vectors, _cfg, err = await embed_texts_with_failover(params, texts, source="memory_index")
  if err or not vectors:
    return {"ok": False, "error": err or "embedding failed"}

  chunks = []
  idx = 0
  for note, vec in zip(notes, vectors):
    text = (note.get("text") or "").strip()
    if not text:
      continue
    chunks.append({
      "id": note.get("id") or f"n_{idx}",
      "text": text[:MAX_SNIPPET],
      "tags": note.get("tags") or [],
      "at": note.get("at"),
      "vector": vec,
    })
    idx += 1
  _save({"chunks": chunks, "updated_at": int(__import__("time").time())})
  return {"ok": True, "indexed": len(chunks)}


MAX_SNIPPET = 500


async def search_memory_semantic(
  params,
  query: str,
  *,
  limit: int = 5,
  embed_config=None,
) -> dict[str, Any]:
  """Vector search agent memory; falls back to keyword match."""
  from ai.tools.domains.core.memory_store import get_memory
  from ai.core.llm.embedding import embed_texts_with_failover, load_embedding_config_chain

  q = (query or "").strip()
  if not q:
    return {"ok": False, "error": "query required"}

  store = _load()
  chunks = store.get("chunks") or []
  if chunks and load_embedding_config_chain(params):
    vectors, _cfg, err = await embed_texts_with_failover(params, [q], source="memory_search")
    if not err and vectors:
      scored = []
      for ch in chunks:
        vec = ch.get("vector")
        if not vec:
          continue
        scored.append({**ch, "score": round(_cosine(vectors[0], vec), 4), "method": "vector"})
      scored.sort(key=lambda x: x.get("score", 0), reverse=True)
      return {"ok": True, "query": q, "hits": scored[:limit], "method": "vector"}

  # Keyword fallback
  notes = get_memory(params).get("notes") or []
  ql = q.lower()
  hits = []
  for n in notes:
    text = (n.get("text") or "")
    if ql in text.lower():
      hits.append({"id": n.get("id"), "text": text[:MAX_SNIPPET], "tags": n.get("tags"), "method": "keyword"})
  return {"ok": True, "query": q, "hits": hits[:limit], "method": "keyword"}
