"""Tests for the cabana vehicle-profile endpoints (ai/services/cabana/profile.py)."""

from __future__ import annotations

import ai.tests.bootstrap_pc  # noqa: F401  # PC mocks before ai imports
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from ai.services.cabana import profile as profile_mod
from ai.services.cabana.profile import (
  api_profile_commit,
  api_profile_naming,
  api_profile_scan,
)
from ai.tests.cabana_fixtures import (
  make_brake_frames,
  make_speed_frames,
  make_truth_series,
)

ADDR_SPEED = 0x1A8
ADDR_BRAKE = 0x1C0


def _scan_frames() -> list[dict]:
  frames = make_speed_frames(ADDR_SPEED, n=800) + make_brake_frames(ADDR_BRAKE, n=800)
  frames.sort(key=lambda f: f["time"])
  return frames


async def _mock_llm(messages, **_kwargs) -> dict:
  return {
    "ok": True,
    "response": json.dumps([
      {"name": "WHEEL_SPEED", "start_bit": 0, "size": 16, "endian": "little",
       "factor": 0.01, "offset": 0.0, "unit": "m/s", "confidence": 0.95,
       "evidence": "tracks GPS speed"},
    ]),
  }


async def _no_llm(*_args, **_kwargs) -> dict:
  return {"ok": False, "error": "LLM disabled in tests"}


class ProfileEndpointsTest(AioHTTPTestCase):
  """HTTP endpoints with mocked frames/truth/car-params and mocked LLM."""

  def setUp(self):
    self._tmp = tempfile.TemporaryDirectory()
    self._env = patch.dict(os.environ, {"AI_USER_DBC_DIR": self._tmp.name})
    self._env.start()
    self.addCleanup(self._env.stop)
    self.addCleanup(self._tmp.cleanup)
    profile_mod._profile_state.clear()
    profile_mod._profile_state_order.clear()
    super().setUp()

  async def get_application(self) -> web.Application:
    app = web.Application()
    app.router.add_post("/api/cabana/profile/scan", api_profile_scan)
    app.router.add_post("/api/cabana/profile/naming", api_profile_naming)
    app.router.add_post("/api/cabana/profile/commit", api_profile_commit)
    return app

  def _patches(self, llm=_no_llm):
    return [
      patch.object(profile_mod, "_query_frames", return_value=(_scan_frames(), None)),
      patch.object(profile_mod, "_load_truth_cached", return_value=make_truth_series()),
      patch.object(profile_mod, "_resolve_car_params", return_value={
        "carFingerprint": "TOYOTA_RAV4", "brand": "toyota",
      }),
      patch.object(profile_mod, "_suggest_dbc_for_fingerprint", return_value="toyota_rav4"),
      patch("ai.services.cabana.ai_explain._cabana_ai_complete", new=llm),
    ]

  @unittest_run_loop
  async def test_scan_report_schema(self):
    with self._stack(self._patches()):
      resp = await self.client.post("/api/cabana/profile/scan", json={"route": "r--1--0"})
    self.assertEqual(resp.status, 200)
    body = await resp.json()
    self.assertTrue(body["ok"])
    self.assertEqual(body["schema"], "cabana.profile.v1")
    self.assertEqual(body["route"], "r--1--0")
    self.assertFalse(body["llm_used"])
    self.assertEqual(body["fingerprint"]["carFingerprint"], "TOYOTA_RAV4")
    self.assertEqual(body["fingerprint"]["suggested_dbc"], "toyota_rav4")
    self.assertTrue(body["fingerprint"]["matched"])
    # truth report
    self.assertTrue(body["truth"]["available"])
    self.assertTrue(body["truth"]["variance_ok"])
    self.assertIn("gps_speed", body["truth"]["series"])
    self.assertIn("hz", body["truth"]["series"]["gps_speed"])
    self.assertIn("count", body["truth"]["series"]["gps_speed"])
    # addresses
    blocks = {a["address"]: a for a in body["addresses"]}
    self.assertIn(ADDR_SPEED, blocks)
    self.assertGreater(blocks[ADDR_SPEED]["hz"], 5.0)
    self.assertEqual(blocks[ADDR_SPEED]["bus"], 0)
    self.assertIn("payload_len", blocks[ADDR_SPEED])
    self.assertTrue(blocks[ADDR_SPEED]["dbc_text_draft"].startswith("BO_ "))
    speed = next(c for c in blocks[ADDR_SPEED]["candidates"] if c["start_bit"] == 0 and c["size"] == 16)
    self.assertIsInstance(speed["evidence"], list)
    self.assertIsInstance(speed["confidence"], int)
    self.assertIn("speed", speed["functions"])
    self.assertEqual(speed["anchor"]["truth"], "gps_speed")
    # summary groups
    self.assertTrue(body["summary"]["speed"])
    self.assertEqual(body["summary"]["speed"][0]["address"], ADDR_SPEED)
    for entry in body["summary"]["speed"]:
      # Identity tuple (start_bit/size/endian) lets the frontend re-match
      # summary entries to candidates even after LLM renaming.
      self.assertEqual(set(entry.keys()), {"address", "name", "confidence", "start_bit", "size", "endian"})
      self.assertEqual((entry["start_bit"], entry["size"]), (0, 16))

  @unittest_run_loop
  async def test_scan_route_not_found(self):
    with patch.object(profile_mod, "_query_frames", return_value=(None, "Route not found")):
      resp = await self.client.post("/api/cabana/profile/scan", json={"route": "nope"})
    self.assertEqual(resp.status, 404)

  @unittest_run_loop
  async def test_scan_requires_route(self):
    resp = await self.client.post("/api/cabana/profile/scan", json={})
    self.assertEqual(resp.status, 400)

  @unittest_run_loop
  async def test_naming_updates_candidates(self):
    with self._stack(self._patches(llm=_mock_llm)):
      resp = await self.client.post("/api/cabana/profile/scan", json={"route": "r--1--0"})
      self.assertEqual(resp.status, 200)
      resp = await self.client.post("/api/cabana/profile/naming", json={
        "route": "r--1--0",
        "address": ADDR_SPEED,
        "candidates": [{"start_bit": 0, "size": 16, "endian": "little"}],
        "hints": "RAV4 车速信号",
      })
    self.assertEqual(resp.status, 200)
    body = await resp.json()
    self.assertTrue(body["ok"])
    self.assertTrue(body["llm_used"])
    self.assertIsNone(body["llm_error"])
    speed = next(c for c in body["candidates"] if c["start_bit"] == 0 and c["size"] == 16)
    self.assertEqual(speed["name"], "WHEEL_SPEED")
    # confidence recomputed to the 0-100 int scale after the merge
    self.assertIsInstance(speed["confidence"], int)
    self.assertTrue(any("LLM:" in e for e in speed["evidence"]))

  @unittest_run_loop
  async def test_naming_requires_scan_first(self):
    with self._stack(self._patches()):
      resp = await self.client.post("/api/cabana/profile/naming", json={
        "route": "never-scanned", "address": ADDR_SPEED,
        "candidates": [{"start_bit": 0, "size": 16, "endian": "little"}],
      })
    self.assertEqual(resp.status, 409)
    self.assertEqual((await resp.json())["error"], "profile scan first")

  @unittest_run_loop
  async def test_naming_rejects_more_than_eight(self):
    candidates = [{"start_bit": i, "size": 1, "endian": "little"} for i in range(9)]
    with self._stack(self._patches()):
      resp = await self.client.post("/api/cabana/profile/naming", json={
        "route": "r", "address": ADDR_SPEED, "candidates": candidates,
      })
    self.assertEqual(resp.status, 400)

  @unittest_run_loop
  async def test_naming_unknown_address(self):
    with self._stack(self._patches()):
      await self.client.post("/api/cabana/profile/scan", json={"route": "r--1--0"})
      resp = await self.client.post("/api/cabana/profile/naming", json={
        "route": "r--1--0", "address": 0x999,
        "candidates": [{"start_bit": 0, "size": 16, "endian": "little"}],
      })
    self.assertEqual(resp.status, 404)

  @unittest_run_loop
  async def test_commit_builds_valid_multi_message_dbc(self):
    with self._stack(self._patches()):
      resp = await self.client.post("/api/cabana/profile/scan", json={"route": "r--1--0"})
      self.assertEqual(resp.status, 200)
      resp = await self.client.post("/api/cabana/profile/commit", json={
        "route": "r--1--0",
        "name": "TOYOTA_RAV4_ai_profile",
        "addresses": [
          {"address": ADDR_SPEED, "candidates": [
            {"start_bit": 0, "size": 16, "endian": "little"},
            {"start_bit": 32, "size": 8, "endian": "little"},
          ]},
          {"address": ADDR_BRAKE},
        ],
      })
    self.assertEqual(resp.status, 200)
    body = await resp.json()
    self.assertTrue(body["ok"])
    self.assertEqual(body["name"], "TOYOTA_RAV4_ai_profile")
    self.assertTrue(body["version"])
    self.assertTrue(body["validation"]["parse_ok"])
    self.assertGreaterEqual(body["validation"]["signal_count"], 3)

  @unittest_run_loop
  async def test_commit_requires_scan(self):
    with self._stack(self._patches()):
      resp = await self.client.post("/api/cabana/profile/commit", json={
        "route": "never-scanned", "name": "some_car",
        "addresses": [{"address": ADDR_SPEED}],
      })
    self.assertEqual(resp.status, 409)

  @unittest_run_loop
  async def test_commit_rejects_invalid_name(self):
    with self._stack(self._patches()):
      await self.client.post("/api/cabana/profile/scan", json={"route": "r--1--0"})
      resp = await self.client.post("/api/cabana/profile/commit", json={
        "route": "r--1--0", "name": "1bad-name!",
        "addresses": [{"address": ADDR_SPEED}],
      })
    self.assertEqual(resp.status, 400)

  def _stack(self, patches):
    import contextlib
    stack = contextlib.ExitStack()
    for p in patches:
      stack.enter_context(p)
    self.addCleanup(stack.close)
    return stack


if __name__ == "__main__":
  unittest.main()
