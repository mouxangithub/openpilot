"""File-backed vector chunks for RAG (vectors too large for Params)."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

from ai.common.rag_config import rag_max_chunks
from ai.system.paths import rag_vectors_path

# Re-export for tests / API limits display (value follows ai_rag_max_chunks param).
def _max_chunks() -> int:
  return rag_max_chunks()


_MAX_CHUNKS = 100_000  # module default; runtime uses rag_max_chunks()

_META_CACHE: dict[str, Any] | None = None
_META_CACHE_KEY: tuple[int, int] | None = None  # (mtime_ns, size)


def _index_path() -> Path:
  p = rag_vectors_path()
  p.parent.mkdir(parents=True, exist_ok=True)
  return p


def _meta_path() -> Path:
  return _index_path().with_name(_index_path().name + ".meta.json")


def _index_stat() -> tuple[int, int] | None:
  path = _index_path()
  if not path.is_file():
    return None
  st = path.stat()
  return (st.st_mtime_ns, st.st_size)


def _write_meta(chunks: list[dict[str, Any]]) -> None:
  global _META_CACHE, _META_CACHE_KEY
  by_doc: dict[str, int] = {}
  for ch in chunks:
    did = str(ch.get("doc_id") or "")
    if did:
      by_doc[did] = by_doc.get(did, 0) + 1
  stat = _index_stat()
  meta = {
    "chunk_count": len(chunks),
    "by_doc": by_doc,
    "at": int(time.time()),
    "index_mtime_ns": stat[0] if stat else 0,
    "index_size": stat[1] if stat else 0,
  }
  _meta_path().write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
  _META_CACHE = meta
  _META_CACHE_KEY = stat


def _read_meta_file() -> dict[str, Any] | None:
  path = _meta_path()
  if not path.is_file():
    return None
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None
  except Exception:
    return None


def _meta_is_valid(meta: dict[str, Any] | None) -> bool:
  if not meta:
    return False
  stat = _index_stat()
  if not stat:
    return bool(meta.get("chunk_count") == 0)
  return (
    int(meta.get("index_mtime_ns") or 0) == stat[0]
    and int(meta.get("index_size") or 0) == stat[1]
  )


def vector_index_meta(*, rebuild: bool = False) -> dict[str, Any]:
  """Fast vector stats without parsing the full embedding index."""
  global _META_CACHE, _META_CACHE_KEY
  stat = _index_stat()
  if not stat:
    empty = {"chunk_count": 0, "by_doc": {}}
    _META_CACHE = empty
    _META_CACHE_KEY = None
    return empty

  if not rebuild and _META_CACHE is not None and _META_CACHE_KEY == stat:
    return _META_CACHE

  meta = None if rebuild else _read_meta_file()
  if _meta_is_valid(meta):
    _META_CACHE = meta
    _META_CACHE_KEY = stat
    return meta

  chunks = _load_chunks()
  _write_meta(chunks)
  return _META_CACHE or {"chunk_count": 0, "by_doc": {}}


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
  cap = rag_max_chunks()
  trimmed = chunks[:cap]
  _index_path().write_text(json.dumps(trimmed, ensure_ascii=False), encoding="utf-8")
  _write_meta(trimmed)


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
  _save_chunks(all_chunks[: rag_max_chunks()])


def write_all_chunks(chunks: list[dict[str, Any]]) -> None:
  _save_chunks(chunks[: rag_max_chunks()])


def remove_doc_chunks(doc_id: str) -> None:
  _save_chunks([c for c in _load_chunks() if c.get("doc_id") != doc_id])


def clear_all_chunks() -> None:
  path = _index_path()
  if path.is_file():
    path.unlink()
  meta = _meta_path()
  if meta.is_file():
    meta.unlink()
  global _META_CACHE, _META_CACHE_KEY
  _META_CACHE = {"chunk_count": 0, "by_doc": {}}
  _META_CACHE_KEY = None


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


def doc_chunk_counts() -> dict[str, int]:
  meta = vector_index_meta()
  by_doc = meta.get("by_doc") or {}
  if not isinstance(by_doc, dict):
    return {}
  return {str(k): int(v) for k, v in by_doc.items() if k}


def chunk_count() -> int:
  return int(vector_index_meta().get("chunk_count") or 0)
