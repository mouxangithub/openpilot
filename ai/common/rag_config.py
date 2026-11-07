"""RAG / knowledge-base limits (device-tunable via ai_* params)."""

from __future__ import annotations

from typing import Any

from ai.common.storage import read_param

# Generous defaults — full wiki + large personal libraries on comma 3.
_DEFAULT_MAX_DOCS = 20_000
_DEFAULT_MAX_CHUNKS = 100_000
_DEFAULT_MAX_TOTAL_CHARS = 50_000_000
_DEFAULT_TOOL_SEARCH_LIMIT = 20
_DEFAULT_WIKI_MAX_FILES = 0  # 0 = no per-repo cap
_TOOL_SEARCH_LIMIT_MAX = 50


def _int_param(key: str, default: int, *, lo: int = 0, hi: int = 10_000_000) -> int:
  try:
    raw = read_param(None, key, str(default))
    val = int(str(raw or default).strip())
    return max(lo, min(hi, val))
  except (TypeError, ValueError):
    return default


def rag_max_docs() -> int:
  return _int_param("ai_rag_max_docs", _DEFAULT_MAX_DOCS, lo=64, hi=100_000)


def rag_max_chunks() -> int:
  return _int_param("ai_rag_max_chunks", _DEFAULT_MAX_CHUNKS, lo=256, hi=500_000)


def rag_max_total_chars() -> int:
  return _int_param("ai_rag_max_total_chars", _DEFAULT_MAX_TOTAL_CHARS, lo=100_000, hi=200_000_000)


def rag_tool_search_limit() -> int:
  """Default hit count when the model calls search_knowledge_base without limit."""
  return _int_param("ai_rag_search_limit", _DEFAULT_TOOL_SEARCH_LIMIT, lo=1, hi=_TOOL_SEARCH_LIMIT_MAX)


def rag_tool_search_limit_cap() -> int:
  return _TOOL_SEARCH_LIMIT_MAX


# Back-compat alias for older imports.
def rag_search_limit() -> int:
  return rag_tool_search_limit()


def wiki_max_files_per_repo() -> int:
  """0 means ingest all markdown pages from a wiki/repo source."""
  return _int_param("ai_wiki_max_files_per_repo", _DEFAULT_WIKI_MAX_FILES, lo=0, hi=50_000)


def rag_limits() -> dict[str, int]:
  return {
    "max_docs": rag_max_docs(),
    "max_chunks": rag_max_chunks(),
    "max_total_chars": rag_max_total_chars(),
  }


def rag_settings() -> dict[str, Any]:
  return {
    "ragSearchLimit": rag_tool_search_limit(),
    "ragToolSearchLimitMax": _TOOL_SEARCH_LIMIT_MAX,
    "ragMaxDocs": rag_max_docs(),
    "ragMaxChunks": rag_max_chunks(),
    "wikiMaxFilesPerRepo": wiki_max_files_per_repo(),
  }
