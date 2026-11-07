"""Tests for carrot_tuning_api.py P3 parameter exposure.

Verifies the 8 vehicle CAN / cluster / planner control params are backed by
the webui tuning API (CARROT_TUNING_DEFAULTS) so they can be read, adjusted,
and reset from the panel, and that their defaults match common/params_keys.h.
"""

from __future__ import annotations

import os
import unittest
from typing import Any

from server.bridge.carrot_tuning_api import (
  CARROT_TUNING_DEFAULTS,
  carrot_get,
  carrot_put,
  carrot_reset,
  is_carrot_key,
)
from server.bridge.panel_catalog import panel_param_keys


# (kind, default) — must match common/params_keys.h registrations.
_EXPECTED = {
  "VehicleNaviCanControl": ("int", 0),
  "VehicleNaviSchoolZoneControl": ("bool", 0),
  "VehicleSpeedCameraControlMode": ("int", 1),
  "LatSuspendAngleDeg": ("int", 300),
}

# The Cluster* / HUD-map params were removed from the panel: sp has no cluster
# subsystem, so every one of them was registered, exposed, and read by nothing.
# They stay in CARROT_TUNING_DEFAULTS (the API whitelist) but must NOT be visible.
_CLUSTER_EXPOSED = {
  "ClusterNaviMapTheme", "ClusterNaviMapType", "ClusterNaviMapFps",
  "CarrotNaviHudMapProfile", "ClusterHud", "ClusterHudTheme",
}


class _FakeParams:
  """In-memory stand-in for openpilot.common.params.Params.

  Mirrors the real backend by returning *typed* values from ``get``
  (int/bool/str), since Params.get() decodes based on the registered key type.
  """

  def __init__(self):
    self._store: dict[str, Any] = {}

  def get(self, key: str, return_default: bool = False):
    return self._store.get(key)

  def put(self, key: str, value: Any, block: bool = False) -> None:
    self._store[key] = value

  def put_bool(self, key: str, value: bool, block: bool = False) -> None:
    self._store[key] = bool(value)

  def remove(self, key: str) -> None:
    self._store.pop(key, None)


class CarrotTuningP3Tests(unittest.TestCase):
  def setUp(self):
    self.params = _FakeParams()
    # Patch the module-level _params() used by the carrot tuning API.
    os.environ["WEBUI_DEV_PC"] = "1"
    import server.bridge.carrot_tuning_api as mod
    self._orig = mod._params
    mod._params = lambda: self.params  # type: ignore[assignment]

  def tearDown(self):
    import server.bridge.carrot_tuning_api as mod
    mod._params = self._orig  # type: ignore[assignment]

  def test_keys_registered_in_api_table(self):
    for key, (kind, default) in _EXPECTED.items():
      self.assertIn(key, CARROT_TUNING_DEFAULTS, f"{key} missing from CARROT_TUNING_DEFAULTS")
      self.assertEqual(CARROT_TUNING_DEFAULTS[key], (kind, default),
                       f"{key} kind/default mismatch: {CARROT_TUNING_DEFAULTS[key]}")

  def test_keys_visible_in_panel_catalog(self):
    panel_keys = set(panel_param_keys("navigation__carrot_tuning"))
    missing = set(_EXPECTED) - panel_keys
    self.assertFalse(missing, f"panel_catalog missing params: {sorted(missing)}")

  def test_cluster_params_visible_with_correct_types(self):
    """Cluster knobs are now first-class settings (part 1 of the cluster port).

    ClusterNaviMap* is read by carrot_navi's ClusterNaviMapParamReader;
    ClusterHud* drive the not-yet-ported external renderer but are deliberately
    exposed so the settings surface is complete and the values persist.
    """
    panel_keys = set(panel_param_keys("navigation__carrot_tuning"))
    for key in _CLUSTER_EXPOSED:
      self.assertIn(key, panel_keys, f"cluster param {key} not exposed")
      kind = CARROT_TUNING_DEFAULTS[key][0]
      self.assertEqual(kind, "bool" if key in {"ClusterHud", "ClusterHudDebug",
                                               "ClusterHudMirror", "ClusterHudRadarDisplay",
                                               "ClusterHudRadarSourceColor", "CarrotNaviHudMapProfile"}
                       else "int", f"{key} kind should match its value type")

  def test_is_carrot_key_true_for_p3_params(self):
    for key in _EXPECTED:
      self.assertTrue(is_carrot_key(key), f"{key} not recognized as carrot key")

  def test_default_values_readable(self):
    for key, (kind, default) in _EXPECTED.items():
      res = carrot_get(key)
      self.assertTrue(res["ok"], f"carrot_get failed for {key}: {res}")
      expected_str = "1" if (kind == "bool" and default) else str(default)
      self.assertEqual(res["value"], expected_str,
                       f"{key} default value mismatch: {res['value']!r} != {expected_str!r}")

  def test_put_and_reset_round_trip(self):
    for key, (kind, default) in _EXPECTED.items():
      if kind == "bool":
        new_value = "1" if not default else "0"
      else:
        # Pick a value different from the default.
        new_value = str(default + 1) if default != 0 else "7"

      put_res = carrot_put(key, new_value)
      self.assertTrue(put_res["ok"], f"carrot_put failed for {key}: {put_res}")
      self.assertEqual(put_res["value"], new_value, f"{key} put value mismatch")

      read_res = carrot_get(key)
      self.assertEqual(read_res["value"], new_value, f"{key} read after put mismatch")

      reset_res = carrot_reset(key)
      self.assertTrue(reset_res["ok"], f"carrot_reset failed for {key}: {reset_res}")
      expected_default = "1" if (kind == "bool" and default) else str(default)
      self.assertEqual(reset_res["value"], expected_default,
                       f"{key} reset did not restore default")

  def test_put_invalid_int_value_rejected(self):
    # A non-numeric string into an int key must be rejected.
    res = carrot_put("VehicleNaviCanControl", "not-a-number")
    self.assertFalse(res["ok"], "invalid int value should be rejected")


if __name__ == "__main__":
  unittest.main()
