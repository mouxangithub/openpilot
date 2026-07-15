#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, "/data/openpilot")
from ai.cabana import _find_qlogs, _find_rlogs

route = Path("/data/media/0/realdata") / (sys.argv[1] if len(sys.argv) > 1 else "0000000a--ac94faebb9--0")
print("rlogs", [p.name for p in _find_rlogs(route)])
print("qlogs", [p.name for p in _find_qlogs(route)])
