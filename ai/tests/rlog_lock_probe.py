#!/usr/bin/env python3
import sys
import time
from pathlib import Path

from tools.lib.logreader import LogReader

route = Path("/data/media/0/realdata") / (sys.argv[1] if len(sys.argv) > 1 else "0000000a--ac94faebb9--0")
for name in ("rlog.lock", "rlog.zst", "qlog.zst"):
  p = route / name
  if not p.is_file():
    print(name, "missing")
    continue
  t0 = time.time()
  n = 0
  try:
    for msg in LogReader(str(p)):
      if msg.which() == "can":
        n += len(msg.can)
        if n >= 80:
          break
  except Exception as e:
    print(name, "error", e, "sec", round(time.time() - t0, 2))
    continue
  print(name, "frames", n, "sec", round(time.time() - t0, 2))
