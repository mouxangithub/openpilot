"""Publish / forge settings for op助手 code release."""

from __future__ import annotations

import json
from typing import Any

from ai.common.repo_targets import ASSISTANT_REPO_URL

SETTINGS_KEY = "ai_publish_settings"

DEFAULT_SETTINGS: dict[str, Any] = {
  "assistant_publish": {
    "fixed_upstream": True,
    "repo_url": ASSISTANT_REPO_URL,
    "default_branch": "main",
    "forge": "github",
  },
  "project_publish": {
    "default_mode": "current_remote",
    "forks": {},
  },
  "issue_publish": {
    "default_unit": "assistant",
    "default_mode": "assistant_upstream",
    "default_template": "bug",
    "dedupe_search": True,
  },
}


def _load_raw() -> dict[str, Any]:
  try:
    from ai.common.config_store import get_config_store

    raw = get_config_store().get(SETTINGS_KEY, "")
    if not raw:
      return {}
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="replace")
    data = json.loads(str(raw))
    return data if isinstance(data, dict) else {}
  except Exception:
    return {}


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
  out = dict(base)
  for key, val in patch.items():
    if isinstance(val, dict) and isinstance(out.get(key), dict):
      out[key] = _deep_merge(out[key], val)
    else:
      out[key] = val
  return out


def get_publish_settings() -> dict[str, Any]:
  merged = _deep_merge(DEFAULT_SETTINGS, _load_raw())
  return {"ok": True, "settings": merged}


def save_publish_settings(patch: dict[str, Any]) -> dict[str, Any]:
  from ai.common.storage import write_param

  current = _deep_merge(DEFAULT_SETTINGS, _load_raw())
  updated = _deep_merge(current, patch if isinstance(patch, dict) else {})
  write_param(None, SETTINGS_KEY, json.dumps(updated, ensure_ascii=False))
  return {"ok": True, "settings": updated}


def assistant_upstream() -> dict[str, Any]:
  s = get_publish_settings()["settings"]["assistant_publish"]
  return {
    "repo_url": s.get("repo_url") or ASSISTANT_REPO_URL,
    "default_branch": s.get("default_branch") or "main",
    "forge": s.get("forge") or "github",
    "fixed_upstream": bool(s.get("fixed_upstream", True)),
  }


def project_default_mode() -> str:
  s = get_publish_settings()["settings"]["project_publish"]
  mode = str(s.get("default_mode") or "current_remote").strip().lower()
  return mode if mode in ("current_remote", "user_fork") else "current_remote"


def project_fork_config(unit_id: str) -> dict[str, Any] | None:
  forks = get_publish_settings()["settings"]["project_publish"].get("forks") or {}
  cfg = forks.get(unit_id)
  return cfg if isinstance(cfg, dict) else None
