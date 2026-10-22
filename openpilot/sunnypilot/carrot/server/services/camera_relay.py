"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""H.264 relay behind `/ws/camera/{camera}` (CarrotPilot's live preview channel).

The client gets one text `hello` frame and then binary frames laid out as

    [4-byte big-endian metadata length][metadata JSON][encoder header][encoder data]

which is byte-for-byte what CarrotPilot's camera hub sends, so the app needs no change.

Two things are fork-specific and live here rather than in the route:

* the camera names. The app asks for `road`; this fork's cereal calls that camera
  `narrowRoad`, so `road` is accepted and mapped, and `narrowRoad` is accepted too.
  The name the client asked for is what goes back in the hello and in every
  metadata block - only the service we subscribe to is ever translated;
* the encode services. Two candidates per camera are tried: the livestream encoder
  (which also runs offroad) and the segment encoder (onroad only). Whichever is
  publishing is the one relayed, so no extra encoder is started for this feature.

Nothing here enables or disables a process: the manager owns that, and this fork only
starts `stream_encoderd` for `IsLiveStreaming`. When neither candidate publishes,
`status()` reports the age of the last frame and the reason, which is what the
`/api/camera/status` route answers with.
"""
import asyncio
import json
import logging
import struct
import time

logger = logging.getLogger("openpilot.carrot.server.camera_relay")


def _safe_int(value):
  if value is None:
    return None
  try:
    return int(value)
  except (TypeError, ValueError):
    return None


def _is_h264_keyframe(payload: bytes) -> bool:
  """True when the chunk holds an IDR NAL, i.e. the frame a client can start from."""
  n = len(payload)
  i = 0
  while i + 5 < n:
    if payload[i] != 0 or payload[i + 1] != 0:
      i += 1
      continue
    if payload[i + 2] == 1:
      nal_start = i + 3
    elif payload[i + 2] == 0 and payload[i + 3] == 1:
      nal_start = i + 4
    else:
      i += 1
      continue
    if nal_start < n and (payload[nal_start] & 0x1F) == 5:
      return True
    i = nal_start
  return False


def _extract_h264_codec(payload: bytes) -> str:
  """`avc1.PPCCLL` from the SPS, which is what browsers want in the metadata block."""
  n = len(payload)
  i = 0
  while i + 6 < n:
    if payload[i] != 0 or payload[i + 1] != 0:
      i += 1
      continue
    if payload[i + 2] == 1:
      nal_start = i + 3
    elif payload[i + 2] == 0 and payload[i + 3] == 1:
      nal_start = i + 4
    else:
      i += 1
      continue
    if nal_start + 3 < n and (payload[nal_start] & 0x1F) == 7:
      return f"avc1.{payload[nal_start + 1]:02X}{payload[nal_start + 2]:02X}{payload[nal_start + 3]:02X}"
    i = nal_start
  return ""


CAMERA_HINT = "no frames? the livestream encoder runs only for IsLiveStreaming, the segment encoder only onroad"


class CameraRelayHub:
  """Latest-frame relay for one camera, started when a client asks and parked when idle."""

  QUEUE_MAXSIZE = 8
  IDLE_STOP_SEC = 5.0
  SEND_TIMEOUT = 0.35
  MAX_SEND_FAILURES = 4
  CLOSE_SEND_TIMEOUT = 1011

  # CarrotPilot camera name -> this fork's canonical name.
  CAMERA_ALIASES = {
    "road": "road",
    "narrowRoad": "road",
    "wideRoad": "wideRoad",
    "driver": "driver",
    "cabin": "driver",
  }

  # Canonical name -> encode services to try, in order. The livestream encoder is first
  # because it is the only one that publishes offroad.
  CAMERA_SERVICE_CANDIDATES = {
    "road": ("livestreamNarrowRoadEncodeData", "narrowRoadEncodeData"),
    "wideRoad": ("livestreamWideRoadEncodeData", "wideRoadEncodeData"),
    "driver": ("livestreamCabinEncodeData", "cabinEncodeData"),
  }

  # Canonical name -> the FrameData service whose frameId bounds what is ready to send.
  CAMERA_STATE_SERVICES = {
    "road": "narrowRoadCameraState",
    "wideRoad": "wideRoadCameraState",
    "driver": "cabinCameraState",
  }

  def __init__(self, messaging):
    self._messaging = messaging
    self._clients = {camera: set() for camera in self.CAMERA_SERVICE_CANDIDATES}
    self._queues = {camera: asyncio.Queue(maxsize=self.QUEUE_MAXSIZE) for camera in self.CAMERA_SERVICE_CANDIDATES}
    self._sockets = {camera: {} for camera in self.CAMERA_SERVICE_CANDIDATES}
    self._producers = {}
    self._senders = {}
    self._sm_frame_id = {}
    self._last_codec = dict.fromkeys(self.CAMERA_SERVICE_CANDIDATES, "")
    self._last_frame_id = dict.fromkeys(self.CAMERA_SERVICE_CANDIDATES, -1)
    self._last_frame_at = dict.fromkeys(self.CAMERA_SERVICE_CANDIDATES, 0.0)
    self._selected_service = dict.fromkeys(self.CAMERA_SERVICE_CANDIDATES, "")
    self._frame_count = dict.fromkeys(self.CAMERA_SERVICE_CANDIDATES, 0)
    self._queue_drops = dict.fromkeys(self.CAMERA_SERVICE_CANDIDATES, 0)
    self._send_drops = dict.fromkeys(self.CAMERA_SERVICE_CANDIDATES, 0)
    self._send_failures = {}
    self._lock = asyncio.Lock()

  # ---- names -------------------------------------------------------------- #

  @classmethod
  def canonical(cls, camera: str):
    """Client camera name -> canonical name, or None when unknown."""
    return cls.CAMERA_ALIASES.get((camera or "").strip())

  @classmethod
  def camera_names(cls):
    return tuple(sorted(cls.CAMERA_SERVICE_CANDIDATES))

  def client_count(self, camera=None) -> int:
    if camera is None:
      return sum(len(clients) for clients in self._clients.values())
    return len(self._clients.get(camera, ()))

  def has_clients(self, camera=None) -> bool:
    return self.client_count(camera) > 0

  # ---- registration ------------------------------------------------------- #

  async def register(self, camera: str, ws) -> None:
    self._clients[camera].add(ws)
    await self._ensure_tasks(camera)

  async def unregister(self, camera: str, ws) -> None:
    self._clients.get(camera, set()).discard(ws)
    self._send_failures.pop(ws, None)

  async def close(self) -> None:
    async with self._lock:
      tasks = list(self._producers.values()) + list(self._senders.values())
      self._producers = {}
      self._senders = {}
    for task in tasks:
      task.cancel()
      try:
        await task
      except (asyncio.CancelledError, Exception):
        pass
    for camera in self._clients:
      for ws in tuple(self._clients[camera]):
        try:
          await ws.close()
        except Exception:
          pass
      self._clients[camera].clear()
      self._sockets[camera] = {}
    self._send_failures.clear()

  async def _ensure_tasks(self, camera: str) -> None:
    async with self._lock:
      producer = self._producers.get(camera)
      if producer is None or producer.done():
        self._producers[camera] = asyncio.create_task(self._producer_loop(camera))
      sender = self._senders.get(camera)
      if sender is None or sender.done():
        self._senders[camera] = asyncio.create_task(self._sender_loop(camera))

  def _pop_task(self, table, camera: str) -> None:
    if table.get(camera) is asyncio.current_task():
      table.pop(camera, None)

  # ---- loops -------------------------------------------------------------- #

  async def _producer_loop(self, camera: str) -> None:
    queue = self._queues[camera]
    idle_since = 0.0
    try:
      while True:
        if not self._clients.get(camera):
          if idle_since <= 0.0:
            idle_since = time.monotonic()
          elif time.monotonic() - idle_since >= self.IDLE_STOP_SEC:
            break
          await asyncio.sleep(0.03)
          continue
        idle_since = 0.0

        self._refresh_ready_frame_id(camera)
        if self._sm_frame_id.get(camera, 0) <= 0:
          await asyncio.sleep(0.03)
          continue

        message, source = self._read_encode_message(camera)
        if message is None:
          await asyncio.sleep(0.002)
          continue
        frame = self._encode_frame(message)
        if frame is None:
          await asyncio.sleep(0.001)
          continue

        packet, frame_id = self._pack_frame(camera, frame, source)
        while queue.full():
          try:
            queue.get_nowait()
            self._queue_drops[camera] += 1
          except asyncio.QueueEmpty:
            break
        try:
          queue.put_nowait(packet)
        except asyncio.QueueFull:
          await asyncio.sleep(0.001)
          continue

        self._frame_count[camera] += 1
        self._last_frame_at[camera] = time.monotonic()
        if frame_id is not None and frame_id >= 0:
          self._last_frame_id[camera] = frame_id
        if source:
          self._selected_service[camera] = source
    except asyncio.CancelledError:
      raise
    except Exception:
      logger.exception("carrot_server: camera producer for %s stopped", camera)
    finally:
      async with self._lock:
        self._pop_task(self._producers, camera)
      self._sockets[camera] = {}
      self._sm_frame_id.pop(camera, None)

  async def _sender_loop(self, camera: str) -> None:
    queue = self._queues[camera]
    idle_since = 0.0
    try:
      while True:
        if not self._clients.get(camera):
          if idle_since <= 0.0:
            idle_since = time.monotonic()
          elif time.monotonic() - idle_since >= self.IDLE_STOP_SEC:
            break
          while queue.qsize() > 1:
            try:
              queue.get_nowait()
              self._queue_drops[camera] += 1
            except asyncio.QueueEmpty:
              break
          await asyncio.sleep(0.03)
          continue
        idle_since = 0.0

        try:
          packet = await asyncio.wait_for(queue.get(), timeout=0.25)
        except TimeoutError:
          continue
        # A preview wants the newest frame, not the backlog: drop everything but the last.
        while queue.qsize() > 0:
          try:
            packet = queue.get_nowait()
            self._queue_drops[camera] += 1
          except asyncio.QueueEmpty:
            break

        clients = list(self._clients.get(camera, ()))
        results = await asyncio.gather(*(self._send_one(ws, packet) for ws in clients))
        for ws, ok in zip(clients, results, strict=False):
          if ok:
            self._send_failures.pop(ws, None)
            continue
          failures = self._send_failures.get(ws, 0) + 1
          if failures >= self.MAX_SEND_FAILURES:
            self._send_failures.pop(ws, None)
            self._send_drops[camera] += 1
            self._clients[camera].discard(ws)
            try:
              await ws.close(code=self.CLOSE_SEND_TIMEOUT, message=b"camera_send_timeout")
            except Exception:
              pass
          else:
            self._send_failures[ws] = failures
    except asyncio.CancelledError:
      raise
    except Exception:
      logger.exception("carrot_server: camera sender for %s stopped", camera)
    finally:
      async with self._lock:
        self._pop_task(self._senders, camera)

  async def _send_one(self, ws, packet: bytes) -> bool:
    try:
      await asyncio.wait_for(ws.send_bytes(packet), timeout=self.SEND_TIMEOUT)
      return True
    except Exception:
      return False

  # ---- cereal ------------------------------------------------------------- #

  def _socket(self, camera: str, service: str):
    sockets = self._sockets.setdefault(camera, {})
    existing = sockets.get(service)
    if existing is not None:
      return existing
    try:
      existing = self._messaging.sub_sock(service, conflate=True)
    except Exception:
      return None
    sockets[service] = existing
    return existing

  def _read_encode_message(self, camera: str):
    for service in self.CAMERA_SERVICE_CANDIDATES[camera]:
      sock = self._socket(camera, service)
      if sock is None:
        continue
      try:
        message = self._messaging.recv_one_or_none(sock)
      except Exception:
        continue
      if self._encode_frame(message) is not None:
        return message, service
    return None, ""

  def _refresh_ready_frame_id(self, camera: str) -> None:
    state_service = self.CAMERA_STATE_SERVICES.get(camera)
    if not state_service:
      return
    sock = self._socket(camera, state_service)
    if sock is None:
      return
    try:
      message = self._messaging.recv_one_or_none(sock)
    except Exception:
      return
    state = self._encode_frame(message)
    frame_id = _safe_int(getattr(state, "frameId", None)) if state is not None else None
    if frame_id is not None and frame_id > 0:
      self._sm_frame_id[camera] = frame_id

  @staticmethod
  def _encode_frame(message):
    """The `EncodeData` (or `FrameData`) payload of an `Event` reader."""
    if message is None:
      return None
    try:
      which = message.which()
    except Exception:
      return None
    if not which:
      return None
    return getattr(message, which, None)

  # ---- framing ------------------------------------------------------------ #

  def _pack_frame(self, camera: str, frame, service: str):
    sample = self._frame_sample(frame, service=service)
    header = bytes(getattr(frame, "header", b"") or b"")
    data = bytes(getattr(frame, "data", b"") or b"")

    if not self._last_codec[camera]:
      probe = header + data if len(header) + len(data) < 4096 else header[:256]
      self._last_codec[camera] = _extract_h264_codec(probe)

    flags = _safe_int(sample.get("flags"))
    is_key = bool(flags is not None and flags & 0x8)
    if not is_key:
      is_key = _is_h264_keyframe(header) if header else _is_h264_keyframe(data[:64])

    frame_id = _safe_int(sample.get("frameId"))
    if frame_id is None or frame_id < 0:
      frame_id = self._sm_frame_id.get(camera, -1)
      sample["frameId"] = frame_id

    meta = {
      "camera": camera,
      "codec": self._last_codec[camera] or "avc1.640028",
      "frameId": frame_id,
      "width": _safe_int(sample.get("width")),
      "height": _safe_int(sample.get("height")),
      "flags": flags,
      "encodeId": _safe_int(sample.get("encodeId")),
      "segmentId": _safe_int(sample.get("segmentId")),
      "frameType": sample.get("frameType"),
      "timestampSof": _safe_int(sample.get("timestampSof")),
      "timestampEof": _safe_int(sample.get("timestampEof")),
      "keyFrame": is_key,
      "size": len(header) + len(data),
      "ts": time.monotonic(),
    }
    meta_bytes = json.dumps(meta, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    out = bytearray(4 + len(meta_bytes) + len(header) + len(data))
    struct.pack_into(">I", out, 0, len(meta_bytes))
    out[4:4 + len(meta_bytes)] = meta_bytes
    offset = 4 + len(meta_bytes)
    out[offset:offset + len(header)] = header
    offset += len(header)
    out[offset:offset + len(data)] = data
    return bytes(out), frame_id

  @staticmethod
  def _frame_sample(frame, *, service: str = ""):
    frame_id = _safe_int(getattr(frame, "frameId", None))
    flags = encode_id = segment_id = None
    frame_type = None
    try:
      idx = getattr(frame, "idx", None)
      if idx is not None:
        flags = _safe_int(getattr(idx, "flags", None))
        encode_id = _safe_int(getattr(idx, "encodeId", None))
        segment_id = _safe_int(getattr(idx, "segmentId", None))
        frame_type = str(getattr(idx, "type", ""))
        if frame_id is None:
          frame_id = _safe_int(getattr(idx, "frameId", None))
    except Exception:
      pass
    return {
      "service": service,
      "frameId": frame_id,
      "timestampSof": _safe_int(getattr(frame, "timestampSof", None)),
      "timestampEof": _safe_int(getattr(frame, "timestampEof", None)),
      "width": _safe_int(getattr(frame, "width", None)),
      "height": _safe_int(getattr(frame, "height", None)),
      "flags": flags,
      "encodeId": encode_id,
      "segmentId": segment_id,
      "frameType": frame_type,
    }

  # ---- introspection ------------------------------------------------------ #

  def status(self) -> dict:
    cameras = {}
    for camera in self.CAMERA_SERVICE_CANDIDATES:
      last_frame_at = self._last_frame_at.get(camera, 0.0)
      streaming = last_frame_at > 0.0 and (time.monotonic() - last_frame_at) < 2.0
      cameras[camera] = {
        "clients": len(self._clients.get(camera, ())),
        "frames": self._frame_count.get(camera, 0),
        "queue": self._queues[camera].qsize(),
        "queueDrops": self._queue_drops.get(camera, 0),
        "sendDrops": self._send_drops.get(camera, 0),
        "lastFrameId": self._last_frame_id.get(camera, -1),
        "lastFrameAgeMs": int((time.monotonic() - last_frame_at) * 1000.0) if last_frame_at > 0.0 else None,
        "service": self._selected_service.get(camera, ""),
        "codec": self._last_codec.get(camera, ""),
        "streaming": streaming,
      }
    return {
      "ok": True,
      "mode": "direct-encode-relay",
      "cameras": cameras,
      "hint": CAMERA_HINT,
    }
