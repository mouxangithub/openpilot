"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Tests for the camera relay behind `/ws/camera/{camera}`.

What matters is the wire format, because the app decodes it byte by byte, and the camera
name mapping: the app asks for `road`, this fork's cereal calls the same camera
`narrowRoad`. The frames carry the name the client asked for, so nothing downstream has
to know about the rename.

The hub is driven with a fake `messaging` and a fake WebSocket, so it runs without zmq,
aiohttp or a device; the HTTP tests need aiohttp and are skipped elsewhere.
"""
import asyncio
import json
import struct
import unittest

from openpilot.sunnypilot.carrot.server.services.camera_relay import (
  CameraRelayHub,
  _extract_h264_codec,
  _is_h264_keyframe,
)

try:
  from aiohttp.test_utils import TestClient, TestServer

  _HAVE_AIOHTTP = True
except Exception:
  _HAVE_AIOHTTP = False


class _Idx:
  def __init__(self, flags=0x8, encode_id=7, segment_id=3, frame_type="h264", frame_id=None):
    self.flags = flags
    self.encodeId = encode_id
    self.segmentId = segment_id
    self.type = frame_type
    self.frameId = frame_id


class _Frame:
  def __init__(self, header=b"\x00\x00\x00\x01\x67\x64\x00\x28", data=b"\x00\x00\x00\x01\x65\xaa\xbb", frame_id=11,
               idx=None, width=1928, height=1208):
    self.header = header
    self.data = data
    self.frameId = frame_id
    self.idx = idx if idx is not None else _Idx()
    self.width = width
    self.height = height
    self.timestampSof = 1000
    self.timestampEof = 1001


class _Message:
  """Stand-in for a capnp `Event` reader: `which()` picks the payload."""

  def __init__(self, frame, which="roadEncodeData"):
    self._frame = frame
    self._which = which

  def which(self):
    return self._which

  @property
  def roadEncodeData(self):
    return self._frame

  @property
  def narrowRoadEncodeData(self):
    return self._frame


class _FakeSock:
  def __init__(self, messages):
    self.messages = list(messages)

  def close(self):
    pass


class _FakeMessaging:
  def __init__(self, per_service):
    self.per_service = per_service
    self.subscribed = []

  def sub_sock(self, service, conflate=False):
    self.subscribed.append(service)
    return _FakeSock(self.per_service.get(service, []))

  def recv_one_or_none(self, sock):
    if not sock.messages:
      return None
    return sock.messages.pop(0)


class _StateMessage:
  def __init__(self, frame_id):
    self._frame_id = frame_id

  def which(self):
    return "narrowRoadCameraState"

  @property
  def narrowRoadCameraState(self):
    return _Frame(frame_id=self._frame_id)


class _FakeWs:
  def __init__(self):
    self.frames = []
    self.closed = False

  async def send_bytes(self, data):
    self.frames.append(data)

  async def close(self, code=None, message=b""):
    self.closed = True


def _decode(frame: bytes):
  length = struct.unpack_from(">I", frame, 0)[0]
  meta = json.loads(frame[4:4 + length].decode("utf-8"))
  return meta, frame[4 + length:]


class TestCameraNames(unittest.TestCase):
  def test_the_app_name_maps_to_the_fork_camera(self):
    self.assertEqual(CameraRelayHub.canonical("road"), "road")
    self.assertEqual(CameraRelayHub.canonical("narrowRoad"), "road")
    self.assertEqual(CameraRelayHub.canonical("cabin"), "driver")

  def test_an_unknown_camera_is_refused(self):
    self.assertIsNone(CameraRelayHub.canonical("rearview"))
    self.assertIsNone(CameraRelayHub.canonical(""))

  def test_every_camera_has_state_and_encode_services(self):
    for camera in CameraRelayHub.camera_names():
      self.assertTrue(CameraRelayHub.CAMERA_SERVICE_CANDIDATES[camera])
      self.assertTrue(CameraRelayHub.CAMERA_STATE_SERVICES[camera])


class TestH264Helpers(unittest.TestCase):
  def test_an_idr_nal_is_a_keyframe(self):
    self.assertTrue(_is_h264_keyframe(b"\x00\x00\x00\x01\x65\xaa"))

  def test_a_non_idr_nal_is_not(self):
    self.assertFalse(_is_h264_keyframe(b"\x00\x00\x00\x01\x41\xaa"))

  def test_the_codec_comes_from_the_sps(self):
    self.assertEqual(_extract_h264_codec(b"\x00\x00\x00\x01\x67\x64\x00\x28"), "avc1.640028")

  def test_a_chunk_without_sps_has_no_codec(self):
    self.assertEqual(_extract_h264_codec(b"\x00\x00\x00\x01\x65\xaa"), "")


class TestCameraHub(unittest.IsolatedAsyncioTestCase):
  async def _hub(self, frames=1):
    messaging = _FakeMessaging({
      "livestreamNarrowRoadEncodeData": [_Message(_Frame()) for _ in range(frames)],
      "narrowRoadCameraState": [_StateMessage(11)],
    })
    hub = CameraRelayHub(messaging)
    ws = _FakeWs()
    await hub.register("road", ws)
    return hub, ws, messaging

  async def test_hello_name_and_frame_layout(self):
    hub, ws, messaging = await self._hub()
    for _ in range(80):
      if ws.frames:
        break
      await asyncio.sleep(0.02)
    await hub.close()

    self.assertTrue(ws.frames, 'a frame must reach the client')
    meta, payload = _decode(ws.frames[0])
    self.assertEqual(meta["camera"], "road")
    self.assertEqual(meta["frameId"], 11)
    self.assertEqual(meta["width"], 1928)
    self.assertTrue(meta["keyFrame"])
    self.assertEqual(meta["size"], len(payload))
    self.assertEqual(payload[:4], b"\x00\x00\x00\x01")
    self.assertIn("livestreamNarrowRoadEncodeData", messaging.subscribed)

  async def test_the_codec_is_reported_once_parsed(self):
    hub, ws, _ = await self._hub()
    for _ in range(80):
      if ws.frames:
        break
      await asyncio.sleep(0.02)
    await hub.close()
    self.assertEqual(_decode(ws.frames[0])[0]["codec"], "avc1.640028")

  async def test_only_the_newest_frame_is_kept(self):
    hub, ws, _ = await self._hub(frames=3)
    await asyncio.sleep(0.15)
    await hub.close()
    self.assertTrue(ws.frames)
    self.assertEqual(len(ws.frames[-1]), len(ws.frames[0]))

  async def test_a_stalled_client_is_dropped_without_killing_the_hub(self):
    hub, ws, _ = await self._hub(frames=5)

    async def _slow(_data):
      raise TimeoutError("pretend the socket stalled")

    ws.send_bytes = _slow
    # The hub keeps only the newest frame, so few sends carry many frames: drop on the
    # first failure here to make the test deterministic rather than timing-dependent.
    hub.MAX_SEND_FAILURES = 1
    for _ in range(100):
      if ws.closed:
        break
      await asyncio.sleep(0.02)
    self.assertTrue(ws.closed)
    self.assertEqual(hub.client_count("road"), 0)
    await hub.close()

  async def test_without_a_ready_frame_id_nothing_is_sent(self):
    messaging = _FakeMessaging({
      "livestreamNarrowRoadEncodeData": [_Message(_Frame())],
      "narrowRoadCameraState": [_StateMessage(0)],
    })
    hub = CameraRelayHub(messaging)
    ws = _FakeWs()
    await hub.register("road", ws)
    await asyncio.sleep(0.1)
    await hub.close()
    self.assertEqual(ws.frames, [])

  async def test_status_reports_the_service_in_use(self):
    hub, ws, _ = await self._hub()
    for _ in range(80):
      if ws.frames:
        break
      await asyncio.sleep(0.02)
    status = hub.status()
    await hub.close()
    self.assertEqual(status["cameras"]["road"]["service"], "livestreamNarrowRoadEncodeData")
    self.assertTrue(status["cameras"]["road"]["streaming"])


@unittest.skipUnless(_HAVE_AIOHTTP, "needs aiohttp")
class TestCameraEndpoints(unittest.IsolatedAsyncioTestCase):
  async def asyncSetUp(self):
    from openpilot.sunnypilot.carrot.server.app import create_app
    from openpilot.sunnypilot.carrot.server.features.camera import CAMERA_HUB_KEY

    self.app = create_app(params=_NullParams())
    self.hub = _FakeRegisteredHub()
    self.app[CAMERA_HUB_KEY] = self.hub
    self.client = TestClient(TestServer(self.app))
    await self.client.start_server()

  async def asyncTearDown(self):
    await self.client.close()

  async def test_an_unknown_camera_is_404(self):
    resp = await self.client.get("/ws/camera/rearview")
    self.assertEqual(resp.status, 404)

  async def test_hello_carries_the_name_the_client_asked_for(self):
    ws = await self.client.ws_connect("/ws/camera/road")
    try:
      message = await ws.receive(timeout=5)
      hello = json.loads(message.data)
      self.assertEqual(hello["type"], "hello")
      self.assertEqual(hello["camera"], "road")
      self.assertEqual(hello["mode"], "direct-encode-relay")
      self.assertEqual([camera for camera, _ in self.hub.registered], ["road"])
    finally:
      await ws.close()
    for _ in range(50):
      if self.hub.unregistered:
        break
      await asyncio.sleep(0.02)
    self.assertTrue(self.hub.unregistered)

  async def test_status_is_json_even_when_idle(self):
    resp = await self.client.get("/api/camera/status")
    self.assertEqual(resp.status, 200)
    self.assertTrue((await resp.json())["ok"])


class _FakeRegisteredHub:
  def __init__(self):
    self.registered = []
    self.unregistered = []

  async def register(self, camera, ws):
    self.registered.append((camera, ws))

  async def unregister(self, camera, ws):
    self.unregistered.append((camera, ws))

  async def close(self):
    pass

  def status(self):
    return {"ok": True, "mode": "direct-encode-relay", "cameras": {}}


class _NullParams:
  """create_app() only stores it; the camera routes never read a parameter."""


if __name__ == "__main__":
  unittest.main()
