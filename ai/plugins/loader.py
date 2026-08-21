"""Load optional op助手 plugins that register extra tools."""

from __future__ import annotations

import importlib
import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("aid.plugins")

_REGISTRY = Path(__file__).resolve().parent / "registry.json"


@lru_cache(maxsize=1)
def _load_registry() -> dict[str, Any]:
  if not _REGISTRY.is_file():
    return {"plugins": []}
  with _REGISTRY.open(encoding="utf-8") as f:
    return json.load(f)


def load_plugin_modules() -> list[Any]:
  mods = []
  for entry in _load_registry().get("plugins") or []:
    if not entry.get("enabled", True):
      continue
    mod_path = entry.get("module", "")
    if not mod_path:
      continue
    try:
      mods.append(importlib.import_module(mod_path))
    except Exception as e:
      log.warning(f"plugin load failed {mod_path}: {e}")
  return mods


def collect_plugin_tool_meta() -> dict[str, dict[str, Any]]:
  out: dict[str, dict[str, Any]] = {}
  for mod in load_plugin_modules():
    meta = getattr(mod, "TOOL_META", None)
    if isinstance(meta, dict):
      out.update(meta)
  return out


def collect_plugin_schemas() -> list[dict[str, Any]]:
  schemas: list[dict[str, Any]] = []
  for mod in load_plugin_modules():
    items = getattr(mod, "TOOL_SCHEMAS", None)
    if isinstance(items, list):
      schemas.extend(items)
  return schemas


def make_plugin_handlers(ctx: dict[str, Any]) -> dict[str, Callable[..., Any]]:
  handlers: dict[str, Callable[..., Any]] = {}
  for mod in load_plugin_modules():
    factory = getattr(mod, "make_handlers", None)
    if callable(factory):
      part = factory(ctx)
      if isinstance(part, dict):
        handlers.update(part)
  return handlers


def list_plugins() -> dict[str, Any]:
  entries = []
  for entry in _load_registry().get("plugins") or []:
    mod_path = entry.get("module", "")
    loaded = False
    tool_count = 0
    if entry.get("enabled", True) and mod_path:
      try:
        mod = importlib.import_module(mod_path)
        loaded = True
        tool_count = len(getattr(mod, "TOOL_META", {}) or {})
      except Exception:
        loaded = False
    entries.append({**entry, "loaded": loaded, "tool_count": tool_count})
  return {"ok": True, "plugins": entries, "registry": str(_REGISTRY)}
