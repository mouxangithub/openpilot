"""Admin mode for op助手 — full read/write on openpilot + AGNOS paths."""

from __future__ import annotations

from openpilot.common.params import Params


def is_admin_mode(params: Params | None = None) -> bool:
  """Open mode: all restrictions lifted except direct vehicle control."""
  p = params or Params()
  try:
    return p.get_bool("ai_admin_mode")
  except Exception:
    raw = p.get("ai_admin_mode")
    if raw is None:
      return True
    if isinstance(raw, bytes):
      raw = raw.decode(errors="replace")
    return str(raw).strip().lower() not in ("0", "false", "no", "")
