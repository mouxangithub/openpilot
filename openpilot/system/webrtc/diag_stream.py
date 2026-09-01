#!/usr/bin/env python3
"""Diagnostic: check if livestream narrow/wide road encode data streams are alive and distinct."""
import time

from openpilot.cereal import messaging

V4L2_BUF_FLAG_KEYFRAME = 0x8

streams = {
  "road": "livestreamNarrowRoadEncodeData",
  "wideRoad": "livestreamWideRoadEncodeData",
}

socks = {name: messaging.sub_sock(topic, conflate=False) for name, topic in streams.items()}
print("Subscribed to", list(streams.values()))

deadline = time.monotonic() + 10.0
seen = {name: 0 for name in streams}
last = {name: None for name in streams}

while time.monotonic() < deadline:
  for name, sock in socks.items():
    msg = messaging.recv_one_or_none(sock)
    if msg is None:
      continue
    seen[name] += 1
    ed = getattr(msg, msg.which())
    is_key = bool(ed.idx.flags & V4L2_BUF_FLAG_KEYFRAME)
    info = {
      "topic": streams[name],
      "frame_id": ed.idx.frameId,
      "encode_id": ed.idx.encodeId,
      "key": is_key,
      "width": ed.width,
      "height": ed.height,
      "data_len": len(ed.data),
      "header_len": len(ed.header),
    }
    last[name] = info
    print(f"[{name}] {info}")
  time.sleep(0.01)

print("\n--- summary ---")
for name in streams:
  print(f"{name}: received {seen[name]} frames, last={last[name]}")