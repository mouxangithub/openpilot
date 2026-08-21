"""Load built-in RAG documents from data/rag/builtin/*.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_BUILTIN_DIR = Path(__file__).resolve().parents[2] / "data" / "rag" / "builtin"


def load_json_builtin_docs() -> list[dict[str, Any]]:
  """Load static builtin docs shipped as JSON under data/rag/builtin/."""
  if not _BUILTIN_DIR.is_dir():
    return []
  docs: list[dict[str, Any]] = []
  for path in sorted(_BUILTIN_DIR.glob("*.json")):
    try:
      raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
      continue
    if isinstance(raw, list):
      docs.extend([d for d in raw if isinstance(d, dict) and d.get("id")])
    elif isinstance(raw, dict) and raw.get("id"):
      docs.append(raw)
  return docs
