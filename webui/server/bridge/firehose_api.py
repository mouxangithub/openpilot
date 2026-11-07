"""Firehose mode status page."""

from __future__ import annotations

import json
import os
from typing import Any


def firehose_status() -> dict[str, Any]:
  if os.environ.get("WEBUI_DEV_PC") == "1":
    return {
      "ok": True,
      "active": True,
      "segments": 3,
      "network_type": "Wi-Fi",
      "metered": False,
      "stats_raw": '{"firehose":3}',
      "dev_pc": True,
    }
  try:
    import openpilot.cereal.messaging as messaging
    from openpilot.common.params import Params

    p = Params()
    sm = messaging.SubMaster(["deviceState"], poll="deviceState")
    sm.update(200)
    ds = sm["deviceState"]
    net = ds.networkType.raw if hasattr(ds, "networkType") else 0
    net_names = {0: "--", 1: "Wi-Fi", 2: "ETH", 3: "2G", 4: "3G", 5: "LTE", 6: "5G"}
    raw = p.get("ApiCache_FirehoseStats") or "{}"
    try:
      stats = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
      stats = {}
    net_connected = net != 0
    metered = bool(getattr(ds, "networkMetered", False))
    active = net_connected and not metered
    return {
      "ok": True,
      "active": active,
      "segments": int(stats.get("firehose", 0) or 0),
      "network_type": net_names.get(net, "--"),
      "metered": bool(getattr(ds, "networkMetered", False)),
      "stats_raw": raw if isinstance(raw, str) else json.dumps(stats),
    }
  except Exception as exc:
    return {"ok": False, "error": str(exc)}
