"""Trips / drive stats."""

from __future__ import annotations

from typing import Any


def trips_stats() -> dict[str, Any]:
  import os
  if os.environ.get("WEBUI_DEV_PC") == "1":
    try:
      from openpilot.common.params import Params
      import json
      raw = Params().get("LocalDriveStats") or "{}"
      stats = json.loads(raw) if isinstance(raw, str) else raw
      return {"ok": True, "stats": stats, "dev_pc": True}
    except Exception:
      return {
        "ok": True,
        "stats": {"all": {"distance": 1234.5, "routes": 42, "minutes": 890}, "week": {"distance": 120, "routes": 5, "minutes": 80}},
        "dev_pc": True,
      }
  try:
    from openpilot.common.params import Params
    from openpilot.selfdrive.ui.sunnypilot.lib.drive_stats import refresh_local_drive_stats

    p = Params()
    key = "LocalDriveStats"
    stats = p.get(key) or {}
    if not stats:
      stats = refresh_local_drive_stats(p, key)
    return {"ok": True, "stats": stats}
  except Exception as exc:
    return {"ok": False, "error": str(exc), "stats": {}}
