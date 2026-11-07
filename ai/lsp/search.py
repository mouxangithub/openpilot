"""Symbol and document search helpers for the LSP index.

Search is intentionally simple: exact/prefix/fuzzy matching over indexed
symbol names and container names. Result ranking is left to callers.
"""

from __future__ import annotations

from typing import Any

from ai.lsp.index import Symbol, SymbolIndex


def _matches(symbol: Symbol, query: str) -> bool:
  q = query.lower()
  if q in symbol.name.lower():
    return True
  if q in symbol.container_name.lower():
    return True
  if q in symbol.detail.lower():
    return True
  return False


def search_symbols(
  index: SymbolIndex,
  query: str,
  *,
  kind: int | None = None,
  uri_prefix: str | None = None,
  limit: int = 50,
) -> list[Symbol]:
  """Return indexed symbols matching `query`."""
  results: list[Symbol] = []
  for symbol in index.all_symbols():
    if kind is not None and symbol.kind != kind:
      continue
    if uri_prefix is not None and not symbol.uri.startswith(uri_prefix):
      continue
    if not _matches(symbol, query):
      continue
    results.append(symbol)
    if len(results) >= limit:
      break
  return results


def search_documents(
  file_paths: list[str],
  query: str,
  *,
  limit: int = 20,
) -> list[str]:
  """Return file paths whose names contain `query`."""
  q = query.lower()
  results = [p for p in file_paths if q in p.lower()]
  return results[:limit]


def format_symbol(symbol: Symbol) -> str:
  """Compact one-line rendering of a symbol."""
  rng = symbol.range.get("start", {})
  line = rng.get("line", 0) + 1
  char = rng.get("character", 0) + 1
  return f"{symbol.name} ({symbol.kind_name()}) at {symbol.uri}:{line}:{char}"
