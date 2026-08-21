"""Quick smoke test for webui APIs (run while run_pc.py is up)."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:5080"

ENDPOINTS = [
  "/api/opui/bootstrap",
  "/api/opui/state",
  "/api/opui/home",
  "/api/opui/panels",
  "/api/opui/panels/device",
  "/api/opui/panels/toggles",
  "/api/opui/panels/models",
  "/api/opui/panels/steering__mads",
  "/api/opui/models",
  "/api/opui/sunnylink/status",
  "/api/opui/firehose",
  "/api/opui/device/extras",
  "/api/opui/osm/regions",
  "/api/opui/osm/progress",
  "/api/opui/vehicle/platforms",
  "/api/opui/ssh/status",
  "/api/opui/trips",
  "/api/opui/software",
  "/api/opui/wifi/scan",
  "/api/opui/model/overlay?w=800&h=600",
]


def main() -> int:
  fails = 0
  for path in ENDPOINTS:
    url = BASE + path
    try:
      with urllib.request.urlopen(url, timeout=8) as resp:
        raw = resp.read()
      data = json.loads(raw)
      ok = data.get("ok", True)
      if not ok:
        print(f"FAIL {path}: {data.get('error', data)}")
        fails += 1
      else:
        print(f"OK   {path}")
    except Exception as exc:
      print(f"ERR  {path}: {exc}")
      fails += 1

  css = urllib.request.urlopen(BASE + "/static/css/opui.css", timeout=8).read().decode()
  if "opui-modal[hidden]" not in css:
    print("FAIL /static/css/opui.css: missing opui-modal[hidden] rule")
    fails += 1
  else:
    print("OK   CSS modal hidden fix present")

  html = urllib.request.urlopen(BASE + "/", timeout=8).read().decode()
  for mid in ("modal-confirm", "modal-keyboard", "modal-tree", "modal-multi", "modal-html"):
    if f'id="{mid}"' not in html:
      print(f"FAIL HTML missing {mid}")
      fails += 1
  print(f"\n{len(ENDPOINTS)} endpoints, {fails} failures")
  return 1 if fails else 0


if __name__ == "__main__":
  sys.exit(main())
