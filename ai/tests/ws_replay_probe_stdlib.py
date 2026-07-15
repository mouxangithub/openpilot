#!/usr/bin/env python3
"""Probe Cabana offline replay WebSocket (stdlib only, run on device)."""
from __future__ import annotations

import json
import os
import socket
import struct
import sys
import time
import urllib.parse


def _ws_handshake(host: str, port: int, path: str) -> socket.socket:
  key = "dGhlIHNhbXBsZSBub25jZQ=="
  req = (
    f"GET {path} HTTP/1.1\r\n"
    f"Host: {host}:{port}\r\n"
    "Upgrade: websocket\r\n"
    "Connection: Upgrade\r\n"
    f"Sec-WebSocket-Key: {key}\r\n"
    "Sec-WebSocket-Version: 13\r\n"
    "\r\n"
  )
  sock = socket.create_connection((host, port), timeout=120)
  sock.sendall(req.encode())
  resp = b""
  while b"\r\n\r\n" not in resp:
    chunk = sock.recv(4096)
    if not chunk:
      raise RuntimeError("handshake closed")
    resp += chunk
  if b"101" not in resp.split(b"\r\n", 1)[0]:
    raise RuntimeError(resp[:200].decode("utf-8", "replace"))
  return sock


def _recv_frame(sock: socket.socket) -> str:
  hdr = sock.recv(2)
  if len(hdr) < 2:
    raise RuntimeError("connection closed")
  b1, b2 = hdr
  masked = (b2 & 0x80) != 0
  length = b2 & 0x7F
  if length == 126:
    length = struct.unpack("!H", sock.recv(2))[0]
  elif length == 127:
    length = struct.unpack("!Q", sock.recv(8))[0]
  if masked:
  # server frames are unmasked
    _ = sock.recv(4)
  payload = b""
  while len(payload) < length:
    chunk = sock.recv(length - len(payload))
    if not chunk:
      raise RuntimeError("truncated frame")
    payload += chunk
  opcode = b1 & 0x0F
  if opcode == 8:
    raise RuntimeError("ws close")
  if opcode != 1:
    return ""
  return payload.decode("utf-8", "replace")


def main() -> None:
  route = sys.argv[1] if len(sys.argv) > 1 else "00000009--668208f571--69"
  host = os.environ.get("CABANA_HOST", "127.0.0.1")
  port = int(os.environ.get("CABANA_PORT", "5090"))
  qs = urllib.parse.urlencode({"route": route, "speed": "10", "autoplay": "1"})
  path = f"/api/cabana/offline/ws?{qs}"
  print("connect", f"ws://{host}:{port}{path}")
  sock = _ws_handshake(host, port, path)
  sock.settimeout(120)
  t0 = time.time()
  can_batches = frames = 0
  try:
    while True:
      raw = _recv_frame(sock)
      if not raw:
        continue
      data = json.loads(raw)
      typ = data.get("type")
      elapsed = time.time() - t0
      if typ == "loading":
        print(f"[{elapsed:5.1f}s] loading phase={data.get('phase')} can={data.get('can_frames', '')}")
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
          print(f"[{elapsed:5.1f}s] can #{can_batches} progress={data.get('progress', 0):.2f} n={n}")
      elif typ == "done":
        print(f"[{elapsed:5.1f}s] DONE batches={can_batches} frames={frames}")
        break
      elif typ == "error":
        print("ERROR:", data.get("error"))
        break
      if elapsed > 120:
        print("TIMEOUT")
        break
  finally:
    sock.close()


if __name__ == "__main__":
  main()
