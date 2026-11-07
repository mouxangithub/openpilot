"""Admin mode for op助手 — full read/write on openpilot + AGNOS paths."""

from __future__ import annotations

from openpilot.common.params import Params


def is_admin_mode(params: Params | None = None) -> bool:
  """Open mode: all restrictions lifted except direct vehicle control."""
  from ai.common.storage import read_param_bool
  return read_param_bool(params, "ai_admin_mode", default=True)
