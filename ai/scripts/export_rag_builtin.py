#!/usr/bin/env python3
"""Export static builtin RAG docs from rag_seed to data/rag/builtin/*.json."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "tools" / "domains" / "core" / "rag_seed.py"
OUT = ROOT / "data" / "rag" / "builtin"


def main() -> int:
  text = SEED.read_text(encoding="utf-8")
  m = re.search(r"_BUILTIN_DOCS:\s*list\[.*?\]\s*=\s*\[", text)
  if not m:
    print("could not find _BUILTIN_DOCS")
    return 1
  # Evaluate only the static dict literals before splats
  start = m.end()
  depth = 1
  i = start
  static_part = []
  while i < len(text) and depth > 0:
    ch = text[i]
    if ch == "[":
      depth += 1
    elif ch == "]":
      depth -= 1
      if depth == 0:
        break
    if depth == 1 and text[i:i + 1] == "*":
      break
    static_part.append(ch)
    i += 1
  blob = "[" + "".join(static_part) + "]"
  blob = re.sub(r",\s*$", "", blob.strip())
  docs = eval(blob, {"__builtins__": {}}, {})  # noqa: S307 — maintainer export script
  OUT.mkdir(parents=True, exist_ok=True)
  for doc in docs:
    if not isinstance(doc, dict) or not doc.get("id"):
      continue
    path = OUT / f"{doc['id']}.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {path.name}")
  print(f"exported {len(docs)} docs")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
