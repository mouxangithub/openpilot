"""Tests for the CarrotPilot-alignment gaps: the engaged refusal gate on
destructive endpoints, the engaged flag in param-change history, and the
wired-up time-sync endpoint.

The aiohttp-backed endpoint tests skip on a PC without aiohttp and run for
real on the device; the history-field test is pure logic and runs anywhere.
"""
from __future__ import annotations

import tempfile
import unittest
from unittest import mock


try:
  import aiohttp  # noqa: F401
  _AIOHTTP = True
except ImportError:  # pragma: no cover - PC without deps
  _AIOHTTP = False


class TestParamChangeEngagedFlag(unittest.TestCase):
  """append_param_change already had the `engaged` field; api_param_set must
  now populate it (CarrotPilot contract: record *that* it happened while driving)."""

  def test_engaged_true_is_recorded_and_hashed(self):
    from openpilot.sunnypilot.carrot.server.services import param_changes

    with tempfile.TemporaryDirectory() as tmp:
      path = f"{tmp}/changes.log"
      with mock.patch.object(param_changes, "CARROT_PARAM_CHANGES_PATH", path), \
           mock.patch.object(param_changes, "_known_values", {}):
        param_changes.append_param_change("VehicleNaviSectionAvgControl", 0, 1, source="web_ui", engaged=True)
        param_changes.append_param_change("VehicleNaviSectionAvgMargin", 0, 2, source="web_ui", engaged=False)

        records = param_changes.read_param_changes()
        self.assertEqual(len(records), 2)
        newest, oldest = records[0], records[1]
        self.assertFalse(newest["engaged"])
        self.assertTrue(oldest["engaged"])
        # The engaged flag participates in the hash input, so identical
        # key/values with different engagement must not hash equal.
        self.assertNotEqual(newest["hash"], oldest["hash"])


@unittest.skipUnless(_AIOHTTP, "aiohttp required (device)")
class TestSystemEngagedGate(unittest.TestCase):
  """The 409 gate itself predates this change in sp (named _refuse_if_engaged);
  these cases pin the contract so a refactor cannot silently drop it."""

  @staticmethod
  def _make_request(engaged_runtime: bool, is_engaged_param: bool = False):
    from aiohttp import web
    from aiohttp.test_utils import make_mocked_request

    from openpilot.sunnypilot.carrot.server.features import system as sysmod

    class _FakeRuntime:
      def is_engaged(self):
        return engaged_runtime

    app = web.Application()
    app[sysmod.RUNTIME_KEY] = _holder(_FakeRuntime() if engaged_runtime else None)
    request = make_mocked_request("POST", "/api/reboot", app=app)
    return sysmod, request

  def test_refuse_if_engaged_returns_409_when_runtime_engaged(self):
    sysmod, request = self._make_request(engaged_runtime=True)
    blocked = sysmod._refuse_if_engaged(request)
    self.assertIsNotNone(blocked)
    self.assertEqual(blocked.status, 409)

  def test_allows_reboot_when_not_engaged(self):
    sysmod, request = self._make_request(engaged_runtime=False)
    self.assertIsNone(sysmod._refuse_if_engaged(request))

  def test_is_drive_engaged_public_hook(self):
    sysmod, request = self._make_request(engaged_runtime=True)
    self.assertTrue(sysmod.is_drive_engaged(request))


@unittest.skipUnless(_AIOHTTP, "aiohttp required (device)")
class TestTimeSyncEndpoint(unittest.TestCase):
  def test_bad_json_is_400(self):
    import asyncio

    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    from openpilot.sunnypilot.carrot.server.features import system as sysmod

    async def scenario():
      app = web.Application()
      app.router.add_post("/api/time_sync", sysmod.api_time_sync)
      client = TestClient(TestServer(app))
      await client.start_server()
      try:
        resp = await client.post("/api/time_sync", data=b"not json")
        self.assertEqual(resp.status, 400)
        resp = await client.post("/api/time_sync", json={"timezone": "Asia/Shanghai"})
        self.assertEqual(resp.status, 400)
        body = await resp.json()
        self.assertIn("epoch_ms", body["error"])
      finally:
        await client.close()

    asyncio.run(scenario())

  def test_result_shape_and_status_follow_service(self):
    import asyncio

    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    from openpilot.sunnypilot.carrot.server.features import system as sysmod
    from openpilot.sunnypilot.carrot.server.services import time_sync

    fake_result = {"ok": True, "applied": True, "diff_sec": 120, "message": "time updated"}

    async def scenario():
      app = web.Application()
      app.router.add_post("/api/time_sync", sysmod.api_time_sync)
      client = TestClient(TestServer(app))
      await client.start_server()
      try:
        with mock.patch.object(time_sync, "sync_system_time_from_browser", return_value=dict(fake_result)) as m:
          resp = await client.post("/api/time_sync", json={
            "epoch_ms": 1799838400000, "timezone": "Asia/Shanghai", "debug": True})
          self.assertEqual(resp.status, 200)
          body = await resp.json()
          self.assertTrue(body["ok"])
          self.assertTrue(body["applied"])
          m.assert_called_once()
          args = m.call_args.args
          self.assertEqual(args[0], 1799838400000)
          self.assertEqual(args[1], "Asia/Shanghai")
          self.assertTrue(args[2])
      finally:
        await client.close()

    asyncio.run(scenario())


def _holder(runtime):
  class _H:
    def __init__(self, value):
      self._value = value

    def get(self):
      return self._value
  return _H(runtime)


if __name__ == "__main__":
  unittest.main()
