"""Intro preset table must only name params this fork can actually write.

The defect this pins
--------------------
`server/features/intro/presets.py` writes its preset values through
`services.params.set_param_value()`. That path is:

    set_param_value(name, value, p)
      -> put_typed(params, name, value, p)
           -> params.get_type(name)          # raises UnknownKeyName
           -> _put_inferred(...)             # raises UnknownKeyName again
      -> except Exception as exc:
           if p is None or ...: raise        # p IS None here -> re-raised

`p` is the setting definition looked up from the settings catalog. For a key that is in
neither `params_keys.h` nor `carrot_settings_sp.json`, `_clamped()` returns `p = None`,
so the re-raise wins and `_apply_preset_sync` records the param in `failed`. The route
then answers `500 {"ok": false, "error": "some params failed"}`.

Because the loop writes params one at a time, the *other* params of the preset were
already committed by then: the caller sees an error and the car is half-configured,
which is exactly what the module docstring forbids ("a partial state is not acceptable").

Why the existing tests missed it
--------------------------------
`test_carrot_server_completeness.py` covers "unknown preset -> 400" and
`/api/intro/state`, but never applies a *known* preset. And the failure only happens
with real `Params` (device): on a bare PC checkout `HAS_PARAMS` is False and
`set_param_value` short-circuits to an in-memory dict, so it cannot fail. Hence a static
test on the key table, which runs everywhere, is the right shape.

`presets.py` is loaded by file path on purpose: `features/intro/__init__.py` imports
`.routes`, which pulls in aiohttp and the cereal/opendbc chain, so a normal package
import cannot run on a bare PC checkout. The module under test is stdlib-only.
"""
from __future__ import annotations

import importlib.util
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
PRESETS_PY = (REPO / "openpilot" / "sunnypilot" / "carrot" / "server" /
              "features" / "intro" / "presets.py")
PARAMS_KEYS_H = REPO / "openpilot" / "common" / "params_keys.h"


def _load_presets():
  spec = importlib.util.spec_from_file_location("carrot_intro_presets", PRESETS_PY)
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


# Keys this fork deliberately records without acting on them yet. Every one needs a
# reason, so adding an entry is a conscious act rather than a silent drift.
#
# Their consumers live in CarrotPilot's opendbc / monitoring layer, which this fork does
# not carry: sp derives HyundaiFlags.CAMERA_SCC from the fingerprint instead of from a
# param, and has no `selfdrive/monitoring/config.py` (it gates DM with AlwaysOnDM).
# Registering them is still correct - it is what makes the preset writable at all - but a
# value written here does not change driving behaviour until that layer is ported.
NO_CONSUMER_YET = {
  "HyundaiCameraSCC": "cp reads it in opendbc/car/hyundai; sp derives CAMERA_SCC from the fingerprint",
  "DriverMonitoringMode": "cp reads it in selfdrive/monitoring/config.py, which sp does not carry",
  "DriverMonitoringEnabled": "cp's DM master switch; sp gates DM with AlwaysOnDM instead",
  "CanfdHDA2": "cp's HDA step; the HDA write path exists but the consumer is not ported",
}


def _registered_keys() -> set[str]:
  return set(re.findall(r'\{"([A-Za-z_][A-Za-z0-9_]*)",\s*\{',
                        PARAMS_KEYS_H.read_text(encoding="utf-8")))


class TestPresetKeysAreRegistered(unittest.TestCase):
  """Every key a preset writes must exist in params_keys.h.

  This is the invariant that was violated and made /api/intro/apply_preset answer 500 on
  every device.
  """

  @classmethod
  def setUpClass(cls):
    cls.presets = _load_presets()
    cls.registered = _registered_keys()

  def test_every_preset_param_is_declared(self):
    missing = sorted({name for values in self.presets.PRESETS.values() for name in values}
                     - self.registered)
    self.assertEqual(missing, [],
                     f"undeclared preset keys - applying the preset would answer 500: {missing}")

  def test_the_hda_param_is_declared(self):
    self.assertIn(self.presets.HDA_PARAM, self.registered,
                  f"HDA_PARAM={self.presets.HDA_PARAM!r} must be declared: /api/param_set writes it")

  def test_no_consumer_keys_are_explicit(self):
    """A key with no consumer in this fork must be listed, not discovered later.

    Registering a param that nothing reads is acceptable here (it keeps the write
    readable and lets a future port reuse the value), but it must be a recorded decision.
    If a key gains a consumer, drop it from this set in the same change.
    """
    undocumented = sorted(k for k in NO_CONSUMER_YET if k not in self.registered)
    self.assertEqual(undocumented, [], f"NO_CONSUMER_YET lists undeclared keys: {undocumented}")

  def test_preset_shape_is_intact(self):
    """Three presets, int values, and the axis that separates them is preserved."""
    self.assertEqual(set(self.presets.PRESETS), {"radar_long", "camera_long", "stock"})
    for name, values in self.presets.PRESETS.items():
      for key, value in values.items():
        self.assertIsInstance(value, int, f"{name}.{key} must be an int")
    # EnableCornerRadar is the ONLY axis separating radar_long from camera_long; the
    # module docstring says not to "tidy" it away.
    self.assertNotEqual(self.presets.PRESETS["radar_long"]["EnableCornerRadar"],
                        self.presets.PRESETS["camera_long"]["EnableCornerRadar"])


if __name__ == "__main__":
  unittest.main()
