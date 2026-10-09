"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Tests for the second half of the port-7000 surface: history, backup, preferences, refusals.

The first test is the receipt for "the surface is complete". It carries CarrotPilot's route
table and asserts this server answers every one of them - the point being that a client
must never see 404 where CarrotPilot answered something, because a 404 cannot be told apart
from "this fork is behind".

The rest exercises the parts that are easy to get quietly wrong: the hash chain, the QR
payload actually decoding back to what was encoded, and a refusal being 501 rather than 404.
"""
import base64
import unittest
from unittest import mock

from openpilot.sunnypilot.carrot.server.services import param_changes as pc
from openpilot.sunnypilot.carrot.server.services import params_backup as pb

try:
  from aiohttp.test_utils import TestClient, TestServer

  _HAVE_AIOHTTP = True
except Exception:
  _HAVE_AIOHTTP = False

try:
  import openpilot.common.params  # noqa: F401

  _HAVE_PARAMS = True
except Exception:
  _HAVE_PARAMS = False


# CarrotPilot's route table, reduced to the two-segment prefix each route lives under.
CARROTPILOT_ROUTE_PREFIXES = (
  "/",
  "/api/bluetooth",
  "/api/calibration_status",
  "/api/carrot_navi",
  "/api/cars",
  "/api/dashcam",
  "/api/device_network",
  "/api/egpu",
  "/api/heartbeat_status",
  "/api/intro",
  "/api/live_runtime",
  "/api/mapbox",
  "/api/param_changes",
  "/api/param_fingerprint",
  "/api/param_set",
  "/api/params_backup",
  "/api/params_bulk",
  "/api/params_qr_backup",
  "/api/params_qr_dependency",
  "/api/params_restore",
  "/api/poweroff",
  "/api/reboot",
  "/api/recalibrate",
  "/api/regulatory",
  "/api/screenrecord",
  "/api/set_default",
  "/api/setting_favorites",
  "/api/setting_popular_values",
  "/api/setting_profiles",
  "/api/setting_unit_index",
  "/api/settings",
  "/api/ssh_keys",
  "/api/support_terminal",
  "/api/terminal_commands",
  "/api/terminal_pty",
  "/api/time_sync",
  "/api/tools",
  "/api/vision_diag",
  "/api/vision_test",
  "/api/web_settings",
  "/api/youtube_live",
  "/download/params_backup.json",
  "/download/tmux.log",
  "/stream",
  "/support-terminal-assets",
  "/support/terminal",
  "/ws/camera",
  "/ws/carrot_navi",
  "/ws/compact_state",
  "/ws/raw",
  "/ws/raw_multiplex",
  "/ws/support_terminal",
  "/ws/terminal",
  "/ws/terminal_pty",
  "/ws/web_sound",
  "/xiaoge",
)


class _KeyType:
  def __init__(self, name):
    self.name = name


class _FakeParams:
  """Mirrors the slice of `Params` the backup service uses."""

  def __init__(self, types=None, store=None, defaults=None):
    self.types = dict(types or {})
    self.store = dict(store or {})
    self.defaults = dict(defaults or dict.fromkeys(self.types, ""))

  def check_key(self, key):
    if key not in self.types:
      raise KeyError(key)

  def get_type(self, key):
    return _KeyType(self.types[key])

  def all_keys(self):
    return list(self.types)

  def get_default_value(self, key):
    return self.defaults.get(key)

  def get(self, key, block=False, return_default=False):
    return self.store.get(key, self.defaults.get(key))

  def put(self, key, dat):
    self.store[key] = dat


# ---------------------------------------------------------------------------
# parameter change history
# ---------------------------------------------------------------------------


class TestParamChangeChain(unittest.TestCase):
  def setUp(self):
    self._saved = (pc.CARROT_PARAM_CHANGES_PATH, pc.CARROT_FINGERPRINT_BASELINE_PATH)
    import tempfile
    import os

    self._dir = tempfile.mkdtemp()
    pc.CARROT_PARAM_CHANGES_PATH = os.path.join(self._dir, "param_changes.jsonl")
    pc.CARROT_FINGERPRINT_BASELINE_PATH = os.path.join(self._dir, "fingerprint_baseline.json")

  def tearDown(self):
    pc.CARROT_PARAM_CHANGES_PATH, pc.CARROT_FINGERPRINT_BASELINE_PATH = self._saved
    pc._known_values.clear()

  def test_records_are_chained_and_verify(self):
    pc.append_param_change("IsMetric", 0, 1, source="web_ui")
    pc.append_param_change("IsMetric", 1, 0, source="profile")
    changes = pc.read_param_changes()
    self.assertEqual(len(changes), 2)
    # Newest first.
    self.assertEqual(changes[0]["next"], 0)
    self.assertTrue(pc.verify_param_changes()["valid"])

  def test_a_tampered_record_is_detected(self):
    pc.append_param_change("IsMetric", 0, 1)
    records = pc.read_param_changes()
    records[0]["next"] = 99
    # Rewrite the line without re-hashing, which is exactly what tampering looks like.
    with open(pc.CARROT_PARAM_CHANGES_PATH, "w", encoding="utf-8") as f:
      f.write(pc._canonical(records[0]) + "\n")
    result = pc.verify_param_changes()
    self.assertFalse(result["valid"])
    self.assertIn("hash", result["reason"])

  def test_reads_can_be_narrowed(self):
    pc.append_param_change("IsMetric", 0, 1)
    pc.append_param_change("ExperimentalMode", 0, 1)
    self.assertEqual(len(pc.read_param_changes(name="IsMetric")), 1)
    self.assertEqual(len(pc.read_param_changes(source="device")), 0)

  def test_an_unknown_source_is_recorded_as_unknown(self):
    pc.append_param_change("IsMetric", 0, 1, source="made_up")
    self.assertEqual(pc.read_param_changes()[0]["source"], "unknown")

  def test_drift_is_recorded_as_device_and_only_for_allowed_keys(self):
    pc.observe_param_values({"IsMetric": 1}, allowed={"IsMetric"})
    # First observation is adopted as the baseline, not reported as a change.
    self.assertEqual(len(pc.read_param_changes()), 0)
    pc.observe_param_values({"IsMetric": 0, "NotAllowed": 7}, allowed={"IsMetric"})
    changes = pc.read_param_changes()
    self.assertEqual(len(changes), 1)
    self.assertEqual(changes[0]["source"], "device")

  def test_fingerprint_baseline_round_trip(self):
    self.assertIsNone(pc.read_fingerprint_baseline())
    written = pc.write_fingerprint_baseline("abc12345")
    self.assertEqual(pc.read_fingerprint_baseline()["fingerprint"], written["fingerprint"])

  def test_fingerprint_is_stable_and_order_independent(self):
    self.assertEqual(pc.param_fingerprint({"a": 1, "b": 2}), pc.param_fingerprint({"b": 2, "a": 1}))
    self.assertNotEqual(pc.param_fingerprint({"a": 1}), pc.param_fingerprint({"a": 2}))
    self.assertEqual(pc.param_fingerprint({"a": 1})["count"], 1)


# ---------------------------------------------------------------------------
# QR backup / restore
# ---------------------------------------------------------------------------


class TestParamsQrBackup(unittest.TestCase):
  def setUp(self):
    self.params = _FakeParams(
      {"IsMetric": "BOOL", "ExperimentalMode": "BOOL", "SpeedFromPCM": "INT", "CarParams": "BYTES"},
      {"IsMetric": True, "ExperimentalMode": False, "SpeedFromPCM": 2},
    )

  def test_backup_skips_bytes_and_json(self):
    values = pb.get_all_param_values_for_backup(self.params)
    self.assertIn("IsMetric", values)
    self.assertNotIn("CarParams", values)

  def test_qr_payload_round_trips(self):
    payload = pb.build_params_qr_payload(self.params)["payload"]
    # brotli is optional; without it the encoder must fall back to CQR4, which decodes too.
    self.assertTrue(payload.startswith(("CQR3:", "CQR4:")), payload[:8])
    restored = pb.parse_params_qr_payload(self.params, payload)
    self.assertEqual(restored["IsMetric"], "1")
    self.assertEqual(restored["ExperimentalMode"], "0")
    self.assertEqual(restored["SpeedFromPCM"], "2")

  def test_a_corrupted_checksum_is_rejected(self):
    payload = pb.build_params_qr_payload(self.params)["payload"]
    # rsplit, not split: base45 uses ":" as one of its 45 characters.
    encoded, checksum = payload[5:].rsplit(":", 1)
    broken = f"{payload[:5]}{encoded}:{'0' * len(checksum)}"
    with self.assertRaises(ValueError):
      pb.parse_params_qr_payload(self.params, broken)

  def test_v2_payload_from_carrotpilot_is_read(self):
    import hashlib
    import json
    import zlib

    envelope = [2, [[base64.urlsafe_b64encode(b"x").decode().rstrip("="), "1"]], {}]
    raw = json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    compressed = zlib.compress(raw, 9)
    checksum = hashlib.sha256(compressed).hexdigest()[:12]
    payload = f"CQR2.{base64.urlsafe_b64encode(compressed).decode().rstrip('=')}.{checksum}"
    # Decoding must not raise; unknown short codes simply resolve to nothing.
    self.assertIsInstance(pb.parse_params_qr_payload(self.params, payload), dict)

  def test_a_plain_object_payload_is_accepted(self):
    self.assertEqual(pb.parse_params_qr_payload(self.params, {"values": {"IsMetric": "1"}}), {"IsMetric": "1"})

  def test_preview_marks_same_and_unknown_keys(self):
    preview = pb.preview_param_restore_values(self.params, {"IsMetric": "1", "Nope": "1", "CarParams": "x"})
    by_key = {entry["key"]: entry for entry in preview["entries"]}
    self.assertEqual(by_key["IsMetric"]["status"], "same")
    self.assertEqual(by_key["Nope"]["status"], "invalid")
    self.assertEqual(by_key["CarParams"]["status"], "skipped")

  def test_restore_only_writes_selected_keys(self):
    result = pb.restore_param_values_validated(self.params, {"SpeedFromPCM": "0", "IsMetric": "0"}, ["SpeedFromPCM"])
    self.assertEqual(result["result"]["ok_cnt"], 1)


# ---------------------------------------------------------------------------
# surface completeness
# ---------------------------------------------------------------------------


@unittest.skipUnless(_HAVE_AIOHTTP, "needs aiohttp")
class TestRouteCompleteness(unittest.IsolatedAsyncioTestCase):
  async def asyncSetUp(self):
    from openpilot.sunnypilot.carrot.server.app import create_app

    self.app = create_app(params=_FakeParams({"IsMetric": "BOOL"}, {"IsMetric": True}))
    self.paths = sorted({str(resource.canonical) for resource in self.app.router.resources()})
    self.client = TestClient(TestServer(self.app))
    await self.client.start_server()

  async def asyncTearDown(self):
    await self.client.close()

  def _matches(self, prefix: str) -> bool:
    return any(path == prefix or path.startswith((prefix + "/", prefix + "/{")) for path in self.paths)

  def test_every_carrotpilot_route_prefix_is_answered(self):
    missing = [prefix for prefix in CARROTPILOT_ROUTE_PREFIXES if not self._matches(prefix)]
    self.assertEqual(missing, [], f"routes a CarrotPilot client may call that answer 404: {missing}")

  async def test_refused_routes_answer_501_with_a_reason(self):
    for path in ("/api/dashcam/routes", "/api/screenrecord/videos", "/ws/compact_state", "/api/tools"):
      with self.subTest(path=path):
        resp = await self.client.get(path) if not path.startswith("/api/tools") else await self.client.post(path, json={})
        self.assertEqual(resp.status, 501, path)
        self.assertIn("note", await resp.json())

  async def test_the_index_lists_the_routes(self):
    resp = await self.client.get("/")
    self.assertEqual(resp.status, 200)
    self.assertIn("/api/param_set", (await resp.json())["routes"])

  async def test_web_settings_round_trip(self):
    resp = await self.client.post("/api/web_settings", json={"language": "zh"})
    self.assertEqual(resp.status, 200)
    self.assertEqual((await resp.json())["settings"]["language"], "zh")

  async def test_an_unsupported_web_setting_value_is_ignored_not_stored(self):
    resp = await self.client.post("/api/web_settings", json={"language": "klingon"})
    self.assertEqual((await resp.json())["settings"]["language"], "")

  async def test_favorites_round_trip(self):
    resp = await self.client.post("/api/setting_favorites", json={"favorites": ["IsMetric", "IsMetric", 7]})
    body = await resp.json()
    self.assertEqual(body["favorites"], ["IsMetric"])

  async def test_intro_hides_by_default_and_lists_presets(self):
    # no state file is "done", and a comma that ran the wizard has one with
    # done=False: pin the read so the test means the same on a PC and a device
    with mock.patch("openpilot.sunnypilot.carrot.server.features.intro._read_state", return_value={}):
      resp = await self.client.get("/api/intro/state")
      body = await resp.json()
    self.assertFalse(body["should_show"])
    self.assertIn("radar_long", body["presets"])

  async def test_intro_shows_again_after_a_reset(self):
    # the wizard returns for a device whose state says it was reset
    with mock.patch("openpilot.sunnypilot.carrot.server.features.intro._read_state",
                    return_value={"done": False}):
      resp = await self.client.get("/api/intro/state")
      body = await resp.json()
    self.assertTrue(body["should_show"])

  async def test_an_unknown_preset_is_a_400(self):
    resp = await self.client.post("/api/intro/apply_preset", json={"name": "nope"})
    self.assertEqual(resp.status, 400)
    self.assertIn("presets", await resp.json())


if __name__ == "__main__":
  unittest.main()
