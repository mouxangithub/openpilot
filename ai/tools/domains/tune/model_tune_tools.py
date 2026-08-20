"""NN model tuning params (CameraOffset, PlanplusControl) — modeld_v2."""

from __future__ import annotations

from typing import Any

from openpilot.common.params import Params

MODEL_TUNE_KEYS = ("CameraOffset", "PlanplusControl")


def get_model_tune_settings(params: Params | None = None) -> dict[str, Any]:
  params = params or Params()
  out: dict[str, Any] = {}
  for key in MODEL_TUNE_KEYS:
    try:
      out[key] = params.get(key, return_default=True)
    except Exception:
      val = params.get(key)
      if isinstance(val, bytes):
        val = val.decode(errors="replace")
      out[key] = val
  return {
    "ok": True,
    "section": "Models",
    "settings": out,
    "hint": "CameraOffset: lateral camera offset (m). PlanplusControl: Plan+ longitudinal gain (default 1.0). Active custom NN bundle recommended.",
  }


def apply_model_tune_writes(params: Params, writes: dict[str, Any]) -> dict[str, Any]:
  allowed = {k: v for k, v in writes.items() if k in MODEL_TUNE_KEYS}
  if not allowed:
    return {"ok": False, "error": "No valid model tune keys"}
  for key, val in allowed.items():
    params.put(key, str(val))
  return {"ok": True, "applied": allowed, "current": get_model_tune_settings(params)}


def preview_model_tune_writes(params: Params, writes: dict[str, Any]) -> dict[str, Any]:
  from ai.tools.diagnostics_tools import diff_params
  allowed = {k: v for k, v in writes.items() if k in MODEL_TUNE_KEYS}
  if not allowed:
    return {"ok": False, "error": "No valid model tune keys"}
  return diff_params(params, allowed)
