"""Headless smoke for the storage panel's webui-snapshot data path.

Why this exists
---------------
The storage page is a 1:1 port of the webui storage panel and consumes the
webui's snapshot dict directly. A render smoke (settings_panels_render_smoke)
only proves the panel constructs; this one feeds a webui-shaped snapshot into
_apply_data and asserts the visible outcomes: summary text, legend values,
cleanup estimates and button gating, the starred list truncation, the external
SSD section visibility and the space warnings.

Run from the repo root:

    PYTHONPATH=.;opendbc_repo python openpilot/selfdrive/ui/tests/storage_panel_smoke.py

NOTE: deliberately NOT named test_*.py - it installs sys.modules stubs and
pytest must not collect it into a shared session.
"""
from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import settings_panels_render_smoke


def _snapshot(**overrides) -> dict:
  """A webui storage_api shaped snapshot (mirrors _mock_snapshot's contract)."""
  GB = 1024 ** 3
  MB = 1024 ** 2
  total = 128 * GB
  cats = {
    "routes": 40 * GB, "models": 9 * GB, "maps": 4 * GB, "software": 18 * GB,
    "logs": 2 * GB, "ota_staging": 9 * GB, "scons_cache": 900 * MB, "other": 100 * MB,
  }
  used = sum(cats.values())
  free = total - used
  snap = {
    "ok": True, "scanning": False, "offroad": True,
    "total_bytes": total, "used_bytes": used, "free_bytes": free,
    "free_percent": round(100.0 * free / total, 1),
    "low_space": False, "critical_space": False,
    "categories": [{"id": cid, "bytes": b, "percent": round(100.0 * b / total, 1)} for cid, b in cats.items()],
    "external": None,
    "routes_external_bytes": 0,
    "starred_routes": {"count": 0, "bytes": 0, "items": []},
    "clearable": {"routes": 44 * GB, "routes_starred": 8 * GB, "maps": 4 * GB, "models_cache": 3 * GB,
                  "logs": 2 * GB, "scons_cache": 900 * MB, "download_cache": 512 * MB},
  }
  snap.update(overrides)
  return snap


class StoragePanelSmoke(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    settings_panels_render_smoke.install()
    cls.storage = importlib.import_module("openpilot.selfdrive.ui.sunnypilot.layouts.settings.storage")

  def _panel(self):
    # keep the constructor's background scan synchronous and inert
    with mock.patch.object(self.storage.threading, "Thread", self._sync_thread):
      return self.storage.StorageLayout()

  @staticmethod
  def _sync_thread(target=None, args=(), daemon=None, timer=None):
    class _Sync:
      def __init__(self, target, args): self._t, self._a = target, args
      def start(self): self._t(*self._a)
      def join(self, timeout=None): pass
    return _Sync(target, args)

  def test_fmt_bytes_matches_webui(self):
    GB, MB = 1024 ** 3, 1024 ** 2
    f = self.storage._fmt_bytes
    self.assertEqual(f(1.5 * GB), "1.5 GB")
    self.assertEqual(f(3 * MB), "3.0 MB")
    self.assertEqual(f(2048), "2 KB")
    self.assertEqual(f(5), "5 B")
    self.assertEqual(f(None), "0 B")   # webui: Number(null) -> 0
    self.assertEqual(f("junk"), "-")   # webui: non-finite -> "—"

  def test_summary_and_legend_from_snapshot(self):
    p = self._panel()
    snap = _snapshot()
    p._apply_data(snap)
    self.assertIn("83.0 GB", p._disk_item.action_item.text)   # used
    self.assertIn("45.0 GB", p._disk_item.action_item.text)   # free
    routes = snap["categories"][0]
    self.assertEqual(p._legend_rows["routes"]._size_text, "40.0 GB")
    self.assertEqual(p._legend_rows["routes"]._pct_text, f"{routes['percent']}%")
    self.assertEqual(p._legend_free._size_text, "45.0 GB")
    # bar carries one segment per non-zero category + free
    colors, _ = zip(*p._bar._segments, strict=False)
    self.assertEqual(len(colors), 8)
    self.assertAlmostEqual(p._bar._free_fraction, snap["free_bytes"] / snap["total_bytes"], places=5)

  def test_cleanup_rows_get_estimates_and_gate(self):
    p = self._panel()
    p._apply_data(_snapshot())
    row = p._action_rows["routes"]
    self.assertIn("About 44.0 GB can be freed", row.action_item.value)
    self.assertTrue(row.action_item.enabled)
    # a zero estimate disables its clear button
    snap = _snapshot(clearable={"routes": 0, "routes_starred": 0, "maps": 0, "models_cache": 0,
                                "logs": 0, "scons_cache": 0, "download_cache": 0})
    p._apply_data(snap)
    self.assertFalse(p._action_rows["routes"].action_item.enabled)
    self.assertIn("Nothing to clear", p._action_rows["routes"].action_item.value)

  def test_routes_description_includes_auto_delete_and_external(self):
    p = self._panel()
    p._apply_data(_snapshot())
    desc = p._routes_desc()
    self.assertIn("auto-delete", desc)
    self.assertNotIn("external SSD", desc.lower())
    p._apply_data(_snapshot(routes_external_bytes=120 * 1024 ** 3))
    self.assertIn("Includes 120.0 GB on external SSD.", p._routes_desc())

  def test_starred_list_rows_and_truncation(self):
    p = self._panel()
    GB = 1024 ** 3
    items = [{"id": f"2026-01-{i:02d}", "volume": "internal", "segments": 3, "bytes": GB}
             for i in range(8)]
    p._apply_data(_snapshot(starred_routes={"count": 8, "bytes": 8 * GB, "items": items}))
    visible = [r for r in p._starred_rows if r.is_visible]
    self.assertEqual(len(visible), self.storage.STARRED_LIST_MAX)
    self.assertTrue(p._starred_more.is_visible)
    self.assertIn("2", p._starred_more._title)  # and 2 more…
    # few starred routes: list rows follow the count, no "more" row
    p._apply_data(_snapshot(starred_routes={"count": 1, "bytes": GB, "items": items[:1]}))
    self.assertEqual(len([r for r in p._starred_rows if r.is_visible]), 1)
    self.assertFalse(p._starred_more.is_visible)

  def test_external_section_visibility(self):
    p = self._panel()
    p._apply_data(_snapshot())
    self.assertFalse(p._ext_heading.is_visible)
    ext = {
      "mounted": True, "label": "External SSD", "mount": "/mnt/external_realdata",
      "total_bytes": 512 * 1024 ** 3, "used_bytes": 120 * 1024 ** 3, "free_bytes": 392 * 1024 ** 3,
      "free_percent": 76.6, "low_space": False, "critical_space": False,
      "routes_bytes": 120 * 1024 ** 3,
      "categories": [{"id": "routes", "bytes": 120 * 1024 ** 3, "percent": 23.4}],
    }
    p._apply_data(_snapshot(external=ext, routes_external_bytes=120 * 1024 ** 3))
    self.assertTrue(p._ext_heading.is_visible)
    self.assertTrue(p._ext_bar.is_visible)
    self.assertEqual(p._ext_legend_routes._size_text, "120.0 GB")
    self.assertAlmostEqual(p._ext_bar._free_fraction, 392.0 / 512.0, places=5)

  def test_low_and_critical_space_warnings(self):
    p = self._panel()
    p._apply_data(_snapshot())
    self.assertFalse(p._warn_item.is_visible)
    p._apply_data(_snapshot(low_space=True))
    self.assertTrue(p._warn_item.is_visible)
    self.assertIn("10%", p._warn_item.title)
    p._apply_data(_snapshot(low_space=False, critical_space=True))
    self.assertIn("2%", p._warn_item.title)

  def test_offroad_hint_hidden_offroad(self):
    p = self._panel()
    p._apply_data(_snapshot())
    self.assertFalse(p._offroad_hint.is_visible)

  # ------------------------------------------------------- model split rows
  def test_model_rows_show_sizes_and_gate(self):
    p = self._panel()
    GB, MB = 1024 ** 3, 1024 ** 2
    p._sizes = {"models": 5 * GB, "qcom": 2 * GB, "chestnut": 3 * GB}
    p._model_clearable = {"qcom": 500 * MB, "chestnut": 0}
    p._update_model_rows()
    self.assertIn("2.00 GB", p._model_rows["qcom"].action_item.value)
    self.assertIn("3.00 GB", p._model_rows["chestnut"].action_item.value)
    # clearable source clears; a source with nothing deletable does not
    self.assertTrue(p._model_rows["qcom"].action_item.enabled)
    self.assertFalse(p._model_rows["chestnut"].action_item.enabled)
    # the live description carries the estimate
    self.assertIn("About 500.00 MB can be freed", p._model_desc("qcom")())
    self.assertNotIn("can be freed", p._model_desc("chestnut")())

  def test_cached_bundle_sizes_reads_model_artifacts(self):
    """Regression: artifacts hang off bundle.models[], not bundle.artifacts -
    reading the wrong field made both size rows show 0 forever."""
    import os
    import tempfile
    from types import SimpleNamespace
    from openpilot.selfdrive.ui.sunnypilot.storage_info import cached_bundle_sizes

    with tempfile.TemporaryDirectory() as root:
      for name in ("small.bin", "big.bin"):
        with open(os.path.join(root, name), "wb") as f:
          f.write(b"x" * 1024)
      def make_bundle(name):
        return SimpleNamespace(models=[SimpleNamespace(
          artifact=SimpleNamespace(fileName=name, fileSizeBytes=1024), metadata=None)])

      sizes = cached_bundle_sizes(root, {"qcom": [make_bundle("small.bin")], "chestnut": [make_bundle("big.bin")]})
    self.assertEqual(sizes["qcom"], 1024)
    self.assertEqual(sizes["chestnut"], 1024)

  def test_model_clearable_skips_selected_and_shared(self):
    """Per-source clear keeps both slots' selected bundles and files the other
    catalog also lists; only exclusive, not-in-use files are deletable."""
    import os
    import tempfile
    from types import SimpleNamespace
    from unittest import mock

    from openpilot.selfdrive.ui.sunnypilot.layouts.settings import storage as st

    def make_bundle(*names):
      return SimpleNamespace(models=[SimpleNamespace(
        artifact=SimpleNamespace(fileName=n, fileSizeBytes=100), metadata=None) for n in names])

    selected = {"qcom": make_bundle("active_small.bin"), "chestnut": make_bundle("active_big.bin")}
    catalogs = {
      "qcom": [make_bundle("active_small.bin", "old_small.bin", "shared.bin")],
      "chestnut": [make_bundle("active_big.bin", "old_big.bin", "shared.bin")],
    }
    with tempfile.TemporaryDirectory() as root:
      for name in ("active_small.bin", "old_small.bin", "shared.bin", "active_big.bin", "old_big.bin"):
        with open(os.path.join(root, name), "wb") as f:
          f.write(b"x" * 100)
      with mock.patch("openpilot.sunnypilot.models.helpers.get_selected_bundle",
                      side_effect=lambda params, s: selected[s]), \
           mock.patch("openpilot.sunnypilot.models.model_sizes.artifact_size",
                      side_effect=lambda path, declared=None: {"downloadedBytes": 100}):
        clearable_qcom = st.StorageLayout._model_clearable_bytes(None, root, "qcom", catalogs)
        clearable_chestnut = st.StorageLayout._model_clearable_bytes(None, root, "chestnut", catalogs)
    # qcom side: old_small.bin only (active protected, shared serves chestnut too)
    self.assertEqual(clearable_qcom, 100)
    self.assertEqual(clearable_chestnut, 100)


if __name__ == "__main__":
  unittest.main()
