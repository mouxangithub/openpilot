#!/usr/bin/env python3
"""Smoke-test HTTP API and static assets (run while aid is up on :5090)."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:5090"

ENDPOINTS = [
  ("GET", "/"),
  ("GET", "/api/ai/status"),
  ("GET", "/api/ai/bootstrap?lite=1"),
  ("GET", "/api/ai/config"),
  ("GET", "/api/ai/sessions"),
  ("GET", "/api/ai/feedback"),
  ("GET", "/api/ai/files/search"),
  ("GET", "/api/ai/context/branch"),
  ("GET", "/api/ai/tools"),
  ("GET", "/api/ai/rag"),
  ("GET", "/api/ai/agents"),
  ("GET", "/api/ai/sync/schema"),
  ("GET", "/api/ai/workspace"),
  ("GET", "/api/ai/consumer/wizards"),
  ("GET", "/api/panda/status"),
  ("GET", "/api/cabana/car"),
  ("GET", "/api/cabana/routes"),
  ("GET", "/static/js/app/dom.js"),
  ("GET", "/static/js/ai.js"),
]

# Expected non-200 on PC without optional deps
ALLOW_FAIL = {
  "/api/cabana/dbcs": {503},  # opendbc
}


def fetch(method: str, path: str) -> tuple[int, str]:
  req = urllib.request.Request(f"{BASE}{path}", method=method)
  try:
    with urllib.request.urlopen(req, timeout=20) as resp:
      body = resp.read(512).decode("utf-8", errors="replace")
      return resp.status, body
  except urllib.error.HTTPError as e:
    body = e.read(256).decode("utf-8", errors="replace") if e.fp else ""
    return e.code, body


def main() -> int:
  failed: list[str] = []
  for method, path in ENDPOINTS:
    code, body = fetch(method, path)
    allowed = ALLOW_FAIL.get(path, set())
    if code == 200 or code in allowed:
      print(f"ok  {code} {path}")
      if path.startswith("/api/ai/") and code == 200:
        try:
          data = json.loads(body) if body.strip().startswith("{") else {}
          if isinstance(data, dict) and data.get("ok") is False and "error" in data:
            failed.append(f"{path}: ok=false {data.get('error')}")
            print(f"    WARN json ok=false: {data.get('error')}")
        except json.JSONDecodeError:
          pass
    else:
      print(f"FAIL {code} {path} {body[:120]}")
      failed.append(f"{path} -> {code}")

  if failed:
    print(f"\n{len(failed)} issue(s)")
    return 1
  print("\nall smoke checks passed")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
