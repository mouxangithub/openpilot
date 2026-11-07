"""RAG document store with cloud embedding + keyword fallback."""

from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any

from openpilot.common.params import Params

from ai.common.storage import read_param, write_param

from ai.common.rag_config import rag_limits, rag_max_docs, rag_max_total_chars, rag_search_limit
from ai.tools.domains.core.rag_vectors import chunk_count, doc_chunk_counts, remove_doc_chunks, replace_doc_chunks, search_vector_chunks, vector_index_meta

_RAG_KEY = "ai_rag_documents"
_MAX_DOC_CHARS = 24000
_CHUNK_SIZE = 900
_CHUNK_OVERLAP = 120


def _tokenize(text: str) -> set[str]:
  return {w.lower() for w in re.findall(r"[\w\u4e00-\u9fff]+", text) if len(w) > 1}


def _chunk_text(text: str) -> list[str]:
  text = (text or "").strip()
  if not text:
    return []
  if len(text) <= _CHUNK_SIZE:
    return [text]
  chunks: list[str] = []
  start = 0
  while start < len(text):
    end = min(len(text), start + _CHUNK_SIZE)
    chunks.append(text[start:end])
    if end >= len(text):
      break
    start = max(0, end - _CHUNK_OVERLAP)
  return chunks


def _load_docs(params: Params) -> list[dict[str, Any]]:
  try:
    raw = read_param(params, _RAG_KEY)
    if not raw:
      return []
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="replace")
    data = json.loads(raw)
    return data if isinstance(data, list) else []
  except Exception:
    return []


def _save_docs(params: Params, docs: list[dict[str, Any]]) -> None:
  max_docs = rag_max_docs()
  max_chars = rag_max_total_chars()
  total = sum(len(d.get("text", "")) for d in docs)
  while docs and total > max_chars:
    removed = docs.pop()
    total -= len(removed.get("text", ""))
  write_param(params, _RAG_KEY, json.dumps(docs[:max_docs], ensure_ascii=False))


def upsert_document_sync(
  params: Params,
  *,
  title: str,
  text: str,
  tags: list[str] | None = None,
  doc_id: str | None = None,
) -> dict[str, Any]:
  """Sync upsert without embedding (for built-in seed docs)."""
  text = (text or "").strip()
  title = (title or "Untitled").strip()
  if not text:
    return {"ok": False, "error": "text is empty"}
  if len(text) > _MAX_DOC_CHARS:
    text = text[:_MAX_DOC_CHARS]

  docs = _load_docs(params)
  did = doc_id or f"doc_{uuid.uuid4().hex[:10]}"
  entry = {
    "id": did,
    "title": title,
    "text": text,
    "tags": tags or [],
    "at": int(time.time()),
    "embedded": False,
    "chunk_count": 0,
  }
  replaced = False
  for i, d in enumerate(docs):
    if d.get("id") == did:
      docs[i] = entry
      replaced = True
      break
  if not replaced:
    docs.insert(0, entry)
  _save_docs(params, docs)
  return {"ok": True, "document": {"id": did, "title": title}}


def list_documents(params: Params | None = None, *, compact: bool = False) -> dict[str, Any]:
  params = params or Params()
  docs = _load_docs(params)
  meta = vector_index_meta()
  by_doc = meta.get("by_doc") or {}
  if not isinstance(by_doc, dict):
    by_doc = {}
  total_chunks = int(meta.get("chunk_count") or 0)
  if compact:
    embedded = sum(1 for d in docs if int(by_doc.get(str(d.get("id") or ""), 0)) > 0)
    return {
      "ok": True,
      "compact": True,
      "documents": [],
      "count": len(docs),
      "embedded_docs": embedded,
      "vector_chunks": total_chunks,
      "limits": rag_limits(),
    }
  items = []
  for d in docs:
    did = str(d.get("id") or "")
    actual_chunks = int(by_doc.get(did, 0))
    items.append({
      "id": d.get("id"),
      "title": d.get("title"),
      "tags": d.get("tags", []),
      "chars": len(d.get("text", "")),
      "at": d.get("at"),
      "embedded": actual_chunks > 0,
      "chunks": actual_chunks,
    })
  return {
    "ok": True,
    "documents": items,
    "count": len(docs),
    "embedded_docs": sum(1 for x in items if x["embedded"]),
    "vector_chunks": total_chunks,
    "limits": rag_limits(),
  }


async def index_document_vectors(
  params: Params,
  doc_id: str,
  title: str,
  text: str,
  *,
  embed_config: Any | None = None,
  persist: bool = True,
) -> dict[str, Any]:
  from ai.core.llm.embedding import embed_texts_with_failover, load_embedding_config_chain

  pieces = _chunk_text(text)
  if not pieces:
    return {"ok": False, "error": "nothing to embed"}
  if embed_config is not None and not embed_config.is_configured:
    if not load_embedding_config_chain(params):
      return {"ok": False, "error": "embedding not configured", "fallback": "keyword"}
  elif not load_embedding_config_chain(params):
    return {"ok": False, "error": "embedding not configured", "fallback": "keyword"}

  vectors, _cfg, err = await embed_texts_with_failover(params, pieces, source="rag_index")
  if err or vectors is None:
    return {"ok": False, "error": err or "embed failed"}

  chunks = []
  for i, (piece, vec) in enumerate(zip(pieces, vectors)):
    chunks.append({
      "doc_id": doc_id,
      "title": title,
      "chunk_index": i,
      "text": piece,
      "embedding": vec,
    })
  if persist:
    replace_doc_chunks(doc_id, chunks)
  return {"ok": True, "chunks": len(chunks), "dims": len(vectors[0]) if vectors else 0, "chunk_rows": chunks}


async def upsert_document(
  params: Params,
  *,
  title: str,
  text: str,
  tags: list[str] | None = None,
  doc_id: str | None = None,
  embed_config: Any | None = None,
  reindex: bool = True,
) -> dict[str, Any]:
  text = (text or "").strip()
  title = (title or "Untitled").strip()
  if not text:
    return {"ok": False, "error": "text is empty"}
  if len(text) > _MAX_DOC_CHARS:
    text = text[:_MAX_DOC_CHARS]

  docs = _load_docs(params)
  did = doc_id or f"doc_{uuid.uuid4().hex[:10]}"
  entry = {
    "id": did,
    "title": title,
    "text": text,
    "tags": tags or [],
    "at": int(time.time()),
    "embedded": False,
    "chunk_count": 0,
  }

  replaced = False
  for i, d in enumerate(docs):
    if d.get("id") == did:
      docs[i] = entry
      replaced = True
      break
  if not replaced:
    docs.insert(0, entry)
  _save_docs(params, docs)

  embed_result: dict[str, Any] = {}
  if reindex and embed_config is not None:
    embed_result = await index_document_vectors(params, did, title, text, embed_config=embed_config)
    if embed_result.get("ok"):
      entry["embedded"] = True
      entry["chunk_count"] = embed_result.get("chunks", 0)
      for i, d in enumerate(docs):
        if d.get("id") == did:
          docs[i] = entry
          break
      _save_docs(params, docs)

  return {"ok": True, "document": {"id": did, "title": title}, "embedding": embed_result}


def remove_document(params: Params, doc_id: str) -> dict[str, Any]:
  docs = _load_docs(params)
  new_docs = [d for d in docs if d.get("id") != doc_id]
  _save_docs(params, new_docs)
  remove_doc_chunks(doc_id)
  return {"ok": True, "removed": len(docs) - len(new_docs)}


def search_documents_keyword(params: Params, query: str, *, limit: int = 5, tags: list[str] | None = None) -> dict[str, Any]:
  q_tokens = _tokenize(query)
  if not q_tokens:
    return {"ok": False, "error": "query too short"}
  tag_set = {t.lower() for t in (tags or []) if t}
  docs = _load_docs(params)
  scored: list[tuple[float, dict[str, Any]]] = []
  for doc in docs:
    doc_tags = {str(t).lower() for t in (doc.get("tags") or [])}
    if tag_set and not (tag_set & doc_tags):
      continue
    text = f"{doc.get('title', '')} {doc.get('text', '')} {' '.join(doc.get('tags', []))}"
    d_tokens = _tokenize(text)
    if not d_tokens:
      continue
    overlap = len(q_tokens & d_tokens)
    if overlap == 0:
      continue
    score = overlap / max(len(q_tokens), 1)
    scored.append((score, doc))
  scored.sort(key=lambda x: x[0], reverse=True)
  hits = []
  for score, doc in scored[:limit]:
    hits.append({
      "id": doc.get("id"),
      "title": doc.get("title"),
      "score": round(score, 3),
      "snippet": doc.get("text", "")[:800],
      "method": "keyword",
    })
  return {"ok": True, "query": query, "hits": hits, "method": "keyword"}


async def search_documents(
  params: Params,
  query: str,
  *,
  limit: int = 5,
  embed_config: Any | None = None,
  tags: list[str] | None = None,
) -> dict[str, Any]:
  """Hybrid keyword + vector search with reciprocal rank fusion."""
  kw_res = search_documents_keyword(params, query, limit=limit * 2, tags=tags)
  kw_hits = kw_res.get("hits") or []

  vec_hits: list[dict[str, Any]] = []
  from ai.core.llm.embedding import embed_texts_with_failover, load_embedding_config_chain
  chain_ok = bool(load_embedding_config_chain(params))
  configured = (embed_config is not None and embed_config.is_configured) or chain_ok
  if configured and chunk_count() > 0:
    vectors, _cfg, err = await embed_texts_with_failover(params, [query], source="rag_search")
    if not err and vectors:
      vec_hits = search_vector_chunks(vectors[0], limit=limit * 2)
      for h in vec_hits:
        h["method"] = "vector"

  if not vec_hits:
    return kw_res

  if not kw_hits:
    return {"ok": True, "query": query, "hits": vec_hits[:limit], "method": "vector"}

  scores: dict[str, float] = {}
  meta: dict[str, dict[str, Any]] = {}
  for rank, h in enumerate(kw_hits):
    doc_id = str(h.get("id", f"kw_{rank}"))
    scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (60 + rank + 1)
    meta[doc_id] = h
  for rank, h in enumerate(vec_hits):
    doc_id = str(h.get("id", f"vec_{rank}"))
    scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (60 + rank + 1)
    if doc_id not in meta:
      meta[doc_id] = h
    else:
      meta[doc_id] = {**meta[doc_id], **h, "score_kw": meta[doc_id].get("score"), "score_vec": h.get("score")}

  merged = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]
  hits = []
  for doc_id, rrf in merged:
    h = dict(meta[doc_id])
    h["score"] = round(rrf, 4)
    h["method"] = "hybrid"
    hits.append(h)

  return {"ok": True, "query": query, "hits": hits, "method": "hybrid"}


async def reindex_all(
  params: Params,
  embed_config: Any = None,
  *,
  on_progress: Any | None = None,
) -> dict[str, Any]:
  import asyncio

  from ai.common.rag_config import rag_max_chunks
  from ai.tools.domains.core.rag_vectors import chunk_count, write_all_chunks

  cap = rag_max_chunks()
  docs = _load_docs(params)
  for doc in docs:
    doc["embedded"] = False
    doc["chunk_count"] = 0
  ok_n = 0
  errors: list[str] = []
  all_rows: list[dict[str, Any]] = []
  total = len(docs)
  for i, doc in enumerate(docs):
    res = await index_document_vectors(
      params,
      doc.get("id", ""),
      doc.get("title", ""),
      doc.get("text", ""),
      embed_config=embed_config,
      persist=False,
    )
    if res.get("ok"):
      ok_n += 1
      doc["embedded"] = True
      doc["chunk_count"] = res.get("chunks", 0)
      rows = res.get("chunk_rows") or []
      if rows:
        all_rows = rows + all_rows
        if len(all_rows) > cap:
          all_rows = all_rows[:cap]
    else:
      errors.append(f"{doc.get('id')}: {res.get('error', '?')}")
      doc["embedded"] = False
      doc["chunk_count"] = 0
    if on_progress:
      try:
        on_progress(i + 1, total, ok_n)
      except Exception:
        pass
    await asyncio.sleep(0)
  if not all_rows:
    return {
      "ok": False,
      "indexed": ok_n,
      "total": total,
      "errors": errors[:5] or ["no vectors produced"],
      "vector_chunks": chunk_count(),
    }
  write_all_chunks(all_rows)
  vector_index_meta(rebuild=True)
  _save_docs(params, docs)
  return {"ok": True, "indexed": ok_n, "total": total, "errors": errors[:5], "vector_chunks": len(all_rows)}


def format_rag_prompt(params: Params, query: str = "", limit: int | None = None, hits: list[dict[str, Any]] | None = None) -> str:
  hit_limit = limit if limit is not None else rag_search_limit()
  if hits is None:
    if query:
      res = search_documents_keyword(params, query, limit=hit_limit)
      hits = res.get("hits") or []
    else:
      docs = _load_docs(params)[:hit_limit]
      hits = [{"title": d.get("title"), "snippet": d.get("text", "")[:600]} for d in docs]
  if not hits:
    return ""
  parts = ["# Knowledge base excerpts\n"]
  for h in hits:
    method = h.get("method", "")
    suffix = f" ({method})" if method else ""
    parts.append(f"### {h.get('title', 'Doc')}{suffix}\n{h.get('snippet', '')}")
  return "\n\n".join(parts)
