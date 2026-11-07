#!/usr/bin/env python3
"""Time how long until first N CAN frames from a route."""
import sys
import time
from pathlib import Path

from tools.lib.logreader import LogReader


def first_can_frames(route_name: str, need: int = 80) -> None:
  route = Path("/data/media/0/realdata") / route_name
  rlogs = sorted(route.rglob("rlog"))
  qlogs = sorted(route.rglob("qlog"))
  print("route", route_name, "rlogs", len(rlogs), "qlogs", len(qlogs))
  for label, paths in [("qlog", qlogs[:1]), ("rlog", rlogs[:1])]:
    if not paths:
      continue
    t0 = time.time()
    n = 0
    for msg in LogReader(str(paths[0])):
      if msg.which() != "can":
        continue
      n += len(msg.can)
      if n >= need:
        break
    print(f"  {label} first {need} frames: {time.time() - t0:.2f}s (count={n})")


if __name__ == "__main__":
  route = sys.argv[1] if len(sys.argv) > 1 else "0000000a--ac94faebb9--0"
  first_can_frames(route)
