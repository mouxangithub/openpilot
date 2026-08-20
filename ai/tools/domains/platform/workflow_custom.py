"""User-editable custom workflows (WorkBuddy workflow editor)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai.system.paths import workspace_path
from ai.tools.domains.platform.workflows import WORKFLOWS, list_workflows

_CUSTOM_PATH: Path | None = None


def custom_path() -> Path:
  global _CUSTOM_PATH
  if _CUSTOM_PATH is None:
    d = workspace_path("workflows", mkdir=True)
    _CUSTOM_PATH = d / "custom.json"
  return _CUSTOM_PATH


def load_custom() -> dict[str, dict[str, Any]]:
  path = custom_path()
  if not path.is_file():
    return {}
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}
  except (OSError, json.JSONDecodeError):
    return {}


def save_custom(workflows: dict[str, dict[str, Any]]) -> dict[str, Any]:
  path = custom_path()
  cleaned: dict[str, dict[str, Any]] = {}
  for wid, w in (workflows or {}).items():
    if not isinstance(w, dict):
      continue
    wid = str(wid).strip()
    if not wid or wid in WORKFLOWS:
      continue
    cleaned[wid] = {
      "name": str(w.get("name") or wid),
      "mode": str(w.get("mode") or "execute"),
      "steps": list(w.get("steps") or []),
      "prompt": str(w.get("prompt") or ""),
      "custom": True,
    }
  try:
    path.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "count": len(cleaned), "path": str(path)}
  except OSError as e:
    return {"ok": False, "error": str(e)}


def list_all_workflows() -> list[dict[str, Any]]:
  builtin = list_workflows()
  custom = load_custom()
  out = list(builtin)
  for wid, w in custom.items():
    out.append({
      "id": wid,
      "name": w.get("name", wid),
      "mode": w.get("mode", "execute"),
      "steps": w.get("steps", []),
      "custom": True,
    })
  return out


def get_merged_workflow(workflow_id: str) -> dict[str, Any] | None:
  custom = load_custom()
  if workflow_id in custom:
    return custom[workflow_id]
  return WORKFLOWS.get(workflow_id)


def merged_system_prompt(workflow_id: str) -> str:
  w = get_merged_workflow(workflow_id)
  if not w:
    return ""
  steps = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(w.get("steps", [])))
  return (
    f"# Active workflow: {w.get('name', workflow_id)}\n"
    f"Follow these steps in order (use tools where noted):\n{steps}\n\n"
    f"{w.get('prompt', '')}"
  )
