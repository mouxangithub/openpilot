"""Persisted agent enable/disable preferences."""

from __future__ import annotations

import json
from typing import Any

from ai.common.storage import read_param, write_param

_PARAM_KEY = "ai_agents_disabled"


def load_disabled_agent_ids(params: Any = None) -> set[str]:
  p = params
  if p is None:
    from openpilot.common.params import Params
    p = Params()
  try:
    raw = read_param(p, _PARAM_KEY)
    if not raw:
      return set()
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="replace")
    data = json.loads(raw)
    if isinstance(data, list):
      return {str(x).strip() for x in data if str(x).strip()}
  except Exception:
    pass
  return set()


def save_disabled_agent_ids(params: Any, disabled: list[str]) -> None:
  clean = sorted({str(x).strip() for x in disabled if str(x).strip()})
  write_param(params, _PARAM_KEY, json.dumps(clean, ensure_ascii=False))


def is_agent_enabled(agent_id: str, params: Any = None) -> bool:
  if not agent_id:
    return True
  return agent_id not in load_disabled_agent_ids(params)


def agents_enabled_payload(params: Any) -> dict[str, Any]:
  disabled = load_disabled_agent_ids(params)
  return {
    "disabled": sorted(disabled),
  }
