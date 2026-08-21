"""Detect comma hardware class: C2 (comma two / EON-class) vs C3/C3X/C4 (AGNOS/TICI)."""

from __future__ import annotations

import os
import subprocess
from typing import Any

from ai.system.paths import is_comma_device, openpilot_root


def _getprop(name: str) -> str | None:
  try:
    proc = subprocess.run(
      ["getprop", name],
      capture_output=True,
      text=True,
      timeout=3,
    )
  except (OSError, subprocess.TimeoutExpired):
    return None
  if proc.returncode != 0:
    return None
  value = (proc.stdout or "").strip()
  return value or None


def _android_openpilot_host() -> bool:
  if is_comma_device():
    return False
  if os.path.isfile("/system/build.prop") or os.path.isdir("/system"):
    return True
  if os.path.isdir("/data/openpilot") and os.path.isfile("/data/data/com.android.shell"):
    return True
  return False


def detect_comma_product() -> dict[str, Any]:
  """
  Return host product metadata.

  device_class: c2 | c3 | c3x | c4 | pc | unknown
  """
  try:
    from ai.tsk.lib.panda_connect import comma_product_meta, get_device_type

    dt = get_device_type()
    if dt in ("tici", "tizi", "mici"):
      meta = comma_product_meta(dt)
      mapping = {"tici": "c3", "tizi": "c3x", "mici": "c4"}
      return {
        "device_class": mapping[dt],
        "device_type": dt,
        "device_label": meta.get("label"),
        "product_name": meta.get("name"),
        "platform": "agnos",
        "openpilot_root": str(openpilot_root()),
      }
  except Exception:
    pass

  if _android_openpilot_host():
    model = (_getprop("ro.product.model") or "").lower()
    device = (_getprop("ro.product.device") or "").lower()
    brand = (_getprop("ro.product.brand") or "").lower()
    hints = " ".join([model, device, brand])
    root = openpilot_root()
    android_op = any(
      token in hints
      for token in ("le pro", "lepro", "comma", "commatwo", "eon", "le x527")
    ) or (root / "d2").is_file()
    return {
      "device_class": "c2",
      "device_type": "commatwo",
      "device_label": "C2",
      "product_name": "comma two / EON-class Android",
      "platform": "android",
      "android_model": model or None,
      "openpilot_root": str(root),
      "detected_android_openpilot": android_op,
      "note": "C2 为 Android 宿主；TSK/pandad_tici 等与 C3+ AGNOS 不同。",
    }

  return {
    "device_class": "pc",
    "device_type": None,
    "device_label": "PC",
    "product_name": "development host",
    "platform": "pc",
    "openpilot_root": str(openpilot_root()),
  }


def comma_host_summary() -> str:
  info = detect_comma_product()
  parts = [
    f"设备: {info.get('device_label') or info.get('device_class')}",
    f"平台: {info.get('platform')}",
  ]
  if info.get("product_name"):
    parts.append(str(info["product_name"]))
  branch_hint = ""
  try:
    from ai.fork.repo_scan import scan_openpilot_repo

    scan = scan_openpilot_repo(openpilot_root())
    if scan.get("git_branch"):
      parts.append(f"分支: {scan['git_branch']}")
    remote = (scan.get("remote_identity") or {}).get("slug")
    if remote:
      parts.append(f"remote: {remote}")
  except Exception:
    pass
  return "；".join(parts) + branch_hint
