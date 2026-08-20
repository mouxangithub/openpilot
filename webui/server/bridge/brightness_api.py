"""Direct screen brightness control for Web UI.

Mirrors the hardware path used by openpilot's native UI so that the display
panel brightness slider takes effect immediately, even when the native UI is
not running or has not yet polled the updated param.
"""

from __future__ import annotations

from typing import Any


def _hardware() -> Any | None:
  try:
    from openpilot.common.hardware import HARDWARE
    return HARDWARE
  except Exception:
    return None


def _clamp_brightness(value: int | str | None) -> int:
  try:
    pct = int(value or 0)
  except (TypeError, ValueError):
    pct = 0
  return max(0, min(100, pct))


def snapshot_brightness() -> dict[str, Any]:
  """Return current hardware brightness (0-100) with param fallback."""
  hw = _hardware()
  try:
    current = int(hw.get_screen_brightness()) if hw is not None else 0
  except Exception:
    current = 0

  try:
    from webui.server.bridge.params_api import get_param
    param_value = int(get_param("Brightness").get("value", 0))
  except Exception:
    param_value = 0

  return {
    "ok": True,
    "brightness": current if current is not None else param_value,
    "param": param_value,
  }


def apply_brightness(value: int | str) -> dict[str, Any]:
  """Set hardware brightness immediately and persist to the Brightness param."""
  pct = _clamp_brightness(value)
  hw = _hardware()
  applied = False
  if hw is not None:
    try:
      hw.set_screen_brightness(pct)
      applied = True
    except Exception as exc:
      return {"ok": False, "error": f"hardware refused brightness {pct}: {exc}"}

  try:
    from webui.server.bridge.params_api import put_param
    res = put_param("Brightness", str(pct))
    if not res.get("ok"):
      return {"ok": False, "brightness": pct, "applied": applied,
              "error": f"saved to hardware but param write failed: {res.get('error')}"}
  except Exception as exc:
    return {"ok": False, "brightness": pct, "applied": applied, "error": f"saved to hardware but param write failed: {exc}"}

  return {"ok": True, "brightness": pct, "applied": applied}