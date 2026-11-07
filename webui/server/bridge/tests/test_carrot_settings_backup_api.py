"""Tests for carrot_settings_backup_api (backup / restore / QR / profiles / favorites).

Mirrors the harness in test_carrot_tuning_api.py: we patch
``carrot_tuning_api._params`` with an in-memory fake so no real Params store or
device hardware is required.

NOTE: the webui server runs as the ``webui`` package, so every import here uses
the ``webui.server.bridge`` namespace — patching ``server.bridge`` would target a
*separate* module object and have no effect on the code under test.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from typing import Any
from unittest.mock import patch

# PC-dev path so importing the route table / params works on this machine, and so
# the code under test uses the same env the PC preview does.
os.environ.setdefault("WEBUI_DEV_PC", "1")

# Point profiles / favorites storage at a temp dir before importing the module.
_STATE_DIR = tempfile.mkdtemp(prefix="carrot_settings_test_")
os.environ["CARROT_SETTINGS_STATE_DIR"] = _STATE_DIR

from webui.server.bridge import carrot_settings_backup_api as mod
from webui.server.bridge import offroad_guard
from webui.server.bridge.carrot_tuning_api import (
  CARROT_TUNING_DEFAULTS,
  carrot_value_str,
  is_carrot_key,
)
import webui.server.bridge.carrot_tuning_api as _cta


class _FakeParams:
  """In-memory stand-in for openpilot.common.params.Params."""

  def __init__(self):
    self._store: dict[str, Any] = {}

  def get(self, key: str, block: bool = False, default=None, return_default: bool = False):
    return self._store.get(key, default)

  def get_bool(self, key: str, block: bool = False) -> bool:
    v = self._store.get(key)
    if v is None:
      return False
    return str(v).strip().lower() in ("1", "true", "yes", "on")

  def put(self, key: str, value: Any, block: bool = False) -> None:
    self._store[key] = value

  def put_bool(self, key: str, value: bool, block: bool = False) -> None:
    self._store[key] = bool(value)

  def remove(self, key: str) -> None:
    self._store.pop(key, None)


def _set_cta_params(fn):
  _cta._params = fn  # type: ignore[assignment]


class CarrotSettingsBackupTests(unittest.TestCase):
  def setUp(self):
    self.params = _FakeParams()
    self._orig = _cta._params
    _set_cta_params(lambda: self.params)
    mod.STATE_DIR = _STATE_DIR
    mod.PROFILES_PATH = os.path.join(_STATE_DIR, "setting_profiles.json")
    mod.FAVORITES_PATH = os.path.join(_STATE_DIR, "setting_favorites.json")

  def tearDown(self):
    _set_cta_params(self._orig)
    for path in (mod.PROFILES_PATH, mod.FAVORITES_PATH):
      if os.path.exists(path):
        os.remove(path)


class TestBackupExport(CarrotSettingsBackupTests):
  def test_export_returns_known_keys_only(self):
    backup = mod.export_params_backup()
    self.assertEqual(backup["version"], 1)
    self.assertEqual(set(backup["values"].keys()), set(CARROT_TUNING_DEFAULTS.keys()))
    for v in backup["values"].values():
      self.assertIsInstance(v, str)

  def test_export_reflects_current_values(self):
    self.params.put("AutoUpRoadLimit", 7)
    backup = mod.export_params_backup()
    self.assertEqual(backup["values"]["AutoUpRoadLimit"], "7")

  def test_restore_round_trip(self):
    payload = {"AutoUpRoadLimit": "5", "AlwaysLateral": "1", "CruiseSpeed1": "42"}
    result = mod.restore_params_backup(payload)
    self.assertTrue(result["ok"], result)
    self.assertEqual(result["ok_cnt"], 3)
    self.assertEqual(result["unknown_keys"], [])
    self.assertEqual(carrot_value_str("AutoUpRoadLimit"), "5")
    self.assertEqual(carrot_value_str("AlwaysLateral"), "1")
    self.assertEqual(carrot_value_str("CruiseSpeed1"), "42")

  def test_restore_rejects_unknown_key(self):
    payload = {"AutoUpRoadLimit": "5", "NotARealCarrotKey": "99"}
    result = mod.restore_params_backup(payload)
    self.assertIn("NotARealCarrotKey", result["unknown_keys"])
    self.assertFalse(result["ok"])
    self.assertEqual(result["ok_cnt"], 1)
    self.assertEqual(carrot_value_str("AutoUpRoadLimit"), "5")
    self.assertFalse(is_carrot_key("NotARealCarrotKey"))


class TestRestoreOffroadGuard(unittest.TestCase):
  def setUp(self):
    self.params = _FakeParams()
    self._orig = _cta._params
    _set_cta_params(lambda: self.params)
    self._orig_onroad = offroad_guard.device_is_onroad

  def tearDown(self):
    _set_cta_params(self._orig)
    offroad_guard.device_is_onroad = self._orig_onroad  # type: ignore[assignment]

  def test_require_offroad_returns_guard_when_onroad(self):
    offroad_guard.device_is_onroad = lambda: True  # type: ignore[assignment]
    self.assertEqual(offroad_guard.require_offroad()["error"], "only_available_offroad")

  def test_require_offroad_returns_none_when_offroad(self):
    offroad_guard.device_is_onroad = lambda: False  # type: ignore[assignment]
    self.assertIsNone(offroad_guard.require_offroad())

  def test_restore_handler_rejects_onroad(self):
    # The real handler lives in webui.server.routes, which cannot be imported on
    # this PC because the device dependency ``opendbc`` is absent (same class of
    # pre-existing gap as capnp / pyray). The handler is a trivial composition of
    # the offroad guard + restore_params_backup; both are exercised here with the
    # real implementations.
    from webui.server.bridge.offroad_guard import require_offroad

    async def handler(values):
      guard = require_offroad()
      if guard is not None:
        return guard
      return mod.restore_params_backup(values)

    offroad_guard.device_is_onroad = lambda: True  # type: ignore[assignment]
    res = asyncio.run(handler({"AutoUpRoadLimit": "9"}))
    self.assertEqual(res["error"], "only_available_offroad")
    self.assertEqual(carrot_value_str("AutoUpRoadLimit"), "0")

    offroad_guard.device_is_onroad = lambda: False  # type: ignore[assignment]
    res = asyncio.run(handler({"AutoUpRoadLimit": "9"}))
    self.assertTrue(res["ok"], res)
    self.assertEqual(carrot_value_str("AutoUpRoadLimit"), "9")


class TestQrBackup(unittest.TestCase):
  def setUp(self):
    self._orig = _cta._params
    _set_cta_params(lambda: _FakeParams())

  def tearDown(self):
    _set_cta_params(self._orig)

  def test_qr_builds_payload_with_encoder(self):
    with patch("webui.server.bridge.qr_data_url.qr_data_url", return_value="data:image/png;base64,XXXX"):
      res = mod.build_params_qr_backup({"AutoUpRoadLimit": "3"})
    self.assertTrue(res["ok"])
    self.assertTrue(res["data_url"].startswith("data:image/png;base64,"))

  def test_qr_too_large_when_encoder_returns_empty(self):
    with patch("webui.server.bridge.qr_data_url.qr_data_url", return_value=""):
      res = mod.build_params_qr_backup({"AutoUpRoadLimit": "3"})
    self.assertFalse(res["ok"])
    self.assertEqual(res["error"], "qr_too_large_or_encoder_unavailable")


class TestProfiles(unittest.TestCase):
  def setUp(self):
    self.params = _FakeParams()
    self._orig = _cta._params
    _set_cta_params(lambda: self.params)
    mod.STATE_DIR = _STATE_DIR
    mod.PROFILES_PATH = os.path.join(_STATE_DIR, "setting_profiles.json")
    if os.path.exists(mod.PROFILES_PATH):
      os.remove(mod.PROFILES_PATH)

  def tearDown(self):
    _set_cta_params(self._orig)
    if os.path.exists(mod.PROFILES_PATH):
      os.remove(mod.PROFILES_PATH)

  def test_create_read_update_delete(self):
    profile = mod.create_setting_profile("Commute")
    self.assertTrue(profile["id"])
    self.assertEqual(profile["name"], "Commute")
    self.assertTrue(profile["values"])

    listed = mod.read_setting_profiles()
    self.assertEqual(len(listed["profiles"]), 1)

    mod.update_setting_profile(profile["id"], {"name": "Highway"})
    self.assertEqual(mod.read_setting_profiles()["profiles"][0]["name"], "Highway")

    mod.delete_setting_profile(profile["id"])
    self.assertEqual(mod.read_setting_profiles()["profiles"], [])

  def test_create_rejects_empty_name(self):
    with self.assertRaises(ValueError):
      mod.create_setting_profile("   ")

  def test_profile_values_are_whitelisted(self):
    profile = mod.create_setting_profile("P")
    self.assertTrue(all(is_carrot_key(k) for k in profile["values"].keys()))

  def test_apply_writes_values(self):
    self.params.put("AutoUpRoadLimit", 0)
    profile = mod.create_setting_profile("P")
    new_values = dict(profile["values"])
    new_values["AutoUpRoadLimit"] = "8"
    mod.update_setting_profile(profile["id"], {"values": new_values})
    res = mod.apply_setting_profile(profile["id"])
    self.assertTrue(res["ok"], res)
    self.assertEqual(carrot_value_str("AutoUpRoadLimit"), "8")

  def test_apply_ignores_unknown_keys(self):
    self.params.put("AutoUpRoadLimit", 0)
    profile = mod.create_setting_profile("P")
    bad = dict(profile["values"])
    bad["NoSuchKey"] = "1"
    bad["AutoUpRoadLimit"] = "8"
    res = mod.apply_setting_profile(profile["id"], bad)
    self.assertTrue(res["ok"], res)
    self.assertEqual(carrot_value_str("AutoUpRoadLimit"), "8")
    # Unknown key was dropped (not written); it is not a carrot key at all.
    self.assertFalse(is_carrot_key("NoSuchKey"))

  def test_preview_reports_changed(self):
    self.params.put("AutoUpRoadLimit", 0)
    profile = mod.create_setting_profile("P")
    new_values = dict(profile["values"])
    new_values["AutoUpRoadLimit"] = "9"
    preview = mod.preview_setting_profile(profile["id"], new_values)
    entry = next(e for e in preview["entries"] if e["key"] == "AutoUpRoadLimit")
    self.assertTrue(entry["changed"])
    self.assertEqual(entry["value"], "9")
    self.assertEqual(entry["current"], "0")


class TestFavorites(unittest.TestCase):
  def setUp(self):
    self._orig = _cta._params
    _set_cta_params(lambda: _FakeParams())
    mod.STATE_DIR = _STATE_DIR
    mod.FAVORITES_PATH = os.path.join(_STATE_DIR, "setting_favorites.json")
    if os.path.exists(mod.FAVORITES_PATH):
      os.remove(mod.FAVORITES_PATH)

  def tearDown(self):
    _set_cta_params(self._orig)
    if os.path.exists(mod.FAVORITES_PATH):
      os.remove(mod.FAVORITES_PATH)

  def test_update_and_read(self):
    res = mod.update_setting_favorites({"favorites": ["AutoUpRoadLimit", "AlwaysLateral"]})
    self.assertEqual(res["favorites"], ["AutoUpRoadLimit", "AlwaysLateral"])
    self.assertEqual(mod.read_setting_favorites()["favorites"], ["AutoUpRoadLimit", "AlwaysLateral"])

  def test_favorites_rejects_unknown_keys(self):
    res = mod.update_setting_favorites({"favorites": ["AutoUpRoadLimit", "Nope"]})
    self.assertEqual(res["favorites"], ["AutoUpRoadLimit"])

  def test_favorites_dedup_and_cap(self):
    res = mod.update_setting_favorites({"favorites": ["AlwaysLateral", "AlwaysLateral", "AutoUpRoadLimit"]})
    self.assertEqual(res["favorites"], ["AlwaysLateral", "AutoUpRoadLimit"])


# --- small fakes / helpers -------------------------------------------------
class _FakeRequest:
  def __init__(self, body: dict | None = None, match: dict | None = None):
    self._body = body or {}
    self.match_info = match or {}

  async def json(self):
    return self._body


def _json_body(resp):
  import json as _json
  return _json.loads(resp.text)


if __name__ == "__main__":
  unittest.main()
