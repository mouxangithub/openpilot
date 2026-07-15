"""AI token usage persistence with per-model and per-provider breakdown."""

from __future__ import annotations

import json
import time
from typing import Any

from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog

USAGE_KEY = "ai_usage_log"
_EMPTY_COUNTERS = {
  "calls": 0,
  "prompt_tokens": 0,
  "completion_tokens": 0,
  "total_tokens": 0,
}


def model_usage_key(provider: str, model: str) -> str:
  return f"{provider}::{model}"


def _empty_usage() -> dict[str, Any]:
  return {
    **_EMPTY_COUNTERS,
    "by_model": {},
    "by_provider": {},
    "history": [],
  }


def _normalize_usage(data: dict[str, Any]) -> dict[str, Any]:
  out = _empty_usage()
  for key in _EMPTY_COUNTERS:
    out[key] = int(data.get(key, 0) or 0)
  out["by_model"] = dict(data.get("by_model") or {})
  out["by_provider"] = dict(data.get("by_provider") or {})
  out["history"] = list(data.get("history") or [])
  return out


def load_usage(params: Params) -> dict[str, Any]:
  try:
    raw = params.get(USAGE_KEY)
    if raw:
      if isinstance(raw, bytes):
        raw = raw.decode()
      return _normalize_usage(json.loads(raw))
  except Exception:
    pass
  return _empty_usage()


def _bump_counters(target: dict[str, Any], usage: dict[str, Any]) -> None:
  target["calls"] = int(target.get("calls", 0) or 0) + 1
  target["prompt_tokens"] = int(target.get("prompt_tokens", 0) or 0) + int(usage.get("prompt_tokens", 0) or 0)
  target["completion_tokens"] = int(target.get("completion_tokens", 0) or 0) + int(usage.get("completion_tokens", 0) or 0)
  target["total_tokens"] = int(target.get("total_tokens", 0) or 0) + int(usage.get("total_tokens", 0) or 0)


def record_usage(
  params: Params,
  usage: dict[str, Any],
  *,
  provider: str = "",
  model: str = "",
  source: str = "chat",
) -> None:
  try:
    data = load_usage(params)
    _bump_counters(data, usage)

    provider = (provider or "unknown").strip() or "unknown"
    model = (model or "unknown").strip() or "unknown"
    model_key = model_usage_key(provider, model)

    by_model: dict[str, Any] = data.setdefault("by_model", {})
    model_bucket = by_model.get(model_key)
    if not isinstance(model_bucket, dict):
      model_bucket = {"provider": provider, "model": model, **_EMPTY_COUNTERS.copy()}
      by_model[model_key] = model_bucket
    else:
      model_bucket.setdefault("provider", provider)
      model_bucket.setdefault("model", model)
    _bump_counters(model_bucket, usage)

    by_provider: dict[str, Any] = data.setdefault("by_provider", {})
    provider_bucket = by_provider.get(provider)
    if not isinstance(provider_bucket, dict):
      provider_bucket = {"provider": provider, **_EMPTY_COUNTERS.copy()}
      by_provider[provider] = provider_bucket
    else:
      provider_bucket.setdefault("provider", provider)
    _bump_counters(provider_bucket, usage)

    entry = dict(usage)
    entry["time"] = int(time.time())
    entry["provider"] = provider
    entry["model"] = model
    entry["source"] = source
    history = data.get("history", [])
    history.append(entry)
    data["history"] = history[-200:]

    params.put(USAGE_KEY, json.dumps(data, ensure_ascii=False))
  except Exception as e:
    cloudlog.error(f"usage_log: failed to record usage: {e}")
