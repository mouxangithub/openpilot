"""Lightweight notification queue for scheduler / critical events."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from ai.system.paths import notifications_path

_MAX = 30


def _load() -> list[dict[str, Any]]:
  p = notifications_path()
  if not p.is_file():
    return []
  try:
    data = json.loads(p.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []
  except Exception:
    return []


def _save(items: list[dict[str, Any]]) -> None:
  p = notifications_path()
  p.parent.mkdir(parents=True, exist_ok=True)
  p.write_text(json.dumps(items[:_MAX], ensure_ascii=False), encoding="utf-8")


def push_notification(title: str, body: str, *, level: str = "info") -> dict[str, Any]:
  items = _load()
  entry = {
    "id": f"n_{int(time.time() * 1000)}",
    "title": title[:120],
    "body": body[:500],
    "level": level,
    "at": int(time.time()),
    "read": False,
  }
  items.insert(0, entry)
  _save(items)
  return entry


def list_notifications(*, unread_only: bool = False) -> dict[str, Any]:
  items = _load()
  if unread_only:
    items = [i for i in items if not i.get("read")]
  return {"ok": True, "notifications": items[:_MAX]}


def mark_notifications_read() -> dict[str, Any]:
  items = _load()
  for i in items:
    i["read"] = True
  _save(items)
  return {"ok": True, "marked": len(items)}
