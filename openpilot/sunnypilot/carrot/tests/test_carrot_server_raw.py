"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Tests for the port-7000 raw cereal relay (`/ws/raw_multiplex`).

The relay is the app's main data channel, so two things matter and are pinned here:

* the service-name mapping. The app requests CarrotPilot's names - including `carrotMan`,
  which this fork does not publish - so the alias table has to translate at the edge while
  keeping the name the client asked for in the frame prefix;
* the framing, which the app parses byte by byte: `[len(name)][name][capnp payload]`.

The relay tests use a fake `messaging` and a fake WebSocket, so they run without zmq,
aiohttp or a device; the HTTP tests need aiohttp and are skipped elsewhere.
"""
import asyncio
import json
import unittest

from openpilot.sunnypilot.carrot.server.services.raw_protocol import (
  RAW_MULTIPLEX_MODE,
  RAW_MULTIPLEX_WIRE_FORMAT,
  build_raw_hello,
  build_raw_multiplex_hello,
  encode_raw_multiplex_frame,
)
from openpilot.sunnypilot.carrot.server.services.raw_relay import RawRelayHub
from openpilot.sunnypilot.carrot.server.services.raw_services import (
  is_supported_raw_service,
  resolve_service,
  resolve_services,
)

try:
  from aiohttp.test_utils import TestClient, TestServer

  _HAVE_AIOHTTP = True
except Exception:
  _HAVE_AIOHTTP = False


class TestFraming(unittest.TestCase):
  def test_multiplex_hello_matches_the_documented_shape(self):
    hello = build_raw_multiplex_hello(services=['carState', 'modelV2'])
    self.assertEqual(hello['type'], 'hello')
    self.assertEqual(hello['services'], ['carState', 'modelV2'])
    self.assertEqual(hello['protocolVersion'], 1)
    self.assertEqual(hello['mode'], RAW_MULTIPLEX_MODE)
    self.assertEqual(hello['wireFormat'], RAW_MULTIPLEX_WIRE_FORMAT)

  def test_single_hello_shape(self):
    hello = build_raw_hello(service='carState')
    self.assertEqual(hello['service'], 'carState')
    self.assertEqual(hello['type'], 'hello')

  def test_a_frame_is_length_prefixed_name_plus_payload(self):
    frame = encode_raw_multiplex_frame(service='carState', payload=b'\x01\x02\x03')
    self.assertEqual(frame[0], len('carState'))
    self.assertEqual(frame[1:1 + len('carState')], b'carState')
    self.assertEqual(frame[1 + len('carState'):], b'\x01\x02\x03')

  def test_an_over_long_service_name_is_refused(self):
    with self.assertRaises(ValueError):
      encode_raw_multiplex_frame(service='x' * 256, payload=b'')


class TestServiceMapping(unittest.TestCase):
  def test_carrotman_is_served_from_the_fork_service(self):
    # The app asks for carrotMan; this fork publishes carrotManSP, whose capnp fields are a
    # superset with the same ordinals, so the payload is byte-compatible.
    self.assertEqual(resolve_service('carrotMan'), 'carrotManSP')
    self.assertEqual(resolve_service('carrotNavi'), 'carrotNaviSP')

  def test_a_fork_name_is_accepted_too(self):
    self.assertEqual(resolve_service('carrotManSP'), 'carrotManSP')

  def test_stock_names_pass_through(self):
    for name in ('carState', 'modelV2', 'selfdriveState'):
      self.assertEqual(resolve_service(name), name)
      self.assertTrue(is_supported_raw_service(name))

  def test_unknown_names_are_dropped(self):
    self.assertIsNone(resolve_service('definitelyNotAService'))
    self.assertFalse(is_supported_raw_service('definitelyNotAService'))

  def test_resolve_services_keeps_client_names_and_drops_unknown(self):
    resolved = resolve_services(['carState', 'carrotMan', 'nope', 'carState', ' modelV2 '])
    self.assertEqual(resolved, [('carState', 'carState'), ('carrotMan', 'carrotManSP'), ('modelV2', 'modelV2')])


class _FakeSock:
  def __init__(self, payloads):
    self.payloads = list(payloads)
    self.closed = False

  def receive(self, non_blocking=False):
    if not self.payloads:
      return None
    return self.payloads.pop(0)

  def close(self):
    self.closed = True


class _FakeMessaging:
  def __init__(self, per_service):
    self.per_service = per_service
    self.subscribed = []

  def sub_sock(self, service, conflate=False):
    self.subscribed.append(service)
    return _FakeSock(self.per_service.get(service, []))


class _FakeWs:
  def __init__(self):
    self.frames = []
    self.closed = False
    self.close_calls = []

  async def send_bytes(self, data):
    self.frames.append(data)

  async def close(self, code=None, message=b''):
    self.closed = True
    self.close_calls.append((code, message))


class TestRawRelayHub(unittest.IsolatedAsyncioTestCase):
  async def _hub_with(self, per_service):
    messaging = _FakeMessaging(per_service)
    hub = RawRelayHub(messaging)
    ws = _FakeWs()
    await hub.register([('carrotMan', 'carrotManSP'), ('carState', 'carState')], ws)
    return hub, ws, messaging

  async def test_frames_are_prefixed_with_the_name_the_client_asked_for(self):
    hub, ws, messaging = await self._hub_with({'carrotManSP': [b'CARROT'], 'carState': [b'STATE']})
    for _ in range(60):
      if len(ws.frames) >= 2:
        break
      await asyncio.sleep(0.02)
    await hub.close()

    by_name = {}
    for frame in ws.frames:
      length = frame[0]
      by_name[frame[1:1 + length].decode()] = frame[1 + length:]
    self.assertIn('carrotMan', by_name, 'the client name must be used, not the fork name')
    self.assertIn('carState', by_name)
    self.assertEqual(by_name['carrotMan'], b'CARROT')
    self.assertEqual(by_name['carState'], b'STATE')
    self.assertIn('carrotManSP', messaging.subscribed)

  async def test_it_only_forwards_the_newest_sample_per_service(self):
    hub, ws, _ = await self._hub_with({'carState': [b'one', b'two', b'three']})
    await asyncio.sleep(0.12)
    await hub.close()
    self.assertEqual(ws.frames[-1], encode_raw_multiplex_frame(service='carState', payload=b'three'))

  async def test_a_slow_client_is_dropped_without_killing_the_hub(self):
    hub, ws, _ = await self._hub_with({'carState': [b'x'] * 5})

    async def _slow(_data):
      raise TimeoutError('pretend the socket stalled')

    ws.send_bytes = _slow
    hub.SEND_TIMEOUT = 0.05
    for _ in range(80):
      if ws.closed:
        break
      await asyncio.sleep(0.02)
    self.assertTrue(ws.closed, 'a stalled client must be closed, not left half-registered')
    self.assertEqual(hub.client_count(), 0)
    await hub.close()

  async def test_unregister_stops_delivery(self):
    hub, ws, _ = await self._hub_with({'carState': [b'x'] * 5})
    await hub.unregister(ws)
    ws.frames.clear()
    await asyncio.sleep(0.1)
    await hub.close()
    self.assertEqual(ws.frames, [])

  async def test_no_services_means_no_subscription(self):
    messaging = _FakeMessaging({})
    hub = RawRelayHub(messaging)
    ws = _FakeWs()
    await hub.register([], ws)
    await asyncio.sleep(0.05)
    await hub.close()
    self.assertEqual(messaging.subscribed, [])
    self.assertEqual(ws.frames, [])


class _unloadable_raw_relay:
  """Make `RawRelayHub(...)` raise, as it would on a host without zmq/capnp."""

  def __enter__(self):
    import sys
    import types

    self._name = 'openpilot.sunnypilot.carrot.server.services.raw_relay'
    self._saved = sys.modules.get(self._name)

    class _BrokenHub:
      def __init__(self, messaging):
        raise RuntimeError('cereal unavailable (forced)')

    module = types.ModuleType(self._name)
    module.RawRelayHub = _BrokenHub
    sys.modules[self._name] = module
    return self

  def __exit__(self, *_exc):
    import sys

    if self._saved is None:
      sys.modules.pop(self._name, None)
    else:
      sys.modules[self._name] = self._saved
    return False


class _FakeHub:
  """Records what the route asked for, so the route can be tested without cereal."""

  def __init__(self):
    self.registered = []
    self.unregistered = []

  async def register(self, resolved, ws):
    self.registered.append(list(resolved))

  async def unregister(self, ws):
    self.unregistered.append(ws)

  async def close(self):
    pass


@unittest.skipUnless(_HAVE_AIOHTTP, 'needs aiohttp')
class TestRawEndpoints(unittest.IsolatedAsyncioTestCase):
  async def asyncSetUp(self):
    from openpilot.sunnypilot.carrot.server.app import create_app
    from openpilot.sunnypilot.carrot.server.features.ws import RAW_HUB_KEY

    self.app = create_app(params=_NullParams())
    self.hub = _FakeHub()
    self.app[RAW_HUB_KEY] = self.hub  # injected, so the test never needs zmq
    self.client = TestClient(TestServer(self.app))
    await self.client.start_server()

  async def asyncTearDown(self):
    await self.client.close()

  async def test_multiplex_requires_services(self):
    resp = await self.client.get('/ws/raw_multiplex')
    self.assertEqual(resp.status, 400)

  async def test_multiplex_rejects_only_unknown_names(self):
    resp = await self.client.get('/ws/raw_multiplex?services=nope,nada')
    self.assertEqual(resp.status, 400)

  async def test_single_service_route_rejects_unknown(self):
    resp = await self.client.get('/ws/raw/nope')
    self.assertEqual(resp.status, 404)

  async def test_hello_precedes_the_stream_and_the_alias_is_translated(self):
    ws = await self.client.ws_connect('/ws/raw_multiplex?services=carState,carrotMan')
    try:
      message = await ws.receive(timeout=5)
      self.assertEqual(message.type.name, 'TEXT')
      hello = json.loads(message.data)
      self.assertEqual(hello['type'], 'hello')
      self.assertEqual(hello['services'], ['carState', 'carrotMan'])
      self.assertEqual(self.hub.registered, [[('carState', 'carState'), ('carrotMan', 'carrotManSP')]])
    finally:
      await ws.close()
    for _ in range(50):
      if self.hub.unregistered:
        break
      await asyncio.sleep(0.02)
    self.assertTrue(self.hub.unregistered, 'closing the socket must unregister it')

  async def test_single_service_hello_uses_the_client_name(self):
    ws = await self.client.ws_connect('/ws/raw/carrotMan')
    try:
      hello = json.loads((await ws.receive(timeout=5)).data)
      self.assertEqual(hello['service'], 'carrotMan')
      self.assertEqual(self.hub.registered, [[('carrotMan', 'carrotManSP')]])
    finally:
      await ws.close()

  async def test_missing_cereal_answers_503_rather_than_crashing(self):
    # A host without zmq/capnp must answer 503, not fail to boot. Force the failure in a
    # separate app so the failure cannot be cached in the app under test.
    from openpilot.sunnypilot.carrot.server.app import create_app

    broken_app = create_app(params=_NullParams())
    broken_client = TestClient(TestServer(broken_app))
    await broken_client.start_server()
    try:
      with _unloadable_raw_relay():
        resp = await broken_client.get('/ws/raw_multiplex?services=carState')
        self.assertEqual(resp.status, 503,
                         'without cereal the route must degrade to 503, not raise on import')
        self.assertFalse((await resp.json())['ok'])
    finally:
      await broken_client.close()


class _NullParams:
  """create_app() only stores it; the raw routes never read a parameter."""


if __name__ == '__main__':
  unittest.main()
