"""G8 — profile patch-layer composition (ordered bundles → user → launcher).

Proves behavior, not existence:
- entry-patch semantics: include appends/merges options (later wins per key),
  exclude removes; both accept plain ids and {id, options} objects;
- invalid patch shapes and empty ids fail loud with typed codes;
- compose_profile applies layers in dsh order (bundles in profile order →
  profile user layer → launcher layers) with per-layer attribution;
- unknown / duplicate bundle ids fail loud; missing manifest fails loud;
- profile discovery lists only directories with a valid manifest.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ai.bundle.manifest import BundleManifest
from ai.bundle.profile import (
  PROFILE_PATCH_FILENAME,
  ProfileError,
  apply_patch,
  compose_profile,
  list_profiles,
  load_profile_manifest,
  load_profile_patch,
  profile_dir,
  profiles_root,
)
from ai.bundle.store import BundleStore


class EntryPatchTests(unittest.TestCase):
  def test_include_appends_and_merges_options(self) -> None:
    entries = [{"id": "tool:a", "options": {"timeout": 5, "retries": 1}}]
    out = apply_patch(entries, {"include": [
      {"id": "tool:b", "options": {"flag": True}},
      {"id": "tool:a", "options": {"timeout": 30}},
    ]})
    self.assertEqual([e["id"] for e in out], ["tool:a", "tool:b"])
    self.assertEqual(out[0]["options"], {"timeout": 30, "retries": 1}, "later options win per key, others preserved")
    self.assertEqual(out[1]["options"], {"flag": True})

  def test_exclude_removes_matching_ids(self) -> None:
    entries = [{"id": "tool:a", "options": {}}, {"id": "tool:b", "options": {}}]
    out = apply_patch(entries, {"include": [], "exclude": ["tool:a"]})
    self.assertEqual([e["id"] for e in out], ["tool:b"])

  def test_plain_string_include_and_exclude(self) -> None:
    # A layer's exclude prunes entries inherited from earlier layers; its own
    # include lands after the exclude pass and survives.
    out = apply_patch([{"id": "tool:old", "options": {}}], {"include": ["tool:x"], "exclude": ["tool:old"]})
    self.assertEqual([e["id"] for e in out], ["tool:x"])
    self.assertEqual(apply_patch([], {"include": [], "exclude": ["tool:x"]}), [])

  def test_invalid_shapes_fail_loud(self) -> None:
    with self.assertRaises(ProfileError) as cm:
      apply_patch([], {"include": [{"no_id": True}]})
    self.assertEqual(cm.exception.code, "invalid_patch")
    with self.assertRaises(ProfileError):
      apply_patch([], {"include": [""]})
    with self.assertRaises(ProfileError):
      apply_patch([], "not-an-object")
    with self.assertRaises(ProfileError):
      apply_patch([], {"include": "tool:a"})


class ProfileDiscoveryTests(unittest.TestCase):
  def setUp(self) -> None:
    self.tmp = tempfile.TemporaryDirectory()
    self.base = Path(self.tmp.name)

  def tearDown(self) -> None:
    self.tmp.cleanup()

  def _write_profile(self, name: str, manifest: dict, patch: dict | None = None) -> Path:
    d = profile_dir(name, self.base)
    d.mkdir(parents=True, exist_ok=True)
    (d / "profile.json").write_text(json.dumps(manifest), encoding="utf-8")
    if patch is not None:
      (d / PROFILE_PATCH_FILENAME).write_text(json.dumps(patch), encoding="utf-8")
    return d

  def test_missing_manifest_fails_loud(self) -> None:
    d = profile_dir("ghost", self.base)
    d.mkdir(parents=True)
    with self.assertRaises(ProfileError) as cm:
      load_profile_manifest(d)
    self.assertEqual(cm.exception.code, "profile_not_found")

  def test_manifest_validation(self) -> None:
    d = self._write_profile("bad", {"bundles": []})
    with self.assertRaises(ProfileError) as cm:
      load_profile_manifest(d)
    self.assertEqual(cm.exception.code, "invalid_profile")
    self._write_profile("bad2", {"name": "bad2", "bundles": "not-a-list"})
    with self.assertRaises(ProfileError):
      load_profile_manifest(profile_dir("bad2", self.base))
    self._write_profile("bad3", {"name": "bad3", "bundles": [], "patchReload": "whenever"})
    with self.assertRaises(ProfileError):
      load_profile_manifest(profile_dir("bad3", self.base))

  def test_invalid_profile_name_rejected(self) -> None:
    for bad in ("", "..", "a/b", r"a\\b"):
      with self.assertRaises(ProfileError):
        profile_dir(bad, self.base)

  def test_missing_user_patch_is_empty_layer(self) -> None:
    d = self._write_profile("clean", {"name": "clean", "bundles": []})
    self.assertEqual(load_profile_patch(d), {"include": [], "exclude": []})

  def test_malformed_user_patch_fails_loud(self) -> None:
    d = profile_dir("broken", self.base)
    d.mkdir(parents=True)
    (d / "profile.json").write_text(json.dumps({"name": "broken", "bundles": []}), encoding="utf-8")
    (d / PROFILE_PATCH_FILENAME).write_text("{not json", encoding="utf-8")
    with self.assertRaises(ProfileError) as cm:
      load_profile_patch(d)
    self.assertEqual(cm.exception.code, "invalid_patch")

  def test_list_profiles_only_valid_dirs(self) -> None:
    self._write_profile("alpha", {"name": "alpha", "bundles": []})
    (self.base / "empty-dir").mkdir()
    (self.base / "stray-file.txt").write_text("x", encoding="utf-8")
    self.assertEqual(list_profiles(self.base), ["alpha"])


class CompositionTests(unittest.TestCase):
  def setUp(self) -> None:
    self.tmp = tempfile.TemporaryDirectory()
    self.base = Path(self.tmp.name)
    self.store = BundleStore(store_dir=self.base / "store")

  def tearDown(self) -> None:
    self.tmp.cleanup()

  def _install_bundle(self, bundle_id: str, patch: dict | None) -> None:
    manifest = BundleManifest(
      id=bundle_id, name=bundle_id, version="1.0.0",
      extra={"patch": patch} if patch is not None else {},
    )
    src = self.base / f"src-{bundle_id}"
    src.mkdir(parents=True, exist_ok=True)
    (src / "placeholder.txt").write_text("bundle payload", encoding="utf-8")
    self.store.save_bundle(src, manifest=manifest, bundle_id=bundle_id)

  def _write_profile(self, name: str, manifest: dict, patch: dict | None = None) -> None:
    d = profile_dir(name, self.base)
    d.mkdir(parents=True, exist_ok=True)
    (d / "profile.json").write_text(json.dumps(manifest), encoding="utf-8")
    if patch is not None:
      (d / PROFILE_PATCH_FILENAME).write_text(json.dumps(patch), encoding="utf-8")

  def test_layer_order_bundles_then_profile_then_launcher(self) -> None:
    self._install_bundle("b1", {"include": ["tool:a", "tool:b"]})
    self._install_bundle("b2", {"include": [{"id": "tool:b", "options": {"mode": "fast"}}], "exclude": ["tool:a"]})
    self._install_bundle("b3", None)
    self._write_profile(
      "prod",
      {"name": "prod", "bundles": ["b1", "b2", "b3"], "patchReload": "live"},
      {"include": [{"id": "tool:profile-only", "options": {"v": 1}}]},
    )
    result = compose_profile("prod", store=self.store, base=self.base, extra_layers=[
      {"exclude": ["tool:b"]},
    ])
    self.assertTrue(result["ok"])
    self.assertEqual(result["patchReload"], "live")
    ids = [e["id"] for e in result["entries"]]
    self.assertNotIn("tool:a", ids, "b2's exclude must remove b1's include")
    self.assertNotIn("tool:b", ids, "launcher layer runs last")
    self.assertIn("tool:profile-only", ids)
    self.assertEqual(result["entries"][0]["id"], "tool:profile-only")
    self.assertEqual(result["entries"][0]["options"], {"v": 1})
    sources = [layer["source"] for layer in result["layers"]]
    self.assertEqual(sources, ["bundle:b1", "bundle:b2", "bundle:b3", "profile", "launcher:0"])

  def test_empty_bundle_patch_recorded_as_empty_layer(self) -> None:
    self._install_bundle("b-patchless", None)
    self._write_profile("slim", {"name": "slim", "bundles": ["b-patchless"]})
    result = compose_profile("slim", store=self.store, base=self.base)
    self.assertEqual(result["entries"], [])
    self.assertEqual(len(result["layers"]), 2)
    self.assertEqual(result["layers"][0]["patch"], {"include": [], "exclude": []})

  def test_unknown_bundle_fails_loud(self) -> None:
    self._write_profile("needs", {"name": "needs", "bundles": ["ghost-bundle"]})
    with self.assertRaises(ProfileError) as cm:
      compose_profile("needs", store=self.store, base=self.base)
    self.assertEqual(cm.exception.code, "bundle_not_found")
    self.assertIn("ghost-bundle", str(cm.exception))

  def test_duplicate_bundle_fails_loud(self) -> None:
    self._install_bundle("dup", None)
    self._write_profile("twice", {"name": "twice", "bundles": ["dup", "dup"]})
    with self.assertRaises(ProfileError) as cm:
      compose_profile("twice", store=self.store, base=self.base)
    self.assertEqual(cm.exception.code, "duplicate_bundle")


if __name__ == "__main__":
  unittest.main()
