#!/usr/bin/env python3
import asyncio
import json
import sys

import aiohttp


async def main() -> int:
  route = sys.argv[1] if len(sys.argv) > 1 else "00000003--f7252f725d--70"
  url = (
    "ws://127.0.0.1:5090/api/cabana/offline/ws"
    f"?route={route}&speed=4&start_time=0&autoplay=0"
  )
  async with aiohttp.ClientSession() as session:
    async with session.ws_connect(url, heartbeat=30) as ws:
      for i in range(30):
        msg = await asyncio.wait_for(ws.receive(), timeout=45)
        if msg.type != aiohttp.WSMsgType.TEXT:
          print(i, "non-text", msg.type)
          continue
        data = json.loads(msg.data)
        typ = data.get("type")
        phase = data.get("phase")
        n = len(data.get("frames") or [])
        print(i, typ, phase, n, flush=True)
        if typ == "can" and n:
          return 0
        if typ == "error":
          print("error:", data.get("error"))
          return 1
  return 1


if __name__ == "__main__":
  raise SystemExit(asyncio.run(main()))
