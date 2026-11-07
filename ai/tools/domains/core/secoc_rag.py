"""SecOC reference docs RAG (optskug/docs + RH850_P1m-E)."""

from __future__ import annotations

from typing import Any

try:
  from ai.tools.domains.core.secoc_rag_pages import SECOC_RAG_PAGES
except ImportError:
  SECOC_RAG_PAGES: list[dict[str, Any]] = []

SECOC_RAG: list[dict[str, Any]] = SECOC_RAG_PAGES
