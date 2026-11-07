"""Headless (no builtin panel) detection for WebUI and device APIs."""

from __future__ import annotations

import os

HEADLESS_MODE_PARAM = "WebuiHeadlessMode"
VALID_HEADLESS_MODES = frozenset({"auto", "on", "off"})


def get_headless_mode_pref() -> str:
  if os.environ.get("WEBUI_DEV_PC") == "1":
    try:
      from webui.dev.mock_runtime import SIM
      mode = SIM.get("headless_mode")
      if mode in VALID_HEADLESS_MODES:
        return str(mode)
      return "on" if SIM.get("headless") else "auto"
    except Exception:
      return "auto"
  try:
    from openpilot.common.params import Params
    raw = Params().get(HEADLESS_MODE_PARAM) or "auto"
    return raw if raw in VALID_HEADLESS_MODES else "auto"
  except Exception:
    return "auto"


def has_builtin_display_hardware() -> bool:
  """Physical panel probe only — ignores user headless preference."""
  if os.environ.get("WEBUI_DEV_PC") == "1":
    return True
  try:
    from openpilot.common.hardware import COMMA_HARDWARE
    if not COMMA_HARDWARE:
      return True
    from openpilot.common.hardware.comma.hardware import probe_builtin_display
    return probe_builtin_display()
  except Exception:
    return True


def set_headless_mode_pref(mode: str) -> dict[str, object]:
  mode = (mode or "").strip().lower()
  if mode not in VALID_HEADLESS_MODES:
    return {"ok": False, "error": f"invalid headless mode: {mode}"}
  if mode == "off" and not has_builtin_display_hardware():
    return {"ok": False, "error": "no_builtin_display"}
  if os.environ.get("WEBUI_DEV_PC") == "1":
    try:
      from webui.dev.mock_runtime import SIM
      SIM["headless_mode"] = mode
      SIM["headless"] = mode == "on" or (mode == "auto" and not has_builtin_display_hardware())
    except Exception:
      pass
    return {"ok": True, "mode": mode}
  try:
    from openpilot.common.params import Params
    Params().put(HEADLESS_MODE_PARAM, mode, block=True)
    try:
      from openpilot.common.hardware.comma.hardware import invalidate_display_probe_cache
      invalidate_display_probe_cache()
    except Exception:
      pass
    return {"ok": True, "mode": mode}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def is_headless_mode() -> bool:
  if os.environ.get("WEBUI_DEV_PC") == "1":
    try:
      from webui.dev.mock_runtime import SIM
      pref = get_headless_mode_pref()
      if pref == "on":
        return True
      if pref == "off":
        return False
      return bool(SIM.get("headless"))
    except Exception:
      return False

  pref = get_headless_mode_pref()
  if pref == "on":
    return True
  if pref == "off":
    return not has_builtin_display_hardware()

  try:
    from openpilot.common.hardware import COMMA_HARDWARE, HARDWARE
    if not COMMA_HARDWARE:
      return False
    return not HARDWARE.has_builtin_display()
  except Exception:
    return False
