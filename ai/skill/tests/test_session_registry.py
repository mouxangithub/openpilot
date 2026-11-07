"""SessionSkillRegistry lifecycle tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import ai.tests.bootstrap_pc  # noqa: F401

from ai.skill.models import Skill, SkillParameter
from ai.skill.registry import SkillRegistry
from ai.skill.session_registry import SessionSkillRegistry


class SessionRegistryTests(unittest.TestCase):
  def _registry(self) -> SkillRegistry:
    return SkillRegistry(Path(tempfile.mkdtemp()) / "skills")

  def test_session_overrides_global(self):
    global_reg = self._registry()
    skill = Skill(id="echo", name="Echo", description="x", policy="auto", parameters=[], metadata={"version": "1.0.0"})
    global_reg.register(skill)

    session_reg = global_reg.for_session("s1")
    local = Skill(id="echo", name="Local Echo", description="y", policy="auto", parameters=[], metadata={"version": "2.0.0"})
    session_reg.register(local)

    self.assertEqual(session_reg.get("echo").name, "Local Echo")
    self.assertEqual(global_reg.get("echo").name, "Echo")

  def test_list_skills_union(self):
    global_reg = self._registry()
    global_reg.register(Skill(id="a", name="A", description="x", policy="auto", parameters=[]))
    session_reg = global_reg.for_session("s1")
    session_reg.register(Skill(id="b", name="B", description="y", policy="auto", parameters=[]))
    ids = {s.id for s in session_reg.list_skills()}
    self.assertEqual(ids, {"a", "b"})

  def test_dispose_calls_handler_dispose(self):
    global_reg = self._registry()

    class Handler:
      disposed = False

      def __call__(self) -> dict[str, bool]:
        return {"ok": True}

      def dispose(self) -> None:
        self.disposed = True

    handler = Handler()
    skill = Skill(id="dispose_me", name="D", description="x", policy="auto", parameters=[], handler=handler)
    global_reg.register(skill)

    report = global_reg.dispose("dispose_me")
    self.assertTrue(report["ok"])
    self.assertTrue(handler.disposed)

  def test_session_dispose_all(self):
    global_reg = self._registry()
    session_reg = global_reg.for_session("s2")

    class Handler:
      def __init__(self) -> None:
        self.disposed = False

      def dispose(self) -> None:
        self.disposed = True

    h = Handler()
    session_reg.register(Skill(id="x", name="X", description="x", policy="auto", parameters=[], handler=h))
    reports = session_reg.dispose_all()
    self.assertEqual(len(reports), 1)
    self.assertTrue(h.disposed)


if __name__ == "__main__":
  unittest.main()
