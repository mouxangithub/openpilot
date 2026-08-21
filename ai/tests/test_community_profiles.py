"""Tests for community fork registry matching."""

from __future__ import annotations

import unittest

from ai.fork.community_profiles import match_community_profile


class TestCommunityProfiles(unittest.TestCase):
  def test_match_dragonpilot_remote(self):
    scan = {
      "remote_identity": {"slug": "dragonpilot/dragonpilot", "owner": "dragonpilot", "repo": "dragonpilot"},
      "distinctive_dirs": [],
      "root_files": ["d2"],
      "git_branch": "d2",
      "param_prefixes": {"dp_": 12},
      "readme_excerpt": "",
    }
    profile = match_community_profile(scan)
    self.assertIsNotNone(profile)
    assert profile is not None
    self.assertEqual(profile["id"], "dragonpilot/dragonpilot")
    self.assertGreater(profile["_match_score"], 50)

  def test_match_sunnypilot_dir(self):
    scan = {
      "remote_identity": {"slug": "sunnypilot/sunnypilot"},
      "distinctive_dirs": ["sunnypilot"],
      "root_files": [],
      "param_prefixes": {"Sp": 8},
      "readme_excerpt": "",
      "git_branch": "dev",
      "openpilot_root": ".",
    }
    profile = match_community_profile(scan)
    self.assertIsNotNone(profile)
    assert profile is not None
    self.assertIn("sunnypilot", profile["id"].lower())

  def test_bluepilot_remote_ignored_on_sunnypilot_tree(self):
    """Auxiliary bp remote must not beat sunnypilot when bluepilot/ dir is absent."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      (root / "sunnypilot").mkdir()
      scan = {
        "openpilot_root": str(root),
        "remote_identity": {"slug": "mouxangithub/openpilot", "owner": "mouxangithub", "repo": "openpilot"},
        "distinctive_dirs": [],
        "root_files": [],
        "param_prefixes": {"Sp": 6, "SunnylinkCache_": 2},
        "readme_excerpt": "sunnypilot fork",
        "git_branch": "master-c3",
      }
      profile = match_community_profile(scan)
      self.assertIsNotNone(profile)
      assert profile is not None
      self.assertNotEqual(profile["id"], "BluePilotDev/bluepilot")
      self.assertIn(profile["id"], ("mouxangithub/openpilot", "sunnypilot/sunnypilot"))


if __name__ == "__main__":
  unittest.main()
