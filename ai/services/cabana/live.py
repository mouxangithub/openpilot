"""Cabana live module."""
from ai.services.cabana.deps import *
from ai.services.cabana.frame import can_frame_to_dict as _can_frame_to_dict

class LiveCanBroadcaster:
  def __init__(self):
    self._clients: set[web.WebSocketResponse] = set()
    self._task: asyncio.Task | None = None
    self._sm: Any = None
    self._latest: dict[tuple[int, int], dict[str, Any]] = {}
    self._last_send = 0.0
    self._send_interval = 0.05  # 20 Hz — enough for live view, avoids WS flood

  def start(self):
    if self._task is not None:
      return
    try:
      self._sm = messaging.SubMaster(["can"])
    except Exception as e:
      cloudlog.error(f"cabana: failed to create SubMaster: {e}")
      return
    self._task = asyncio.create_task(self._loop())

  async def _loop(self):
    while True:
      if self._sm is None or not self._clients:
        await asyncio.sleep(0.1)
        continue
      try:
        self._sm.update(100)
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
          frames = list(self._latest.values())
          payload = json.dumps({"type": "can", "frames": frames})
          dead = set()
          for ws in self._clients:
            try:
              await ws.send_str(payload)
            except Exception:
              dead.add(ws)
          self._clients -= dead
          self._last_send = now
        else:
          await asyncio.sleep(0.01)
      except Exception as e:
        cloudlog.error(f"cabana: broadcaster error: {e}")
        await asyncio.sleep(0.5)

  def add(self, ws: web.WebSocketResponse):
    self._clients.add(ws)
    self.start()

  def remove(self, ws: web.WebSocketResponse):
    self._clients.discard(ws)


LIVE_CAN = LiveCanBroadcaster()

async def ws_live(request: web.Request) -> web.WebSocketResponse:
  ws = web.WebSocketResponse()
  await ws.prepare(request)
  LIVE_CAN.add(ws)
  if LIVE_CAN._sm is None:
    await ws.send_str(json.dumps({
      "type": "error",
      "code": "live_can_unavailable",
      "error": "Live CAN requires comma device and cereal messaging (use replay mode on PC).",
    }, ensure_ascii=False))
  try:
    async for _ in ws:
      pass
  finally:
    LIVE_CAN.remove(ws)
  return ws
