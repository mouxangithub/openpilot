#!/usr/bin/env python3
"""List Cabana drive routes (same data as GET /api/cabana/routes and AI list_drive_routes).

Usage (on comma device or PC with openpilot env):
  cd /data/openpilot && python3 ai/scripts/list_cabana_routes.py
  python3 ai/scripts/list_cabana_routes.py --limit 5 --json
  python3 ai/scripts/list_cabana_routes.py --via-api
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def _repo_root() -> Path:
  return Path(__file__).resolve().parents[2]


def _ensure_path() -> None:
  root = str(_repo_root())
  if root not in sys.path:
    sys.path.insert(0, root)


def _list_via_tool(limit: int) -> dict:
  _ensure_path()
  from ai.tools.cabana_route_tools import list_cabana_routes

  return list_cabana_routes(limit=limit)


def _list_via_api(base_url: str, limit: int) -> dict:
  url = f"{base_url.rstrip('/')}/api/cabana/routes"
  req = urllib.request.Request(url, headers={"Accept": "application/json"})
  try:
    with urllib.request.urlopen(req, timeout=20) as resp:
      body = resp.read().decode("utf-8", errors="replace")
  except urllib.error.HTTPError as e:
    return {"ok": False, "error": f"HTTP {e.code}", "url": url}
  except Exception as e:
    return {"ok": False, "error": str(e), "url": url}

  try:
    data = json.loads(body)
  except json.JSONDecodeError as e:
    return {"ok": False, "error": f"Invalid JSON: {e}", "url": url}

  if not isinstance(data, dict):
    return {"ok": False, "error": "Unexpected API response", "url": url}

  routes = data.get("routes")
  if isinstance(routes, list) and limit > 0:
    data = {**data, "routes": routes[:limit]}
  return data


def _print_human(data: dict) -> int:
  if not data.get("ok"):
    print(f"ERROR: {data.get('error', 'unknown')}", file=sys.stderr)
    if hint := data.get("hint"):
      print(f"Hint: {hint}", file=sys.stderr)
    if url := data.get("url"):
      print(f"URL: {url}", file=sys.stderr)
  print(f"routes_dir: {data.get('routes_dir', '?')}")
  print(f"count: {data.get('count', 0)}")
  routes = data.get("routes") or []
  if not routes:
    print("(no routes with qlog/rlog)")
    return 1 if not data.get("ok") else 0
  for r in routes:
    flags = []
    if r.get("has_qlog"):
      flags.append("qlog")
    if r.get("has_rlog"):
      flags.append("rlog")
    print(f"  {r.get('date', '?'):16}  [{','.join(flags) or '-'}]  {r.get('name', '')}")
  return 0 if data.get("ok") else 1


def main() -> int:
  p = argparse.ArgumentParser(description="List Cabana routes (qlog/rlog drives)")
  p.add_argument("--limit", type=int, default=15, help="Max routes to show (default 15)")
  p.add_argument("--json", action="store_true", help="Print raw JSON")
  p.add_argument("--via-api", action="store_true", help="Use HTTP GET /api/cabana/routes (aid must be running)")
  p.add_argument("--base-url", default="http://127.0.0.1:5090", help="Aid base URL for --via-api")
  args = p.parse_args()

  limit = max(1, min(int(args.limit or 15), 100))
  if args.via_api:
    data = _list_via_api(args.base_url, limit)
  else:
    try:
      data = _list_via_tool(limit)
    except Exception as e:
      data = {"ok": False, "error": str(e), "hint": "Try --via-api if aid is running, or run on device with openpilot env."}

  if args.json:
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0 if data.get("ok") else 1
  return _print_human(data)


if __name__ == "__main__":
  raise SystemExit(main())
