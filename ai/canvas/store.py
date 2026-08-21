"""Canvas artifacts — structured visual outputs per session (JSONL persistent)."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from ai.system.paths import workspace_path

_MAX_PER_SESSION = 40
_artifacts: dict[str, list[dict[str, Any]]] = {}


def _session_key(session_id: str) -> str:
  return session_id or "__global__"


def _artifact_path(session_id: str) -> Path:
  sid = _session_key(session_id).replace("/", "_").replace("\\", "_")[:96]
  return workspace_path("artifacts", f"{sid}.jsonl", mkdir=True)


def _load_session_from_disk(session_id: str) -> list[dict[str, Any]]:
  key = _session_key(session_id)
  if key in _artifacts:
    return _artifacts[key]
  path = _artifact_path(session_id)
  items: list[dict[str, Any]] = []
  if path.is_file():
    try:
      with path.open(encoding="utf-8") as f:
        for line in f:
          line = line.strip()
          if not line:
            continue
          try:
            items.append(json.loads(line))
          except json.JSONDecodeError:
            continue
    except OSError:
      pass
  _artifacts[key] = items[-_MAX_PER_SESSION:]
  return _artifacts[key]


def _persist_artifact(session_id: str, artifact: dict[str, Any]) -> None:
  path = _artifact_path(session_id)
  try:
    with path.open("a", encoding="utf-8") as f:
      f.write(json.dumps(artifact, ensure_ascii=False, default=str) + "\n")
  except OSError:
    pass


def add_artifact(
  session_id: str,
  *,
  kind: str,
  title: str,
  payload: dict[str, Any] | None = None,
  source_tool: str = "",
) -> dict[str, Any]:
  key = _session_key(session_id)
  items = _load_session_from_disk(session_id)
  artifact = {
    "id": f"art_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}",
    "kind": kind,
    "title": title,
    "payload": payload or {},
    "sourceTool": source_tool,
    "createdAt": int(time.time()),
  }
  items.append(artifact)
  if len(items) > _MAX_PER_SESSION:
    items[:] = items[-_MAX_PER_SESSION:]
  _artifacts[key] = items
  _persist_artifact(session_id, artifact)
  return artifact


def list_artifacts(session_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
  items = _load_session_from_disk(session_id)
  return list(reversed(items[-limit:]))


def get_artifact(session_id: str, artifact_id: str) -> dict[str, Any] | None:
  for a in _load_session_from_disk(session_id):
    if a.get("id") == artifact_id:
      return a
  return None


def maybe_capture_tool_artifact(
  session_id: str,
  tool_name: str,
  result: Any,
) -> dict[str, Any] | None:
  if not isinstance(result, dict):
    return None
  if result.get("canvas"):
    c = result["canvas"]
    if isinstance(c, dict):
      return add_artifact(
        session_id,
        kind=str(c.get("kind") or "report"),
        title=str(c.get("title") or tool_name),
        payload=c.get("payload") if isinstance(c.get("payload"), dict) else c,
        source_tool=tool_name,
      )
  for key, kind in (
    ("report", "report"),
    ("chart", "chart"),
    ("html", "html"),
    ("markdown", "markdown"),
    ("tune_passport", "tune"),
    ("diff", "file"),
    ("filePath", "file"),
    ("path", "file"),
  ):
    if key in result and result[key]:
      title = str(result.get("title") or result.get("name") or tool_name)
      payload = {key: result[key], **{k: result[k] for k in ("summary", "metrics", "preview", "diff") if k in result}}
      if key in ("filePath", "path"):
        payload["filePath"] = result[key]
      return add_artifact(
        session_id,
        kind=kind,
        title=title,
        payload=payload,
        source_tool=tool_name,
      )
  return None


async def notify_artifact(session_id: str, artifact: dict[str, Any]) -> None:
  try:
    from ai.core.sync.hub import notify_canvas_artifact
    await notify_canvas_artifact(session_id, artifact)
  except Exception:
    pass
