#!/usr/bin/env python3
"""Probe Cabana offline replay WebSocket (run on device)."""
import asyncio
import json
import sys
import time

import aiohttp


async def main() -> None:
  route = sys.argv[1] if len(sys.argv) > 1 else "00000009--668208f571--69"
  url = (
    f"ws://127.0.0.1:5090/api/cabana/offline/ws"
    f"?route={route}&speed=10&autoplay=1"
  )
  t0 = time.time()
  can_batches = 0
  frames = 0
  print("connect", url)
  async with aiohttp.ClientSession() as session:
    async with session.ws_connect(url, timeout=120) as ws:
      async for msg in ws:
        if msg.type != aiohttp.WSMsgType.TEXT:
          continue
        data = json.loads(msg.data)
        typ = data.get("type")
        elapsed = time.time() - t0
        if typ == "loading":
          phase = data.get("phase")
          cf = data.get("can_frames", "")
          print(f"[{elapsed:5.1f}s] loading phase={phase} can_frames={cf}")
        elif typ == "metadata":
          print(
            f"[{elapsed:5.1f}s] metadata dur={data.get('duration'):.2f} "
            f"streaming={data.get('streaming')} frames={data.get('frame_count')}"
          )
        elif typ == "can":
          can_batches += 1
          n = len(data.get("frames", []))
          frames += n
          if can_batches <= 5 or can_batches % 25 == 0:
            print(
              f"[{elapsed:5.1f}s] can #{can_batches} progress={data.get('progress', 0):.2f} n={n}"
            )
        elif typ == "done":
          print(f"[{elapsed:5.1f}s] DONE batches={can_batches} frames={frames}")
          break
        elif typ == "error":
          print("ERROR:", data.get("error"))
          break
        if elapsed > 90:
          print("TIMEOUT")
          break


if __name__ == "__main__":
  asyncio.run(main())
