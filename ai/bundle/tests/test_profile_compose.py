"""Tests for G8 ProfileComposer."""
from __future__ import annotations
import unittest
from dataclasses import dataclass

from ai.bundle.profile_compose import ProfileComposer, PatchLayer


@dataclass
class FakeManifest:
  ops: list[dict]
  def patch_operations(self) -> list[dict]:
    return list(self.ops)


class ProfileComposeTest(unittest.TestCase):
  def setUp(self) -> None:
    self.bundles = {
      "base": FakeManifest([{"op": "set", "path": "a", "value": 1}, {"op": "set", "path": "shared", "value": "base"}]),
      "addon": FakeManifest([{"op": "set", "path": "b", "value": 2}, {"op": "set", "path": "shared", "value": "addon"}]),
    }
    self.composer = ProfileComposer(resolve_bundle=lambda bid: self.bundles[bid], get_profile_config=lambda _pid: {"profile_key": "p", "shared": "profile"})

  def test_preview_order(self) -> None:
    layers = self.composer.preview("p1", ["base", "addon"])
    self.assertEqual([l.source for l in layers], ["base", "addon", "profile"])
    self.assertEqual([l.order for l in layers], [0, 1, 2])

  def test_compose_and_conflicts(self) -> None:
    config, conflicts = self.composer.compose("p1", ["base", "addon"])
    self.assertEqual(config["a"], 1)
    self.assertEqual(config["b"], 2)
    self.assertEqual(config["profile_key"], "p")
    self.assertEqual(config["shared"], "profile")
    self.assertTrue(any("shared" in c for c in conflicts))

  def test_delete_operation(self) -> None:
    bundles = {"x": FakeManifest([{"op": "set", "path": "a", "value": 1}, {"op": "delete", "path": "a"}])}
    c = ProfileComposer(resolve_bundle=lambda bid: bundles[bid], get_profile_config=lambda _pid: {})
    merged, conflicts = c.compose("p", ["x"])
    self.assertNotIn("a", merged)
    self.assertEqual(conflicts, [])

  def test_idempotent(self) -> None:
    self.assertEqual(self.composer.compose("p1", ["base"]), self.composer.compose("p1", ["base"]))


if __name__ == "__main__":
  unittest.main()