"""Tests for the SkillProvider abstraction and scope-aware merge (D-P1.3)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import ai.tests.bootstrap_pc  # noqa: F401

from ai.skill.models import Skill, SkillInvocationPolicy
from ai.skill.providers import (
  CompositeSkillProvider,
  DirectorySkillProvider,
  RegistrySkillProvider,
  filter_by_invocation,
  merge_skills,
)


def _skill(skill_id: str, *, rank: int = 600, scope: str = "global",
           model: bool = True, user: bool = True, source: str = "") -> Skill:
  return Skill(
    id=skill_id,
    name=skill_id,
    description="",
    policy="auto",
    parameters=[],
    rank=rank,
    scope=scope,
    source=source,
    invocation_policy=SkillInvocationPolicy(model_invocable=model, user_invocable=user),
  )


class MergeSkillsTests(unittest.TestCase):
  def test_lower_rank_wins(self):
    merged = merge_skills([_skill("a", rank=900), _skill("a", rank=100)])
    self.assertEqual(len(merged), 1)
    self.assertEqual(merged[0].rank, 100)

  def test_scope_tiebreak_prefers_session(self):
    merged = merge_skills([
      _skill("a", rank=600, scope="global"),
      _skill("a", rank=600, scope="session"),
    ])
    self.assertEqual(len(merged), 1)
    self.assertEqual(merged[0].scope, "session")

  def test_provider_order_tiebreak(self):
    merged = merge_skills(
      [_skill("a", rank=600, source="p2"), _skill("a", rank=600, source="p1")],
      provider_order={"p1": 0, "p2": 1},
    )
    self.assertEqual(merged[0].source, "p1")

  def test_distinct_ids_preserved(self):
    merged = merge_skills([_skill("a"), _skill("b")])
    self.assertEqual([s.id for s in merged], ["a", "b"])


class FilterByInvocationTests(unittest.TestCase):
  def test_model_actor_filters(self):
    skills = [_skill("m", model=True), _skill("n", model=False)]
    self.assertEqual([s.id for s in filter_by_invocation(skills, actor="model")], ["m"])

  def test_user_actor_filters(self):
    skills = [_skill("m", user=True), _skill("n", user=False)]
    self.assertEqual([s.id for s in filter_by_invocation(skills, actor="user")], ["m"])

  def test_unknown_actor_raises(self):
    with self.assertRaises(ValueError):
      filter_by_invocation([_skill("a")], actor="robot")  # type: ignore[arg-type]


class RegistrySkillProviderTests(unittest.TestCase):
  def test_wraps_registry(self):
    from ai.skill.registry import SkillRegistry

    registry = SkillRegistry(Path(tempfile.mkdtemp()) / "skills")
    registry.register(_skill("global_skill"))
    provider = RegistrySkillProvider(registry, name="reg")
    self.assertEqual(provider.name, "reg")
    self.assertEqual([s.id for s in provider.list_skills()], ["global_skill"])
    self.assertEqual(provider.get("global_skill").id, "global_skill")
    self.assertIsNone(provider.get("missing"))


class DirectorySkillProviderTests(unittest.TestCase):
  def test_loads_per_skill_and_aggregate_manifests(self):
    root = Path(tempfile.mkdtemp())
    (root / "alpha").mkdir()
    (root / "alpha" / "skill.json").write_text(
      json.dumps({"id": "alpha", "name": "Alpha", "description": "", "policy": "auto", "rank": 300}),
      encoding="utf-8",
    )
    (root / "manifest.json").write_text(
      json.dumps({"skills": [{"id": "beta", "name": "Beta", "description": "", "policy": "auto"}]}),
      encoding="utf-8",
    )
    provider = DirectorySkillProvider(root)
    ids = {s.id for s in provider.list_skills()}
    self.assertEqual(ids, {"alpha", "beta"})
    self.assertEqual(provider.get("alpha").rank, 300)
    # Source defaults to the manifest file path.
    self.assertTrue(str(provider.get("alpha").source).startswith("file://"))

  def test_cache_and_invalidate(self):
    root = Path(tempfile.mkdtemp())
    (root / "manifest.json").write_text(json.dumps({"skills": [{"id": "one", "name": "One", "description": "", "policy": "auto"}]}), encoding="utf-8")
    provider = DirectorySkillProvider(root)
    self.assertEqual({s.id for s in provider.list_skills()}, {"one"})
    # New manifest added after first load is not visible until invalidate().
    (root / "manifest.json").write_text(json.dumps({"skills": [{"id": "two", "name": "Two", "description": "", "policy": "auto"}]}), encoding="utf-8")
    self.assertEqual({s.id for s in provider.list_skills()}, {"one"})
    provider.invalidate()
    self.assertEqual({s.id for s in provider.list_skills()}, {"two"})


class CompositeSkillProviderTests(unittest.TestCase):
  def test_merges_and_resolves_lowest_rank(self):
    from ai.skill.registry import SkillRegistry

    registry = SkillRegistry(Path(tempfile.mkdtemp()) / "skills")
    registry.register(_skill("shared", rank=600, scope="global", source="registry"))
    reg_provider = RegistrySkillProvider(registry, name="registry")

    root = Path(tempfile.mkdtemp())
    (root / "manifest.json").write_text(
      json.dumps({"skills": [{"id": "shared", "name": "Shared", "description": "", "policy": "auto", "rank": 100}]}),
      encoding="utf-8",
    )
    dir_provider = DirectorySkillProvider(root, name="dir")

    composite = CompositeSkillProvider([reg_provider, dir_provider])
    merged = composite.list_skills()
    self.assertEqual(len(merged), 1)
    self.assertEqual(merged[0].rank, 100)
    self.assertEqual(composite.get("shared").rank, 100)
    self.assertIsNone(composite.get("absent"))

  def test_add_provider(self):
    composite = CompositeSkillProvider()
    self.assertEqual(composite.providers, [])
    composite.add(RegistrySkillProvider(type("R", (), {"list_skills": lambda self: [], "get": lambda self, i: None})(), name="empty"))
    self.assertEqual(len(composite.providers), 1)
    self.assertEqual(composite.list_skills(), [])


if __name__ == "__main__":
  unittest.main()
