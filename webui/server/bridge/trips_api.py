"""Trips / drive stats."""

from __future__ import annotations

from typing import Any


def trips_stats(source: str | None = None) -> dict[str, Any]:
  import os
  from openpilot.common.params import Params

  p = Params()
  data_source = source or p.get("TripsDataSource") or "local"

  if os.environ.get("WEBUI_DEV_PC") == "1":
    try:
      import json
      raw = p.get("LocalDriveStats") or "{}"
      stats = json.loads(raw) if isinstance(raw, str) else raw
      return {"ok": True, "stats": stats, "source": data_source, "dev_pc": True}
    except Exception:
      return {
        "ok": True,
        "stats": {"all": {"distance": 1234.5, "routes": 42, "minutes": 890}, "week": {"distance": 120, "routes": 5, "minutes": 80}},
        "source": data_source,
        "dev_pc": True,
      }

  try:
    from openpilot.selfdrive.ui.sunnypilot.lib.drive_stats import (
      fetch_cloud_drive_stats,
      refresh_local_drive_stats,
    )

    # Always refresh local stats in the background
    local_stats = refresh_local_drive_stats(p, "LocalDriveStats")

    if data_source == "cloud":
      cloud_stats = fetch_cloud_drive_stats(p)
      if "error" not in cloud_stats:
        return {"ok": True, "stats": cloud_stats, "source": data_source}
      return {"ok": False, "error": cloud_stats.get("error"), "stats": local_stats, "source": data_source}

    return {"ok": True, "stats": local_stats, "source": data_source}
  except Exception as exc:
    return {"ok": False, "error": str(exc), "stats": {}}
