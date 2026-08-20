"""OP Agent consumer API helpers."""

from __future__ import annotations

from typing import Any

from ai.common.consumer_lexicon import lexicon_snapshot, preview_param_writes
from ai.tools.domains.platform.consumer_wizards import get_consumer_wizard, list_consumer_wizards


def consumer_bootstrap_payload() -> dict[str, Any]:
  return {
    "wizards": list_consumer_wizards(),
    "lexicon_count": lexicon_snapshot(limit=5).get("count", 0),
    "product_name": "OP",
    "tagline": "像跟懂车的朋友聊天一样调优、适配、排障",
  }


def start_wizard_payload(wizard_id: str) -> dict[str, Any]:
  w = get_consumer_wizard(wizard_id)
  if not w:
    return {"ok": False, "error": f"Unknown wizard: {wizard_id}"}
  return {
    "ok": True,
    "wizard": w,
    "workflow": w.get("workflow_id"),
    "message": w.get("starter_prompt"),
    "consumer_mode": True,
  }


def preview_params_consumer(proposed: dict[str, Any]) -> dict[str, Any]:
  if not isinstance(proposed, dict) or not proposed:
    return {"ok": False, "error": "params object required"}
  preview = preview_param_writes(proposed)
  return preview


def enrich_write_preview(preview: Any) -> dict[str, Any]:
  """Add consumer rows to a write_params pending preview."""
  if not isinstance(preview, dict):
    return {"ok": True, "raw": preview}
  changes = preview.get("changes") or preview
  if isinstance(changes, dict) and changes and all(isinstance(v, dict) and "before" in v for v in changes.values()):
    consumer = preview_param_writes({}, changes=changes)
    return {"ok": True, "consumer": consumer, "raw": preview}
  # write_params preview may be {key: {before, after}}
  if isinstance(preview, dict):
    consumer = preview_param_writes({}, changes=preview)
    return {"ok": True, "consumer": consumer, "raw": preview}
  return {"ok": True, "raw": preview}
