"""Tests for ai.skill registry and invocation policy."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai.skill.models import Skill, SkillError, SkillParameter
from ai.skill.registry import SkillRegistry


class TestSkillRegistry(unittest.TestCase):
  def setUp(self) -> None:
    self.tmp = tempfile.TemporaryDirectory()
    self.registry = SkillRegistry(self.tmp.name)

  def tearDown(self) -> None:
    self.tmp.cleanup()

  def _sample_skill(self, policy: str = "auto") -> Skill:
    return Skill(
      id="read_file",
      name="Read file",
      description="Reads a file from disk.",
      policy=policy,
      parameters=[
        SkillParameter(name="path", type="string", description="File path", required=True),
      ],
      handler=lambda path: f"content:{path}",
    )

  def test_register_and_get(self) -> None:
    skill = self._sample_skill()
    self.registry.register(skill)
    found = self.registry.get("read_file")
    self.assertEqual(found.id, "read_file")
    self.assertEqual(found.policy, "auto")

  def test_persistence(self) -> None:
    skill = self._sample_skill()
    self.registry.register(skill)

    registry2 = SkillRegistry(self.tmp.name)
    found = registry2.get("read_file")
    self.assertEqual(found.name, "Read file")

  def test_unregister(self) -> None:
    self.registry.register(self._sample_skill())
    self.assertTrue(self.registry.unregister("read_file"))
    with self.assertRaises(SkillError) as ctx:
      self.registry.get("read_file")
    self.assertEqual(ctx.exception.code, "SKILL_NOT_FOUND")

  def test_auto_policy_executes(self) -> None:
    self.registry.register(self._sample_skill("auto"))
    inv = self.registry.request_invocation("read_file", {"path": "/tmp/foo"})
    self.assertEqual(inv.status, "success")
    self.assertEqual(inv.result, "content:/tmp/foo")

  def test_confirm_policy_returns_pending(self) -> None:
    self.registry.register(self._sample_skill("confirm"))
    inv = self.registry.request_invocation("read_file", {"path": "/tmp/foo"})
    self.assertEqual(inv.status, "pending")

  def test_confirm_policy_can_auto_confirm(self) -> None:
    self.registry.register(self._sample_skill("confirm"))
    inv = self.registry.request_invocation("read_file", {"path": "/tmp/foo"}, auto_confirm=True)
    self.assertEqual(inv.status, "success")

  def test_disabled_policy_rejected(self) -> None:
    self.registry.register(self._sample_skill("disabled"))
    with self.assertRaises(SkillError) as ctx:
      self.registry.request_invocation("read_file", {"path": "/tmp/foo"})
    self.assertEqual(ctx.exception.code, "SKILL_DISABLED")

  def test_missing_required_arg(self) -> None:
    self.registry.register(self._sample_skill())
    with self.assertRaises(SkillError) as ctx:
      self.registry.request_invocation("read_file", {})
    self.assertEqual(ctx.exception.code, "SKILL_INVALID_ARGS")

  def test_tool_definitions(self) -> None:
    self.registry.register(self._sample_skill())
    tools = self.registry.build_tool_definitions()
    self.assertEqual(len(tools), 1)
    self.assertEqual(tools[0]["function"]["name"], "read_file")
    self.assertIn("path", tools[0]["function"]["parameters"]["required"])

  def test_disabled_skipped_in_tools(self) -> None:
    self.registry.register(self._sample_skill("disabled"))
    tools = self.registry.build_tool_definitions()
    self.assertEqual(len(tools), 0)


if __name__ == "__main__":
  unittest.main()
