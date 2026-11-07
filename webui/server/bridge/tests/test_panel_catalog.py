"""Contract tests for panel_catalog parameter exposure."""

from __future__ import annotations

import ast
import os
import re
import unittest
from unittest import mock

from webui.server.bridge import carrot_tuning_api
from webui.server.bridge.panel_catalog import (CARROT_TUNING_HIDDEN_WITH_READERS, CARROT_TUNING_UNAVAILABLE,
                                               SUBPANELS, _stamp_tuning_metadata, declared_tuning_metadata,
                                               get_panel, panel_param_keys)

# Carrot tuning keys that are intentionally NOT rendered as user-tunable widgets: a
# cross-process diagnostic sink written by the carrot daemon, plus every param that no code
# in this tree consumes (see CARROT_TUNING_UNAVAILABLE for the reasons), plus the handful
# that do have a reader but no widget that could honestly drive them.
_PANEL_EXCLUDED = {"CarrotException"} | set(CARROT_TUNING_UNAVAILABLE) | set(CARROT_TUNING_HIDDEN_WITH_READERS)
# Carrot keys exposed outside the navigation__carrot_tuning tree. Each needs a home panel.
_PANEL_EXCLUDED |= {"CustomSR"}  # exposed as "Custom Steer Ratio" in the steering panel
_PANEL_EXCLUDED |= {"ShowRadarInfo"}  # exposed in the visuals panel, mirroring big UI visuals.py


def _repo_config_py() -> str:
  """carrot/config.py in this checkout, found relative to this test file.

  It used to be a hardcoded `E:\\sp\\...` path, which made the whole suite unrunnable
  anywhere but one developer's PC - including on the device, where it would have been
  the first thing to fail if these tests ever ran there.
  """
  here = os.path.dirname(os.path.abspath(__file__))
  root = os.path.abspath(os.path.join(here, "..", "..", "..", ".."))
  return os.path.join(root, "openpilot", "sunnypilot", "carrot", "config.py")


def _config_nav_param_keys() -> set[str]:
  """Parse _DEFAULT_NAV_PARAMS keys from config.py without importing openpilot."""
  with open(_repo_config_py(), encoding="utf-8") as f:
    src = f.read()
  for node in ast.walk(ast.parse(src)):
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
       and node.target.id == "_DEFAULT_NAV_PARAMS":
      return {k.value for k in node.value.keys}
    if isinstance(node, ast.Assign):
      for t in node.targets:
        if isinstance(t, ast.Name) and t.id == "_DEFAULT_NAV_PARAMS":
          return {k.value for k in node.value.keys}
  return set()


class PanelCatalogParamTests(unittest.TestCase):
  """Verify the P1 carrot params that are actually wired are exposed in the webui.

  VehicleSpeedCameraDistanceTime was in this list but no code reads it, so it is now
  hidden like the rest of the inert params - exposing it would advertise a control
  that cannot do anything. It stays registered, so re-adding it here is all that is
  needed once a reader exists.
  """

  _P1_PARAMS = {
    "VehicleNaviCanControl",
    "VehicleNaviSchoolZoneControl",
    "VehicleSpeedCameraControlMode",
    "AutoNaviSpeedBumpEndDistance",
    "LatSuspendAngleDeg",
  }

  # Cluster params are intentionally exposed: ClusterNaviMap* is read by
  # carrot_navi's ClusterNaviMapParamReader, and ClusterHud*/CarrotNaviHudMapProfile
  # are the first step of porting CarrotPilot's external-cluster subsystem - the
  # settings surface is complete and the values persist across sessions.
  _CLUSTER_EXPOSED = {
    "ClusterNaviMapTheme", "ClusterNaviMapType", "ClusterNaviMapFps",
    "ClusterHud", "ClusterHudTheme",
    "ClusterHudBrightness", "ClusterHudCameraViewMode", "ClusterHudCoreMode",
    "ClusterHudDebug", "ClusterHudEncoder", "ClusterHudLiveFps",
    "ClusterHudMirror", "ClusterHudOrientation", "ClusterHudPanelLayout",
    "ClusterHudPriority", "ClusterHudRadarDisplay", "ClusterHudRadarInfo",
    "ClusterHudRadarSourceColor", "ClusterHudScreenMode",
  }

  def test_carrot_tuning_exposes_p1_params(self):
    keys = set(panel_param_keys("navigation__carrot_tuning"))
    missing = self._P1_PARAMS - keys
    self.assertFalse(missing, f"navigation__carrot_tuning missing params: {sorted(missing)}")

  def test_carrot_tuning_exposes_cluster_params(self):
    """Cluster knobs are now first-class settings (part 1 of the cluster port)."""
    keys = set(panel_param_keys("navigation__carrot_tuning__display"))
    missing = self._CLUSTER_EXPOSED - keys
    self.assertFalse(missing, f"display panel missing cluster params: {sorted(missing)}")


class CarrotTuningFullCoverageTests(unittest.TestCase):
  """Every carrot tuning key must be backed by the API and the panel."""

  def test_all_config_keys_in_api_defaults(self):
    api_keys = set(carrot_tuning_api.CARROT_TUNING_DEFAULTS)
    cfg_keys = _config_nav_param_keys()
    missing = cfg_keys - api_keys
    self.assertFalse(missing, f"CARROT_TUNING_DEFAULTS missing keys: {sorted(missing)}")

  def test_all_config_keys_exposed_in_panel(self):
    panel_keys = set(panel_param_keys("navigation__carrot_tuning"))
    cfg_keys = _config_nav_param_keys()
    missing = cfg_keys - panel_keys - _PANEL_EXCLUDED
    self.assertFalse(missing, f"panel missing carrot params: {sorted(missing)}")

  def test_panel_params_backed_by_api(self):
    api_keys = set(carrot_tuning_api.CARROT_TUNING_DEFAULTS)
    panel_keys = set(panel_param_keys("navigation__carrot_tuning"))
    # Not carrot tuning keys in the nav_params.json sense: CarrotEnabled is the
    # master toggle the panel gates on, and the weather keys are registered
    # Params read by the planner rather than entries in the tuning surface, so
    # carrot_tuning_api has nothing to say about any of them.
    not_tuning_keys = {
      "CarrotEnabled",
      "WeatherOffsetsEnabled", "WeatherAutoDetect", "WeatherState",
      "WeatherIncreaseFollowing", "WeatherIncreaseStoppedDistance",
      "WeatherReduceAcceleration", "WeatherReduceLateralAcceleration",
    }
    orphan = panel_keys - api_keys - not_tuning_keys
    self.assertFalse(orphan, f"panel params not in API: {sorted(orphan)}")


class CarrotTuningLayoutTests(unittest.TestCase):
  """The carrot tuning page is a root list of groups, not a tab strip.

  It used to be the only panel in the catalogue using the `tabs` widget. It now
  mirrors the native settings page: a root list of subpanel rows, one per group,
  separated by `separator` (the webui equivalent of LineSeparatorSP).
  """

  ROOT = "carrot"

  def test_root_uses_subpanel_rows_not_tabs(self):
    widgets = get_panel(self.ROOT)["widgets"]
    types = [w.get("type") for w in widgets]
    self.assertNotIn("tabs", types, "the tab strip is gone; use subpanel rows")
    self.assertNotIn("tab", types, "tab panes are gone; use subpanel rows")

  def test_every_subpanel_row_targets_a_real_panel(self):
    widgets = get_panel(self.ROOT)["widgets"]
    rows = [w for w in widgets if w.get("type") == "subpanel"]
    # 9 groups. "Path Rendering" lost every item when the params with no reader were
    # hidden, so the group and its row were removed rather than left empty; eGPU was
    # then added as its own row.
    self.assertEqual(len(rows), 9, f"expected 9 group rows, got {len(rows)}")
    for w in rows:
      target = w["target"]
      self.assertIn(target, SUBPANELS, f"{target} is not a registered subpanel")
      self.assertTrue(get_panel(target), f"{target} resolves to nothing")
      self.assertEqual(get_panel(target).get("parent"), self.ROOT,
                       f"{target} must declare parent={self.ROOT} so the back button renders")

  def test_group_rows_are_separated_and_described(self):
    widgets = get_panel(self.ROOT)["widgets"]
    row_indices = [i for i, w in enumerate(widgets) if w.get("type") == "subpanel"]
    self.assertEqual(len(row_indices), 9, "expected 9 group rows")
    self.assertNotEqual(widgets[0].get("type"), "separator", "the list must not open with a separator")
    for i in range(len(row_indices) - 1):
      between = widgets[row_indices[i] + 1:row_indices[i + 1]]
      self.assertEqual(sum(1 for w in between if w.get("type") == "separator"), 1,
                       "exactly one separator between each pair of group rows")
    for idx in row_indices:
      w = widgets[idx]
      self.assertTrue(w.get("desc"), f"{w['target']} has no description")
      self.assertTrue(w.get("label"), f"{w['target']} has no label")

  def test_no_group_panel_is_empty(self):
    """A panel that renders itself (``custom``) owns no declarative widgets by design."""
    widgets = get_panel(self.ROOT)["widgets"]
    for w in (x for x in widgets if x.get("type") == "subpanel"):
      panel = get_panel(w["target"])
      if panel.get("custom"):
        continue
      self.assertTrue(panel["widgets"], f"{w['target']} has no widgets")


class CarrotHiddenParamsAreReallyDeadTests(unittest.TestCase):
  """A param hidden from the UI must not be read anywhere in the tree.

  The first version of the dead-param scan only walked `openpilot/**`, so readers
  living inside the submodules were invisible and four working params got hidden -
  three read by opendbc's BYD port (opendbc_repo/opendbc/car/byd/carcontroller.py and
  radar_interface.py) and one by carrot_serv. This test scans the submodule trees too.
  """

  # Every source tree that ships and can read a param. `openpilot` is included so the
  # test also catches a hidden param that gained a reader since it was hidden.
  ROOTS = ("openpilot", "opendbc_repo", "panda", "msgq_repo", "system")
  EXTS = (".py", ".cc", ".h", ".cpp", ".hpp", ".pyx")
  # files that legitimately name every param without reading it
  SURFACES = ("carrot_tuning_items.py", "panel_catalog.py", "carrot/config.py",
              "carrot_tuning_api.py", "nav_params.json", "params_keys.h",
              "carrot_tuning.py")

  def _repo_root(self):
    from pathlib import Path
    # .../webui/server/bridge/tests/ -> repo root
    return Path(__file__).resolve().parents[4]

  def test_no_hidden_carrot_param_has_a_reader(self):
    root = self._repo_root()
    names = set(CARROT_TUNING_UNAVAILABLE)
    self.assertTrue(names, "CARROT_TUNING_UNAVAILABLE is empty; the scan lost its input")
    self.assertFalse(names & set(CARROT_TUNING_HIDDEN_WITH_READERS),
                     "a key cannot be both 'no reader' and 'reader, but hidden on purpose'")

    offenders: dict[str, list[str]] = {}
    for tree in self.ROOTS:
      for ext in self.EXTS:
        for path in root.joinpath(tree).rglob(f"*{ext}"):
          q = str(path).replace("\\", "/")
          if "__pycache__" in q or "/tests/" in q or path.name.startswith("test_"):
            continue
          if any(s in q for s in self.SURFACES):
            continue
          try:
            text = path.read_text(encoding="utf-8")
          except (UnicodeDecodeError, OSError):
            continue
          for name in names:
            pattern = r"get\w*\s*\(\s*[\"']" + re.escape(name) + r"[\"']"
            if re.search(pattern, text):
              rel = q.split("/openpilot/", 1)[-1]
              offenders.setdefault(name, []).append(rel)

    if offenders:
      self.fail(f"hidden but still read by shipped code: {offenders}")

  def test_every_hidden_param_with_a_reader_states_why(self):
    """The reasoned list is the only way to hide a working control, so it must justify itself."""
    for name, reason in CARROT_TUNING_HIDDEN_WITH_READERS.items():
      self.assertTrue(reason.strip(), f"{name} is hidden without a reason")
      self.assertNotIn(name, CARROT_TUNING_UNAVAILABLE,
                       f"{name} is listed as dead and as reasoned; pick one")


class TuningMetadataTests(unittest.TestCase):
  """The catalogue reads its depth numbers from the compiled key table, not from here.

  `openpilot/common/params_keys.h` declares how deep each knob sits (`tuningLevel`) and
  which settings tier owns it (`settingsTier`). Stamping those onto every widget is what
  lets the frontend group and order controls without a second list to keep in step, and
  what makes a newly declared control arrive with the right depth for free.
  """

  def test_a_declared_number_lands_on_the_widget(self):
    widgets = [{"type": "bool", "param": "CarrotEnabled", "label": "Carrot"}]
    out = _stamp_tuning_metadata(widgets, {"CarrotEnabled": {"tuningLevel": 1, "settingsTier": 0}})
    self.assertEqual(out[0]["tuningLevel"], 1)
    self.assertEqual(out[0]["settingsTier"], 0)
    self.assertEqual(out[0]["label"], "Carrot")

  def test_a_widget_with_no_declaration_gains_nothing(self):
    """Absent is not zero: a store with no metadata must not look like "not a knob"."""
    widgets = [{"type": "bool", "param": "SteerRatio"}]
    out = _stamp_tuning_metadata(widgets, {})
    self.assertNotIn("tuningLevel", out[0])
    self.assertNotIn("settingsTier", out[0])

  def test_the_input_widgets_are_left_alone(self):
    """PANELS is module state; a request must not rewrite it for the next one."""
    original = {"type": "bool", "param": "CarrotEnabled"}
    _stamp_tuning_metadata([original], {"CarrotEnabled": {"tuningLevel": 3, "settingsTier": 1}})
    self.assertEqual(original, {"type": "bool", "param": "CarrotEnabled"})

  def test_tab_children_are_stamped_too(self):
    widgets = [{"type": "tab", "widgets": [{"type": "bool", "param": "CarrotEnabled"}]}]
    out = _stamp_tuning_metadata(widgets, {"CarrotEnabled": {"tuningLevel": 2, "settingsTier": 1}})
    self.assertEqual(out[0]["widgets"][0]["tuningLevel"], 2)

  def test_subpanel_widgets_are_stamped(self):
    """The carrot tuning page is nothing but subpanels, and subpanels are fetched by id."""
    import webui.server.bridge.panel_catalog as panel_catalog

    metadata = {"UseLaneLineCurveSpeed": {"tuningLevel": 2, "settingsTier": 1}}
    with mock.patch.object(panel_catalog, "declared_tuning_metadata", lambda names: metadata):
      widgets = panel_catalog.stamped_widgets(get_panel("navigation__carrot_tuning__speed")["widgets"])
    hit = next(w for w in widgets if w.get("param") == "UseLaneLineCurveSpeed")
    self.assertEqual(hit["tuningLevel"], 2)
    self.assertEqual(hit["settingsTier"], 1)

  def test_the_four_unhidden_controls_are_reachable(self):
    """These were hidden as dead while shipped code reads them; they must stay reachable."""
    keys = set(panel_param_keys("navigation__carrot_tuning"))
    for name in ("UseLaneLineCurveSpeed", "SteerRatioRate", "HotspotOnBoot"):
      self.assertIn(name, keys, f"{name} lost its control")
    # ShowRadarInfo moved to the visuals panel, mirroring big UI visuals.py.
    self.assertIn("ShowRadarInfo", set(panel_param_keys("visuals")), "ShowRadarInfo lost its control")

  def test_no_names_means_no_store_read(self):
    """An empty request must not build a Params handle just to answer nothing."""
    self.assertEqual(declared_tuning_metadata([]), {})
    self.assertEqual(declared_tuning_metadata(["", None]), {})

  def test_a_store_that_cannot_be_built_answers_nothing(self):
    """A PC host has no libparams_c.so, and the payload simply carries no depths."""
    import builtins

    real_import = builtins.__import__

    def _refuse(name, *args, **kwargs):
      if name == "openpilot.common.params":
        raise ModuleNotFoundError(name)
      return real_import(name, *args, **kwargs)

    builtins.__import__ = _refuse
    try:
      self.assertEqual(declared_tuning_metadata(["CarrotEnabled"]), {})
    finally:
      builtins.__import__ = real_import


if __name__ == "__main__":
  unittest.main()
