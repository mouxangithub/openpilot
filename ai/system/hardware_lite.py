"""Comma device Lite hardware variant — detection and AI param policy.

Lite = comma three (``tici`` / C3) without I2C audio amp @ bus 0 / 0x10.
Matches ``set_lite_hw()`` in ``launch_chffrplus.sh`` (``tici`` / C3 only, not ``tizi`` C3X).
When ``LITE=1``: no micd/soundd/dmonitoring*; use ``beepd`` + ``SpDevBeep`` for feedback.
C4 (``mici``) has no amp chip but is **not** the Lite variant (different product line).
Not the same as PrimeType.LITE (subscription tier).
"""

from __future__ import annotations

import os
import subprocess
from typing import Any

from openpilot.common.params import Params

from ai.system.paths import is_comma_device

# Only comma three (C3 / tici) — same gate as launch_chffrplus.sh set_lite_hw().
LITE_CAPABLE_DEVICE_TYPES = frozenset({"tici"})

LITE_DEVICE_LABELS = {
  "tici": "C3",
}

# Writes blocked on Lite (hardware cannot honor these).
LITE_BLOCKED_WRITE_PARAMS = frozenset({
  "RecordAudio",
  "AlwaysOnDM",
  "DistractionDetectionLevel",
})

LITE_UNAVAILABLE_PARAMS = frozenset({
  "RecordAudio",
  "AlwaysOnDM",
  "DistractionDetectionLevel",
})

LITE_UNAVAILABLE_NOTE = (
  "Lite 硬件无麦克风与驾驶员监控进程；声音反馈请用 SpDevBeep + beepd，勿启用本项。"
)

_I2C_AMP_PROBE = ("i2cget", "-y", "0", "0x10", "0x00")


def _comma_device_slug() -> str | None:
  try:
    from ai.tsk.lib.panda_connect import get_device_type

    return get_device_type()
  except Exception:
    return None


def _probe_amp_missing() -> bool | None:
  """True if amp read failed (Lite), False if present, None if probe failed."""
  try:
    proc = subprocess.run(
      list(_I2C_AMP_PROBE),
      capture_output=True,
      text=True,
      timeout=3,
    )
    if proc.returncode != 0:
      return True
    return not (proc.stdout or "").strip()
  except Exception:
    return None


def _devicetree_has_tici() -> bool:
  return _comma_device_slug() == "tici"


def detect_lite_hw() -> bool | None:
  """True=Lite, False=full audio stack, None=unknown (PC or probe failed)."""
  if os.getenv("LITE"):
    return True
  if not is_comma_device():
    return None

  slug = _comma_device_slug()
  if slug in ("mici", "tizi"):
    return False
  if slug is not None and slug != "tici":
    return False
  if slug != "tici" and not _devicetree_has_tici():
    return False

  probed = _probe_amp_missing()
  if probed is not None:
    return probed

  return None


def is_lite_hw() -> bool:
  return detect_lite_hw() is True


def lite_device_label(device_type: str | None = None) -> str | None:
  slug = device_type or _comma_device_slug()
  if slug in LITE_DEVICE_LABELS:
    return LITE_DEVICE_LABELS[slug]
  return None


def lite_write_block_reason(key: str) -> str | None:
  if is_lite_hw() and key in LITE_BLOCKED_WRITE_PARAMS:
    label = lite_device_label() or "C3"
    return (
      f"Param '{key}' is unavailable on Lite {label} (no microphone / no dmonitoring). "
      f"Use set_sp_dev_beep for GPIO beep feedback instead."
    )
  return None


def lite_profile(params: Params | None = None) -> dict[str, Any]:
  params = params or Params()
  lite = detect_lite_hw()
  slug = _comma_device_slug()
  label = lite_device_label(slug)

  beep = None
  try:
    if params.get("SpDevBeep") is not None:
      beep = params.get_bool("SpDevBeep")
  except Exception:
    pass

  if lite:
    lite_note = (
      f"LITE=1: micd/soundd/dmonitoringd off; beepd when SpDevBeep=1. "
      f"Lite {label or 'C3'} (tici, no amp @ I2C 0x10)."
    )
  elif lite is False:
    lite_note = f"Full audio stack ({label or slug or 'comma device'})."
  else:
    lite_note = "Lite status unknown off-device."

  return {
    "lite": lite,
    "lite_env": bool(os.getenv("LITE")),
    "device_type": slug,
    "product_label": label,
    "lite_capable": slug in LITE_CAPABLE_DEVICE_TYPES if slug else None,
    "lite_note": lite_note,
    "SpDevBeep": beep,
    "beepd_eligible": lite is True and beep is True,
    "audio_feedback": "beepd" if lite else "soundd",
    "unavailable_params": sorted(LITE_UNAVAILABLE_PARAMS) if lite else [],
  }
