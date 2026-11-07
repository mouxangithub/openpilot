"""Cabana live module: live CAN broadcaster + StreamSource-compatible live stream."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from aiohttp import web

from ai.services.cabana.deps import cloudlog, messaging
from ai.services.cabana.frame import can_frame_to_dict as _can_frame_to_dict
from ai.services.cabana.stream_base import FrameCallback

_WSMsgType = web.WSMsgType


class LiveCanBroadcaster:
  """Broadcasts live CAN frames to WS clients (delta-based, per-client filters)."""

  mode = "live"

  def __init__(self):
    self._clients: set[web.WebSocketResponse] = set()
    self._task: asyncio.Task | None = None
    self._sm: Any = None
    self._latest: dict[tuple[int, int], dict[str, Any]] = {}
    self._last_send = 0.0
    self._send_interval = 0.05  # 20 Hz — enough for live view, avoids WS flood
    self._seq = 0
    self._last_sent: dict[tuple[int, int], tuple[float, str]] = {}
    self._callbacks: list[FrameCallback] = []
    self._filters: dict[web.WebSocketResponse, set[int] | None] = {}
    self._fresh_clients: set[web.WebSocketResponse] = set()

  # -- StreamSource protocol -------------------------------------------------

  def start(self):
    if self._task is not None:
      return
    try:
      self._sm = messaging.SubMaster(["can"])
    except Exception as e:
      cloudlog.error(f"cabana: failed to create SubMaster: {e}")
      return
    self._task = asyncio.create_task(self._loop())

  def stop(self):
    if self._task is not None:
      self._task.cancel()
      self._task = None

  def messages(self, address: int, t0: float, t1: float) -> list[dict[str, Any]]:
    """Frames matching address with t0 <= time <= t1, sorted by time."""
    frames = [
      f for f in self._latest.values()
      if int(f["address"]) == int(address) and t0 <= float(f["time"]) <= t1
    ]
    frames.sort(key=lambda f: float(f["time"]))
    return frames

  def last_msgs(self) -> dict[tuple[int, int], dict[str, Any]]:
    return dict(self._latest)

  def subscribe(self, cb: FrameCallback) -> None:
    if cb not in self._callbacks:
      self._callbacks.append(cb)

  def unsubscribe(self, cb: FrameCallback) -> None:
    if cb in self._callbacks:
      self._callbacks.remove(cb)

  def seek(self, t: float) -> None:  # no-op for live
    return

  def speed(self, v: float) -> None:  # no-op for live
    return

  # -- client / filter management --------------------------------------------

  def add(self, ws: web.WebSocketResponse):
    self._clients.add(ws)
    self._fresh_clients.add(ws)
    self.start()

  def remove(self, ws: web.WebSocketResponse):
    self._clients.discard(ws)
    self._filters.pop(ws, None)
    self._fresh_clients.discard(ws)

  def set_filter(self, ws: web.WebSocketResponse, addresses: set[int] | None) -> None:
    """Per-client address filter; None/empty means no filtering."""
    if not addresses:
      self._filters.pop(ws, None)
    else:
      self._filters[ws] = set(addresses)

  # -- internals ---------------------------------------------------------------

  async def _loop(self):
    while True:
      if self._sm is None or not self._clients:
        await asyncio.sleep(0.1)
        continue
      try:
        # Non-blocking update: SubMaster.update is a blocking C call.
        await asyncio.to_thread(self._sm.update, 100)
        if self._sm.updated["can"]:
          try:
            base_mono = float(self._sm.logMonoTime["can"]) / 1e9
          except (KeyError, TypeError, AttributeError):
            base_mono = 0.0
          if base_mono <= 0:
            base_mono = time.monotonic()
          for idx, cf in enumerate(self._sm["can"]):
            key = (int(cf.src), int(cf.address))
            frame_mono = base_mono + idx * 1e-6
            self._latest[key] = _can_frame_to_dict(cf, frame_mono)
          if len(self._latest) > 400:
            for k in list(self._latest.keys())[: len(self._latest) - 400]:
              del self._latest[k]

        now = time.monotonic()
        if self._latest and now - self._last_send >= self._send_interval:
          await self._broadcast()
          self._last_send = now
        else:
          await asyncio.sleep(0.01)
      except Exception as e:
        cloudlog.error(f"cabana: broadcaster error: {e}")
        await asyncio.sleep(0.5)

  async def _broadcast(self) -> None:
    # Incremental payload: only frames whose (time, data) changed since last send.
    # NOTE: _last_sent is only marked for frames actually delivered to at least
    # one client — a change suppressed by a client's filter stays pending and is
    # delivered once the filter is cleared.
    sig_of: dict[tuple[int, int], tuple[float, str]] = {}
    changed_pairs: list[tuple[tuple[int, int], dict[str, Any]]] = []
    for key, f in self._latest.items():
      sig = (float(f["time"]), str(f.get("data", "")))
      sig_of[key] = sig
      if self._last_sent.get(key) != sig:
        changed_pairs.append((key, f))
    changed = [f for _key, f in changed_pairs]
    has_fresh = bool(self._fresh_clients)
    if not changed and not has_fresh:
      return
    if changed:
      for cb in list(self._callbacks):
        try:
          cb(changed)
        except Exception:
          pass
    self._seq += 1
    dead: set[web.WebSocketResponse] = set()
    delivered: set[tuple[int, int]] = set()
    for ws in list(self._clients):
      fresh = ws in self._fresh_clients
      if fresh:
        self._fresh_clients.discard(ws)
      # First packet for a client is always the full snapshot.
      keys = list(sig_of.keys()) if fresh else [k for k, _f in changed_pairs]
      filt = self._filters.get(ws)
      if filt is not None:
        keys = [k for k in keys if int(self._latest[k]["address"]) in filt]
      if not keys:
        continue
      frames = [self._latest[k] for k in keys]
      payload = json.dumps({"type": "can", "seq": self._seq, "source": "live", "frames": frames})
      try:
        await ws.send_str(payload)
      except Exception:
        dead.add(ws)
        continue
      delivered.update(keys)
    self._clients -= dead
    for key in delivered:
      self._last_sent[key] = sig_of[key]


LIVE_CAN = LiveCanBroadcaster()


async def run_live_ws(ws: web.WebSocketResponse) -> None:
  """Shared live-session body for /api/cabana/ws and /api/cabana/stream/ws."""
  LIVE_CAN.add(ws)
  if LIVE_CAN._sm is None:
    await ws.send_str(json.dumps({
      "type": "error",
      "code": "live_can_unavailable",
      "error": "Live CAN requires comma device and cereal messaging (use replay mode on PC).",
    }, ensure_ascii=False))
  try:
    async for msg in ws:
      if msg.type != _WSMsgType.TEXT:
        continue
      try:
        data = json.loads(msg.data)
        if data.get("type") == "filter":
          if data.get("clear"):
            LIVE_CAN.set_filter(ws, None)
          else:
            addrs = data.get("addresses")
            filt = None
            if isinstance(addrs, (list, tuple)) and addrs:
              try:
                filt = {int(a) for a in addrs}
              except (TypeError, ValueError):
                filt = None
            LIVE_CAN.set_filter(ws, filt)
      except Exception:
        continue
  finally:
    LIVE_CAN.remove(ws)


async def ws_live(request: web.Request) -> web.WebSocketResponse:
  ws = web.WebSocketResponse()
  await ws.prepare(request)
  await run_live_ws(ws)
  return ws
