"""Param read/write policy for op助手 tools."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from ai.tools.catalog_builder import build_merged_catalog

WRITE_TIERS = frozenset({
  "write_offroad_ui",
  "write_offroad_tune",
  "write_offroad_dev",
})

FORBIDDEN_TIERS = frozenset({"write_forbidden"})
REDACTED_TIERS = frozenset({"read_redacted"})

# Params that enable AI/human to directly command actuators — the only write block in open mode.
_DIRECT_CONTROL_PARAM_KEYS = frozenset({
  "JoystickDebugMode",
  "LongitudinalManeuverMode",
})

_MAX_TUNE_WRITES_PER_CALL = 3

_SENSITIVE_EXTRA = frozenset({
  "ai_api_key",
  "DongleId",
  "ApiCache_Device",
  "ApiCache_NavDestinations",
  "GithubSshKeys",
  "SecOCKey",
})


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, dict[str, Any]]:
  return build_merged_catalog()


def get_param_meta(key: str) -> dict[str, Any] | None:
  return load_catalog().get(key)


def is_redacted(key: str) -> bool:
  """Open mode: never redact param reads."""
  return False


def can_write(key: str, *, admin: bool = False) -> tuple[bool, str]:
  if admin:
    if key in _DIRECT_CONTROL_PARAM_KEYS:
      return False, f"Param '{key}' enables direct vehicle control; AI cannot write it."
    return True, ""

  meta = get_param_meta(key)
  if meta is None:
    return False, f"Param '{key}' is not in the AI write catalog."
  tier = meta.get("tier", "")
  if tier in FORBIDDEN_TIERS:
    return False, f"Param '{key}' is forbidden for AI writes ({tier})."
  if tier not in WRITE_TIERS:
    return False, f"Param '{key}' is read-only for AI ({tier})."
  return True, ""


def is_tune_param(key: str) -> bool:
  meta = get_param_meta(key)
  if not meta:
    return False
  return meta.get("tier") == "write_offroad_tune"


def validate_write_batch(writes: dict[str, Any], *, admin: bool = False) -> tuple[bool, str]:
  if not writes:
    return False, "No params to write."
  if not admin:
    tune_count = sum(1 for k in writes if is_tune_param(k))
    if tune_count > _MAX_TUNE_WRITES_PER_CALL:
      return False, f"At most {_MAX_TUNE_WRITES_PER_CALL} driving-tune params per call."
  for key in writes:
    ok, reason = can_write(key, admin=admin)
    if not ok:
      return False, reason
  return True, ""


def catalog_summary() -> list[dict[str, Any]]:
  return [
    {
      "key": k,
      "tier": v.get("tier"),
      "section": v.get("section"),
      "summary": v.get("summary"),
      "brands": v.get("brands"),
      "requires": v.get("requires"),
    }
    for k, v in sorted(load_catalog().items())
  ]
