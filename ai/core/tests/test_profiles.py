"""Tests for ai.core.profiles store and manager."""

import tempfile
import unittest
from pathlib import Path

from ai.core.profiles.profile import Profile, ProfileDomain
from ai.core.profiles.store import ProfileStore


class ProfileStoreTestCase(unittest.TestCase):
  def test_round_trip(self):
    with tempfile.TemporaryDirectory() as tmp:
      store = ProfileStore(tmp)
      p = Profile(
        id="comfort",
        name="舒适",
        domain=ProfileDomain.TUNE,
        description="舒适跟车",
        settings={"preset_id": "comfort_follow"},
      )
      store.save(p)
      loaded = store.get(ProfileDomain.TUNE, "comfort")
      self.assertIsNotNone(loaded)
      assert loaded is not None
      self.assertEqual(loaded.name, "舒适")
      self.assertEqual(loaded.settings["preset_id"], "comfort_follow")

  def test_list_by_domain(self):
    with tempfile.TemporaryDirectory() as tmp:
      store = ProfileStore(tmp)
      store.save(Profile(id="a", name="A", domain=ProfileDomain.TUNE))
      store.save(Profile(id="b", name="B", domain=ProfileDomain.VEHICLE))
      self.assertEqual(len(store.list(ProfileDomain.TUNE)), 1)
      self.assertEqual(len(store.list()), 2)

  def test_import_export(self):
    with tempfile.TemporaryDirectory() as tmp:
      store = ProfileStore(tmp)
      store.save(Profile(id="a", name="A", domain=ProfileDomain.HARNESS, settings={"modelTier": "fast"}))
      exported = store.export_all()
      self.assertEqual(exported["version"], 1)
      self.assertEqual(len(exported["profiles"]), 1)

      with tempfile.TemporaryDirectory() as tmp2:
        store2 = ProfileStore(tmp2)
        imported = store2.import_all(exported)
        self.assertEqual(len(imported), 1)
        self.assertEqual(store2.get(ProfileDomain.HARNESS, "a").settings["modelTier"], "fast")


class ProfileManagerTestCase(unittest.TestCase):
  def test_apply_tune_resolves_preset(self):
    with tempfile.TemporaryDirectory() as tmp:
      from ai.core.profiles.manager import ProfileManager
      mgr = ProfileManager(ProfileStore(tmp))
      p = Profile(id="comfort_follow", name="舒适", domain=ProfileDomain.TUNE, settings={"preset_id": "comfort_follow"})
      result = mgr.apply(p)
      self.assertTrue(result["ok"])
      self.assertEqual(result["applied"], "comfort_follow")

  def test_apply_tune_unknown_preset(self):
    with tempfile.TemporaryDirectory() as tmp:
      from ai.core.profiles.manager import ProfileManager
      mgr = ProfileManager(ProfileStore(tmp))
      p = Profile(id="missing", name="Missing", domain=ProfileDomain.TUNE)
      result = mgr.apply(p)
      self.assertFalse(result["ok"])


if __name__ == "__main__":
  unittest.main()
