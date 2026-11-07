"""Evolved tool description overrides (Hermes phase-2 style)."""

from __future__ import annotations

import json
import time
from typing import Any

from openpilot.common.params import Params

from ai.common.storage import read_param, write_param

_OVERRIDES_KEY = "ai_tool_desc_overrides"
_MAX_OVERRIDES = 48


def _load(params: Params | None = None) -> dict[str, str]:
  params = params or Params()
  try:
    raw = read_param(params, _OVERRIDES_KEY)
    if not raw:
      return {}
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="replace")
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}
  except Exception:
    return {}


def _save(params: Params, data: dict[str, str]) -> None:
  items = list(data.items())[:_MAX_OVERRIDES]
  write_param(params, _OVERRIDES_KEY, json.dumps(dict(items), ensure_ascii=False))


def list_tool_desc_overrides(params: Params | None = None) -> dict[str, Any]:
  data = _load(params)
  return {"ok": True, "overrides": data, "count": len(data)}


def set_tool_desc_override(params: Params, tool_name: str, description: str, *, source: str = "manual") -> dict[str, Any]:
  name = (tool_name or "").strip()
  desc = (description or "").strip()
  if not name or not desc:
    return {"ok": False, "error": "tool_name and description required"}
  data = _load(params)
  data[name] = desc
  data[f"__meta_{name}"] = json.dumps({"source": source, "at": int(time.time())}, ensure_ascii=False)
  _save(params, data)
  return {"ok": True, "tool": name, "chars": len(desc)}


def apply_tool_schema_overrides(schemas: list[dict[str, Any]], params: Params | None = None) -> list[dict[str, Any]]:
  overrides = _load(params)
  if not overrides:
    return schemas
  out: list[dict[str, Any]] = []
  for schema in schemas:
    fn = schema.get("function") or {}
    name = fn.get("name", "")
    if name and name in overrides:
      patched = dict(schema)
      patched_fn = dict(fn)
      patched_fn["description"] = overrides[name]
      patched["function"] = patched_fn
      out.append(patched)
    else:
      out.append(schema)
  return out


def propose_tool_desc_from_trace(
  params: Params,
  *,
  tool_name: str,
  current_description: str,
  error_snippet: str,
  reflection: str = "",
) -> dict[str, Any]:
  """Build improved tool description text (caller may use LLM reflection)."""
  name = (tool_name or "").strip()
  if not name:
    return {"ok": False, "error": "tool_name required"}
  lines = [
    current_description.strip(),
    "",
    f"Evolved hint ({name}):",
    "- Check preconditions before calling.",
    "- On failure, narrow scope and report actionable next step.",
  ]
  if error_snippet:
    lines.append(f"- Known failure pattern: {error_snippet[:200]}")
  if reflection:
    lines.append(f"- Reflection: {reflection[:400]}")
  improved = "\n".join(lines).strip()
  if len(improved) > 1200:
    improved = improved[:1200] + "…"
  return {"ok": True, "tool": name, "description": improved, "needs_approval": True}
