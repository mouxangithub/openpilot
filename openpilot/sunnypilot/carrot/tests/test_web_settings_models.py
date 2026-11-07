"""
Copyright (c) 2026-, mouxan.

Tests for the carrot web panel's hidden-key filter and the dedicated models
page. Pure logic: params and the cereal-backed model helpers are stubbed, so
these run on both a PC and the device's unittest runner.
"""
import sys
import types
import unittest
from unittest import mock

try:
  import openpilot.common.swaglog  # noqa: F401
except Exception:
  stub = types.ModuleType("openpilot.common.swaglog")
  stub.cloudlog = types.SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None,
                                        exception=lambda *a, **k: None)
  sys.modules["openpilot.common.swaglog"] = stub

from openpilot.sunnypilot.carrot import web_settings as ws


class _FakeParams:
  def __init__(self, d=None):
    self.d = d or {}

  def get(self, key, default=None, return_default=False):
    return self.d.get(key)

  def get_bool(self, key):
    return bool(self.d.get(key))

  def put(self, key, value, block=False):
    self.d[key] = value

  def put_bool(self, key, value):
    self.d[key] = value

  def remove(self, key):
    self.d.pop(key, None)


class TestHiddenKeys(unittest.TestCase):
  def test_off_ui_overrides_are_hidden_everywhere(self):
    grouped = {"other": ["ModelManager_MirrorUrl", "ModelManager_GithubProxy", "SomeKey"]}
    filtered = ws.filter_hidden(grouped)
    self.assertEqual(filtered.get("other"), ["SomeKey"])

  def test_jetlink_state_is_hidden(self):
    grouped = {"other": ["JetlinkLink", "JetlinkSpec", "AcceleratorProgress"]}
    self.assertNotIn("other", ws.filter_hidden(grouped))

  def test_manager_state_machine_is_hidden(self):
    grouped = {"models": ["Blendful", "ModelManager_DownloadRef", "ModelManager_ActiveBundle"]}
    self.assertEqual(ws.filter_hidden(grouped).get("models"), ["Blendful"])

  def test_apply_updates_refuses_hidden(self):
    params = _FakeParams()
    kinds = {"ModelManager_MirrorUrl": ws.T_STRING, "Blendful": ws.T_BOOL}
    written, skipped = ws.apply_updates(params, {"ModelManager_MirrorUrl": "x", "Blendful": "1"}, kinds)
    self.assertEqual((written, skipped), (1, 1))
    self.assertNotIn("ModelManager_MirrorUrl", params.d)

  def test_empty_groups_are_dropped(self):
    grouped = {"gone": ["JetlinkLink"], "kept": ["Blendful"]}
    filtered = ws.filter_hidden(grouped)
    self.assertEqual(list(filtered), ["kept"])


_STATE = {
  "qcom_active_name": "Model A",
  "qcom_bundles": [{"ref": "ref-a", "name": "Model A", "folder": "2025-10"},
                    {"ref": "ref-b", "name": "Model B", "folder": "2025-09"}],
  "chestnut_active_name": "Default", "chestnut_bundles": [],
  "download_ref": "ref-b", "download_name": "Model B", "download_fraction": 0.42,
  "jetlink_mode": "usb", "jetlink_status": "USB 端口上有设备。", "offroad": True,
  "cache_size": "512.00 MB",
  "blendful": True, "lane_turn_desire": False, "lagd": True,
  "lane_turn_value": 1900, "lagd_delay": 20, "camera_offset": 5,
}


class TestModelsPageRender(unittest.TestCase):
  def setUp(self):
    self.html = ws.render_models_page(_STATE)

  def test_slots_and_selection(self):
    self.assertIn("小模型", self.html)
    self.assertIn("大模型", self.html)
    self.assertIn(">Default</option>", self.html)
    self.assertIn('optgroup label="2025-10"', self.html)
    self.assertIn('selected>Model A', self.html)

  def test_jetlink_four_buttons_with_status(self):
    self.assertIn("外接算力连接", self.html)
    for title in ("关", "USB", "iOS", "Wi-Fi"):
      self.assertIn(f"{title}</label>", self.html)
    self.assertIn('value="1" checked', self.html)  # usb selected
    self.assertIn("USB 端口上有设备。", self.html)

  def test_download_progress_and_cancel(self):
    self.assertIn("Model B", self.html)
    self.assertIn("42%", self.html)
    self.assertIn("取消下载", self.html)

  def test_clear_cache_uses_the_on_device_confirm_wording(self):
    self.assertIn("这将从缓存中删除除当前活跃模型外的所有已下载模型，确定吗？", self.html)
    self.assertIn("512.00 MB", self.html)

  def test_blendful_in_chinese(self):
    self.assertIn("融合车道（测试版）", self.html)

  def test_slider_units_match_the_on_device_labels(self):
    self.assertIn("31 km/h", self.html)   # LaneTurnValue, MPH_TO_KPH like the panel
    self.assertIn("0.20 s", self.html)    # LagdToggleDelay
    self.assertIn("0.05 m", self.html)    # CameraOffset


class TestModelsFormActions(unittest.TestCase):
  def setUp(self):
    self.params = _FakeParams({"IsOffroad": 1})
    # the form's select branch checks the cached catalog; feed it a fixed one
    self._patcher = mock.patch.dict(sys.modules)

  def test_refresh_zeroes_the_sync_keys(self):
    ok, _ = ws.apply_models_form(self.params, {"action": ["refresh"]})
    self.assertTrue(ok)
    self.assertEqual(self.params.d.get("ModelManager_LastSyncTime"), 0)
    self.assertEqual(self.params.d.get("ModelManager_LastSyncTime_Chestnut"), 0)

  def test_jetlink_offroad_gate(self):
    ok, _ = ws.apply_models_form(self.params, {"action": ["jetlink"], "jetlink": ["2"]})
    self.assertTrue(ok)
    self.assertEqual(self.params.d.get("JetlinkLink"), 2)
    self.params.d["IsOffroad"] = 0
    ok, _ = ws.apply_models_form(self.params, {"action": ["jetlink"], "jetlink": ["3"]})
    self.assertFalse(ok)
    self.assertEqual(self.params.d.get("JetlinkLink"), 2, "onroad switch must not stick")

  def test_clear_cache_sets_the_same_flag_as_the_on_device_page(self):
    ok, _ = ws.apply_models_form(self.params, {"action": ["clear_cache"]})
    self.assertTrue(ok)
    self.assertTrue(self.params.d.get("ModelManager_ClearCache"))

  def test_values_round_trip(self):
    ok, _ = ws.apply_models_form(self.params, {"action": ["values"], "Blendful": ["1"], "LaneTurnValue": ["1900"]})
    self.assertTrue(ok)
    self.assertEqual(self.params.d.get("Blendful"), True)
    self.assertEqual(self.params.d.get("LaneTurnValue"), 1900)

  def test_unknown_action_rejected(self):
    ok, _ = ws.apply_models_form(self.params, {"action": ["nope"]})
    self.assertFalse(ok)


if __name__ == "__main__":
  unittest.main()
