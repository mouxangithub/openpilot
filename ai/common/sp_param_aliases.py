"""Legacy dp_* param names → openpilot Params equivalents."""

from __future__ import annotations

# DP-only keys that map to an existing openpilot Params key.
DP_TO_SP_PARAM_ALIASES: dict[str, str] = {
  "dp_dev_go_off_road": "OffroadMode",
}


def resolve_sp_param_key(key: str) -> str:
  return DP_TO_SP_PARAM_ALIASES.get(key, key)


def normalize_param_writes(writes: dict) -> dict:
  """Rewrite legacy DP keys to SP keys; last write wins on collision."""
  out: dict = {}
  for key, value in writes.items():
    out[resolve_sp_param_key(key)] = value
  return out


def is_dp_legacy_param(key: str) -> bool:
  return key in DP_TO_SP_PARAM_ALIASES
