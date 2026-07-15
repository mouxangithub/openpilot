"""Live cereal subscription (read-only snapshot)."""

from __future__ import annotations

import os
import time
from collections import Counter
from typing import Any


def live_cereal_summary(
  *,
  services: list[str] | None = None,
  addr: str = "127.0.0.1",
  duration_sec: float = 3.0,
  max_messages: int = 500,
) -> dict[str, Any]:
  duration_sec = max(0.5, min(float(duration_sec), 30.0))
  max_messages = max(10, min(int(max_messages), 5000))

  try:
    from openpilot.tools.lib.live_logreader import live_logreader
    from cereal.services import SERVICE_LIST
  except Exception as e:
    return {"ok": False, "error": str(e)}

  svc = services or ["carState", "controlsState", "deviceState", "managerState"]
  invalid = [s for s in svc if s not in SERVICE_LIST]
  if invalid:
    return {"ok": False, "error": f"Unknown services: {invalid}"}

  if addr != "127.0.0.1":
    os.environ["ZMQ"] = "1"

  counts: Counter[str] = Counter()
  start = time.monotonic()
  last_car = None
  try:
    for msg in live_logreader(svc, addr=addr):
      counts[msg.which()] += 1
      if msg.which() == "carState" and counts["carState"] <= 3:
        last_car = {
          "vEgo": round(float(msg.carState.vEgo), 3),
          "standstill": bool(msg.carState.standstill),
        }
      if sum(counts.values()) >= max_messages:
        break
      if time.monotonic() - start >= duration_sec:
        break
  except Exception as e:
    return {"ok": False, "error": str(e), "addr": addr, "zmq": os.environ.get("ZMQ") == "1"}

  return {
    "ok": True,
    "addr": addr,
    "zmq": os.environ.get("ZMQ") == "1",
    "duration_sec": round(time.monotonic() - start, 2),
    "message_counts": dict(counts),
    "last_carState": last_car,
    "script": "tools/lib/live_logreader.py",
    "hint": "Use after pc_launch_replay_stream or device messaging bridge.",
  }


def live_can_capture(
  *,
  duration_sec: float = 2.0,
  max_frames: int = 300,
  max_unique_ids: int = 80,
) -> dict[str, Any]:
  """Sample live CAN from cereal SubMaster (read-only, for AI analysis)."""
  duration_sec = max(0.5, min(float(duration_sec), 15.0))
  max_frames = max(20, min(int(max_frames), 2000))
  max_unique_ids = max(10, min(int(max_unique_ids), 500))

  try:
    from cereal import messaging
  except Exception as e:
    return {"ok": False, "error": f"cereal messaging unavailable: {e}"}

  frames: list[dict[str, Any]] = []
  seen: set[tuple[int, int]] = set()
  id_counts: dict[str, int] = {}
  start = time.monotonic()

  try:
    sm = messaging.SubMaster(["can"])
    while time.monotonic() - start < duration_sec and len(frames) < max_frames:
      sm.update(100)
      if not sm.updated["can"]:
        time.sleep(0.01)
        continue
      mono = time.monotonic()
      for cf in sm["can"]:
        key = (int(cf.src), int(cf.address))
        hex_id = f"0x{int(cf.address):X}"
        id_counts[hex_id] = id_counts.get(hex_id, 0) + 1
        if key in seen and len(seen) >= max_unique_ids:
          continue
        seen.add(key)
        frames.append({
          "address": int(cf.address),
          "bus": int(cf.src),
          "data": cf.dat.hex(),
          "time": mono,
        })
        if len(frames) >= max_frames:
          break
  except Exception as e:
    return {"ok": False, "error": str(e)}

  top_ids = sorted(id_counts.items(), key=lambda x: x[1], reverse=True)[:20]
  return {
    "ok": True,
    "duration_sec": round(time.monotonic() - start, 2),
    "frame_count": len(frames),
    "unique_ids": len(seen),
    "top_ids": [{"id": k, "count": v} for k, v in top_ids],
    "frames": frames[:max_frames],
    "hint": "Pair with cabana_analyze or compare_fingerprint for interpretation.",
  }
