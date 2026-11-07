"""openpilot Wiki RAG integration."""

from __future__ import annotations

from typing import Any

try:
  from ai.tools.domains.core.wiki_rag_pages import WIKI_RAG_PAGES
except ImportError:
  WIKI_RAG_PAGES: list[dict[str, Any]] = []

WIKI_RAG: list[dict[str, Any]] = WIKI_RAG_PAGES
