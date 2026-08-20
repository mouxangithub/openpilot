#!/usr/bin/env python3
"""Smoke-test Cabana offline replay WebSocket (metadata + can rows, no hang)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

try:
  import aiohttp
except ImportError:
  print("aiohttp required", file=sys.stderr)
  sys.exit(2)


async def run(url: str, route: str, timeout: float) -> int:
  base = url.rstrip("/").replace("https://", "wss://").replace("http://", "ws://")
  qs = f"route={route}&speed=4&start_time=0&autoplay=0"
  ws_url = f"{base}/api/cabana/offline/ws?{qs}"
  t0 = time.monotonic()
  got_metadata = False
  got_ready = False
  can_rows = 0
  errors: list[str] = []

  async with aiohttp.ClientSession() as session:
    async with session.ws_connect(ws_url, heartbeat=30) as ws:
      while time.monotonic() - t0 < timeout:
        try:
          msg = await asyncio.wait_for(ws.receive(), timeout=min(45.0, timeout))
        except asyncio.TimeoutError:
          errors.append("ws receive timeout")
          break
        if msg.type == aiohttp.WSMsgType.ERROR:
          errors.append(f"ws error: {ws.exception()}")
          break
        if msg.type != aiohttp.WSMsgType.TEXT:
          continue
        data = json.loads(msg.data)
        typ = data.get("type")
        if typ == "error":
          errors.append(data.get("error") or "unknown error")
          break
        if typ == "loading":
          if data.get("phase") == "ready":
            got_ready = True
          continue
        if typ == "metadata":
          got_metadata = True
          continue
        if typ == "can":
          frames = data.get("frames") or []
          can_rows = max(can_rows, len(frames))
          if got_metadata and can_rows > 0:
            return 0
        if typ == "done":
          break

  if errors:
    print("FAIL:", "; ".join(errors), file=sys.stderr)
    return 1
  if not got_metadata:
    print("FAIL: no metadata within timeout", file=sys.stderr)
    return 1
  if can_rows <= 0:
    print("FAIL: no CAN preview rows", file=sys.stderr)
    return 1
  print(f"OK metadata={got_metadata} ready={got_ready} can_rows={can_rows}")
  return 0


def main() -> int:
  p = argparse.ArgumentParser()
  p.add_argument("--url", default="http://127.0.0.1:5090")
  p.add_argument("--route", required=True)
  p.add_argument("--timeout", type=float, default=90.0)
  args = p.parse_args()
  return asyncio.run(run(args.url, args.route, args.timeout))


if __name__ == "__main__":
  raise SystemExit(main())
