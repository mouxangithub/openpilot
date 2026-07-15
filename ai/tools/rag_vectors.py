"""File-backed vector chunks for RAG (vectors too large for Params)."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from ai.system.paths import rag_vectors_path

_MAX_CHUNKS = 200


def _index_path() -> Path:
  p = rag_vectors_path()
  p.parent.mkdir(parents=True, exist_ok=True)
  return p


def _load_chunks() -> list[dict[str, Any]]:
  path = _index_path()
  if not path.is_file():
    return []
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []
  except Exception:
    return []


def _save_chunks(chunks: list[dict[str, Any]]) -> None:
  _index_path().write_text(json.dumps(chunks[:_MAX_CHUNKS], ensure_ascii=False), encoding="utf-8")


def _cosine(a: list[float], b: list[float]) -> float:
  if not a or not b or len(a) != len(b):
    return 0.0
  dot = sum(x * y for x, y in zip(a, b))
  na = math.sqrt(sum(x * x for x in a))
  nb = math.sqrt(sum(y * y for y in b))
  if na == 0 or nb == 0:
    return 0.0
  return dot / (na * nb)


def replace_doc_chunks(doc_id: str, chunks: list[dict[str, Any]]) -> None:
  all_chunks = [c for c in _load_chunks() if c.get("doc_id") != doc_id]
  all_chunks = chunks + all_chunks
  _save_chunks(all_chunks[:_MAX_CHUNKS])


def remove_doc_chunks(doc_id: str) -> None:
  _save_chunks([c for c in _load_chunks() if c.get("doc_id") != doc_id])


def search_vector_chunks(query_vec: list[float], *, limit: int = 5) -> list[dict[str, Any]]:
  scored: list[tuple[float, dict[str, Any]]] = []
  for ch in _load_chunks():
    emb = ch.get("embedding")
    if not isinstance(emb, list):
      continue
    score = _cosine(query_vec, emb)
    if score > 0.05:
      scored.append((score, ch))
  scored.sort(key=lambda x: x[0], reverse=True)
  return [
    {
      "id": ch.get("doc_id"),
      "title": ch.get("title", ""),
      "score": round(score, 4),
      "snippet": (ch.get("text") or "")[:800],
      "chunk_index": ch.get("chunk_index", 0),
    }
    for score, ch in scored[:limit]
  ]


def chunk_count() -> int:
  return len(_load_chunks())
