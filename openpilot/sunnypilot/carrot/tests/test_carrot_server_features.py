"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Tests for the device-facing routes on port 7000: settings, system, cars, navi, eGPU.

These are the routes a phone hits while the car is parked, so the property that matters
most is that they answer with JSON in every state - including the states where the thing
they describe is missing (no zmq, no eGPU, no opendbc). A 500 or a traceback on a device
that simply has no eGPU is the failure this pins down.

`LiveRuntime` is tested with a fake `messaging` so it needs neither zmq nor capnp.
"""
import unittest

from openpilot.sunnypilot.carrot.server.services.device_info import listening_ports
from openpilot.sunnypilot.carrot.server.services.live_runtime import LiveRuntime, json_safe
from openpilot.sunnypilot.carrot.server.services.settings import _group_for, _type_of

try:
  from aiohttp.test_utils import TestClient, TestServer

  _HAVE_AIOHTTP = True
except Exception:
  _HAVE_AIOHTTP = False


class _State:
  def __init__(self, **fields):
    self.__dict__.update(fields)

  def to_dict(self):
    return dict(self.__dict__)


class _Message:
  def __init__(self, which, payload):
    self._which = which
    self._payload = payload

  def which(self):
    return self._which

  def __getattr__(self, name):
    if name == self._which:
      return self._payload
    raise AttributeError(name)


class _FakeSock:
  def __init__(self, messages):
    self.messages = list(messages)
    self.closed = False

  def close(self):
    self.closed = True


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


class TestJsonSafe(unittest.TestCase):
  def test_scalars_pass_through(self):
    self.assertEqual(json_safe(1), 1)
    self.assertEqual(json_safe("x"), "x")
    self.assertTrue(json_safe(True))

  def test_bytes_are_decoded(self):
    self.assertEqual(json_safe(b"hi"), "hi")

  def test_lists_are_bounded(self):
    self.assertEqual(len(json_safe(list(range(1000)))), 32)

  def test_nesting_is_bounded(self):
    # Past MAX_DEPTH the value is replaced with None instead of recursing forever.
    deep = {"a": {"b": {"c": {"d": {"e": {"f": {"g": 1}}}}}}}
    self.assertEqual(json_safe(deep)["a"]["b"]["c"]["d"]["e"]["f"], {"g": None})

  def test_a_capnp_like_object_is_converted(self):
    self.assertEqual(json_safe(_State(vEgo=1.5)), {"vEgo": 1.5})

  def test_an_unconvertible_object_becomes_a_string(self):
    class _Broken:
      def to_dict(self):
        raise RuntimeError("nope")

    self.assertTrue(json_safe(_Broken()).startswith("<"))


class TestLiveRuntime(unittest.TestCase):
  def _runtime(self, services=None):
    messaging = _FakeMessaging({
      "selfdriveState": [_Message("selfdriveState", _State(enabled=True, active=False))],
      "deviceState": [_Message("deviceState", _State(chestnutPresent=True))],
    })
    return LiveRuntime(messaging, services) if services else LiveRuntime(messaging)

  def test_newest_sample_is_decoded_per_service(self):
    runtime = self._runtime(("selfdriveState", "deviceState"))
    runtime.poll()
    snapshot = runtime.snapshot()
    self.assertTrue(snapshot["ok"])
    self.assertEqual(snapshot["services"]["selfdriveState"]["enabled"], True)
    self.assertEqual(snapshot["services"]["deviceState"]["chestnutPresent"], True)
    self.assertEqual(sorted(snapshot["meta"]["services"]), ["deviceState", "selfdriveState"])

  def test_a_missing_service_is_absent_not_fatal(self):
    runtime = self._runtime(("notARealService",))
    runtime.poll()
    self.assertEqual(runtime.snapshot()["services"], {})

  def test_engagement_reads_selfdrive_state(self):
    runtime = self._runtime(("selfdriveState",))
    runtime.poll()
    self.assertTrue(runtime.is_engaged())

  def test_a_second_poll_keeps_the_previous_sample(self):
    runtime = self._runtime(("selfdriveState",))
    runtime.poll()
    runtime.poll()
    self.assertTrue(runtime.snapshot()["services"]["selfdriveState"]["enabled"])

  def test_close_releases_the_sockets(self):
    messaging = _FakeMessaging({"selfdriveState": []})
    runtime = LiveRuntime(messaging, ("selfdriveState",))
    runtime.poll()
    runtime.close()
    self.assertEqual(runtime._sockets, {})


class TestSettingsCatalog(unittest.TestCase):
  def test_types_follow_the_default(self):
    self.assertEqual(_type_of(True), "bool")
    self.assertEqual(_type_of(3), "int")
    self.assertEqual(_type_of(1.5), "float")
    self.assertEqual(_type_of("x"), "string")

  def test_groups_are_assigned_by_prefix(self):
    self.assertEqual(_group_for("AutoTurnControl"), "navi")
    self.assertEqual(_group_for("TFollowGap1"), "longitudinal")
    self.assertEqual(_group_for("SteerRatioRate"), "lateral")
    self.assertEqual(_group_for("ShowPathEnd"), "display")

  def test_every_key_lands_in_some_group(self):
    self.assertEqual(_group_for("SomethingElse"), "general")


class TestListeningPorts(unittest.TestCase):
  def test_an_unused_port_is_reported_absent(self):
    ports = listening_ports((1,))
    self.assertEqual(ports, {1: False})

  def test_the_probe_never_raises(self):
    self.assertIsInstance(listening_ports((7705, 7706, 7714)), dict)


@unittest.skipUnless(_HAVE_AIOHTTP, "needs aiohttp")
class TestFeatureEndpoints(unittest.IsolatedAsyncioTestCase):
  """Every device-facing route must answer JSON, including when nothing is available."""

  async def asyncSetUp(self):
    from openpilot.sunnypilot.carrot.server.app import create_app

    self.app = create_app(params=_NullParams())
    self.client = TestClient(TestServer(self.app))
    await self.client.start_server()

  async def asyncTearDown(self):
    await self.client.close()

  async def _get_json(self, path):
    resp = await self.client.get(path)
    self.assertEqual(resp.headers.get("Content-Type", "").split(";")[0], "application/json", path)
    return resp.status, await resp.json()

  async def test_health(self):
    status, body = await self._get_json("/api/health")
    self.assertEqual(status, 200)
    self.assertTrue(body["ok"])

  async def test_heartbeat_has_no_heartbeat_yet(self):
    status, body = await self._get_json("/api/heartbeat_status")
    self.assertEqual(status, 200)
    self.assertIsNone(body["hb"])

  async def test_device_network_answers(self):
    status, body = await self._get_json("/api/device_network")
    self.assertEqual(status, 200)
    self.assertIn("network", body)

  async def test_calibration_reports_a_source_even_when_unavailable(self):
    status, body = await self._get_json("/api/calibration_status")
    self.assertEqual(status, 200)
    self.assertIn("source", body["calibration"])

  async def test_carrot_navi_capabilities_mention_the_missing_mode(self):
    status, body = await self._get_json("/api/carrot_navi/capabilities")
    self.assertEqual(status, 200)
    self.assertFalse(body["capabilities"]["compactState"])

  async def test_carrot_navi_status_answers_without_cereal(self):
    status, body = await self._get_json("/api/carrot_navi/status")
    self.assertEqual(status, 200)
    self.assertIn("ports", body)

  async def test_egpu_is_absent_rather_than_an_error(self):
    status, body = await self._get_json("/api/egpu/model")
    self.assertEqual(status, 200)
    self.assertFalse(body["available"])

  async def test_egpu_compile_restart_is_answered_not_honoured(self):
    resp = await self.client.post("/api/egpu/model/compile-restart")
    self.assertEqual(resp.status, 501)

  async def test_setting_unit_index_is_empty_but_present(self):
    status, body = await self._get_json("/api/setting_unit_index")
    self.assertEqual(status, 200)
    self.assertEqual(body["units"], {})

  async def test_bluetooth_status_reports_missing_hardware_as_facts(self):
    status, body = await self._get_json("/api/bluetooth")
    self.assertEqual(status, 200)
    for key in ("hasBluez", "serviceRunning", "hasUart", "hasBtpower", "available"):
      self.assertIn(key, body)

  async def test_bluetooth_mutate_refuses_a_cross_site_write(self):
    resp = await self.client.post("/api/bluetooth/scan", headers={"Sec-Fetch-Site": "cross-site"})
    self.assertEqual(resp.status, 403)

  async def test_time_sync_reports_rather_than_sets_the_clock(self):
    resp = await self.client.post("/api/time_sync", json={"epoch_ms": 1})
    self.assertEqual(resp.status, 200)
    self.assertFalse((await resp.json())["applied"])

  async def test_time_sync_rejects_a_bad_body(self):
    resp = await self.client.post("/api/time_sync", json={"nope": 1})
    self.assertEqual(resp.status, 400)


class _NullParams:
  """create_app() only stores it; these routes read Params lazily, if at all."""


if __name__ == "__main__":
  unittest.main()
