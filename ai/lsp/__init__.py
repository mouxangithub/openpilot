"""LSP — Language Server Protocol integration for op助手.

A lightweight async JSON-RPC client plus symbol indexing and search helpers.
"""

from __future__ import annotations

from ai.lsp.client import LspClient
from ai.lsp.index import Symbol, SymbolIndex
from ai.lsp.search import search_documents, search_symbols
from ai.lsp.server_manager import LspServerManager
from ai.lsp.errors import LspError, NO_PROVIDER, WORKSPACE_OUTSIDE, INVALID_RESPONSE, TIMEOUT

__all__ = [
  "LspClient",
  "LspServerManager",
  "Symbol",
  "SymbolIndex",
  "search_documents",
  "search_symbols",
  "LspError",
  "NO_PROVIDER",
  "WORKSPACE_OUTSIDE",
  "INVALID_RESPONSE",
  "TIMEOUT",
]
