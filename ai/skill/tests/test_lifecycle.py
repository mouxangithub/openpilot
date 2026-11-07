"""Lifecycle tests for Skill scope/version/disposal/diagnose/conflicts."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai.skill.conflicts import SkillConflictReport, check_conflicts
from ai.skill.diagnostics import SkillDiagnosticsReport, diagnose_skill
from ai.skill.models import Skill, SkillDependency, SkillError, SkillParameter
from ai.skill.registry import SkillRegistry


class TestSkillLifecycleModels(unittest.TestCase):
  def test_skill_has_lifecycle_fields(self):
    skill = Skill(
      id="lifecycle_skill",
      name="Lifecycle skill",
      description="demo",
      policy="auto",
      parameters=[],
      scope="session",
      version="1.2.3",
      capabilities=["io", "demo"],
      dependencies=[SkillDependency(name="base", version_constraint="^1.0.0")],
      source="file:///demo.py",
    )
    self.assertEqual(skill.scope, "session")
    self.assertEqual(skill.version, "1.2.3")
    self.assertEqual(skill.capabilities, ["io", "demo"])
    self.assertEqual(skill.dependencies[0].name, "base")
    self.assertEqual(skill.source, "file:///demo.py")

  def test_skill_from_dict_parses_dependencies(self):
    data = {
      "id": "x",
      "name": "X",
      "description": "x",
      "policy": "auto",
      "parameters": [],
      "version": "2.0.0",
      "scope": "project",
      "capabilities": ["a"],
      "dependencies": [{"name": "dep", "version_constraint": ">=1.0.0", "optional": True}],
      "source": "builtin:test",
    }
    skill = Skill.from_dict(data)
    self.assertEqual(skill.version, "2.0.0")
    self.assertEqual(skill.scope, "project")
    self.assertEqual(skill.capabilities, ["a"])
    self.assertTrue(skill.dependencies[0].optional)
    self.assertEqual(skill.dependencies[0].version_constraint, ">=1.0.0")

  def test_skill_to_dict_roundtrip(self):
    skill = Skill(
      id="y",
      name="Y",
      description="y",
      policy="confirm",
      parameters=[SkillParameter(name="n", type="integer", description="n")],
      scope="session",
      version="0.1.0",
      capabilities=["math"],
      dependencies=[SkillDependency(name="z")],
      source="https://example.com/y",
    )
    restored = Skill.from_dict(skill.to_dict())
    self.assertEqual(restored.id, "y")
    self.assertEqual(restored.scope, "session")
    self.assertEqual(restored.version, "0.1.0")
    self.assertEqual(restored.capabilities, ["math"])
    self.assertEqual(restored.dependencies[0].name, "z")


class TestSkillDiagnostics(unittest.TestCase):
  def _registry(self) -> SkillRegistry:
    return SkillRegistry(Path(tempfile.mkdtemp()) / "skills")

  def test_diagnose_builtin_is_healthy(self):
    registry = self._registry()
    registry.register(Skill(
      id="base",
      name="Base",
      description="base",
      policy="auto",
      parameters=[],
      version="1.0.0",
      source="builtin:core",
    ))
    report = registry.diagnose("base")
    self.assertIsInstance(report, SkillDiagnosticsReport)
    self.assertTrue(report.ok)
    self.assertTrue(report.deps_ok)
    self.assertTrue(report.caps_ok)
    self.assertTrue(report.source_trusted)

  def test_diagnose_missing_dependency(self):
    registry = self._registry()
    registry.register(Skill(
      id="child",
      name="Child",
      description="child",
      policy="auto",
      parameters=[],
      version="1.0.0",
      dependencies=[SkillDependency(name="missing")],
    ))
    report = registry.diagnose("child")
    self.assertFalse(report.deps_ok)
    self.assertIn("missing dependency: missing", report.warnings)

  def test_diagnose_version_mismatch(self):
    registry = self._registry()
    registry.register(Skill(
      id="dep",
      name="Dep",
      description="dep",
      policy="auto",
      parameters=[],
      version="1.0.0",
    ))
    registry.register(Skill(
      id="child",
      name="Child",
      description="child",
      policy="auto",
      parameters=[],
      version="1.0.0",
      dependencies=[SkillDependency(name="dep", version_constraint="^2.0.0")],
    ))
    report = registry.diagnose("child")
    self.assertFalse(report.deps_ok)
    self.assertTrue(any("does not satisfy" in w for w in report.warnings))

  def test_diagnose_untrusted_source(self):
    registry = self._registry()
    registry.register(Skill(
      id="untrusted",
      name="Untrusted",
      description="x",
      policy="auto",
      parameters=[],
      source="http://example.com/x",
    ))
    report = registry.diagnose("untrusted")
    self.assertFalse(report.source_trusted)

  def test_diagnose_missing_skill_returns_report(self):
    registry = self._registry()
    report = registry.diagnose("missing")
    self.assertIsInstance(report, SkillDiagnosticsReport)
    self.assertFalse(report.ok)
    self.assertEqual(report.error, "skill missing not found")

  def test_diagnose_skill_function(self):
    base = Skill(id="base", name="Base", description="b", policy="auto", parameters=[], version="1.2.0")
    child = Skill(
      id="child",
      name="Child",
      description="c",
      policy="auto",
      parameters=[],
      version="1.0.0",
      dependencies=[SkillDependency(name="base", version_constraint="^1.0.0")],
    )
    store = {"base": base, "child": child}

    def resolve(sid: str):
      if sid not in store:
        raise SkillError(f"skill {sid} not found", "SKILL_NOT_FOUND")
      return store[sid]

    report = diagnose_skill(child, resolve_dependency=resolve)
    self.assertTrue(report.deps_ok)
    self.assertEqual(report.dependencies[0]["version"], "1.2.0")
    self.assertTrue(report.dependencies[0]["satisfied"])


class TestSkillConflicts(unittest.TestCase):
  def _registry(self) -> SkillRegistry:
    return SkillRegistry(Path(tempfile.mkdtemp()) / "skills")

  def test_no_conflicts_for_unique_skills(self):
    registry = self._registry()
    registry.register(Skill(id="a", name="A", description="x", policy="auto", parameters=[]))
    registry.register(Skill(id="b", name="B", description="y", policy="auto", parameters=[]))
    report = registry.check_conflicts()
    self.assertIsInstance(report, SkillConflictReport)
    self.assertTrue(report.ok)

  def test_duplicate_id_reported(self):
    registry = self._registry()
    registry.register(Skill(id="dup", name="D1", description="x", policy="auto", parameters=[], version="1.0.0"))
    # Simulate duplicate by direct mutation for the in-memory check.
    registry._skills["dup2"] = Skill(id="dup", name="D2", description="y", policy="auto", parameters=[], version="2.0.0")
    report = registry.check_conflicts()
    self.assertFalse(report.ok)
    self.assertTrue(any(c["skill_id"] == "dup" for c in report.duplicate_ids))

  def test_missing_dependency_reported(self):
    registry = self._registry()
    registry.register(Skill(
      id="orphan",
      name="Orphan",
      description="x",
      policy="auto",
      parameters=[],
      dependencies=[SkillDependency(name="gone")],
    ))
    report = registry.check_conflicts()
    self.assertFalse(report.ok)
    self.assertTrue(any(m["missing"] == "gone" for m in report.missing_deps))

  def test_cyclic_dependency_detected(self):
    registry = self._registry()
    registry.register(Skill(
      id="a",
      name="A",
      description="x",
      policy="auto",
      parameters=[],
      dependencies=[SkillDependency(name="b")],
    ))
    registry.register(Skill(
      id="b",
      name="B",
      description="y",
      policy="auto",
      parameters=[],
      dependencies=[SkillDependency(name="a")],
    ))
    report = registry.check_conflicts()
    self.assertFalse(report.ok)
    self.assertTrue(len(report.cycles) > 0)


class TestSkillDispose(unittest.TestCase):
  def _registry(self) -> SkillRegistry:
    return SkillRegistry(Path(tempfile.mkdtemp()) / "skills")

  def test_dispose_calls_handler_dispose(self):
    registry = self._registry()

    class Handler:
      def __init__(self) -> None:
        self.disposed = False

      def __call__(self) -> dict[str, bool]:
        return {"ok": True}

      def dispose(self) -> None:
        self.disposed = True

    handler = Handler()
    registry.register(Skill(
      id="dispose_me",
      name="D",
      description="x",
      policy="auto",
      parameters=[],
      handler=handler,
    ))
    report = registry.dispose("dispose_me")
    self.assertTrue(report["ok"])
    self.assertTrue(handler.disposed)

  def test_dispose_failure_disables_skill(self):
    registry = self._registry()

    class BadHandler:
      def __call__(self) -> dict[str, bool]:
        return {"ok": True}

      def dispose(self) -> None:
        raise RuntimeError("boom")

    handler = BadHandler()
    registry.register(Skill(
      id="bad",
      name="Bad",
      description="x",
      policy="auto",
      parameters=[],
      handler=handler,
    ))
    report = registry.dispose("bad")
    self.assertFalse(report["ok"])
    self.assertIn("boom", report["error"])
    self.assertEqual(registry.get("bad").policy, "disabled")

  def test_dispose_missing_skill(self):
    registry = self._registry()
    report = registry.dispose("missing")
    self.assertFalse(report["ok"])


class TestSessionOverlay(unittest.TestCase):
  def _registry(self) -> SkillRegistry:
    return SkillRegistry(Path(tempfile.mkdtemp()) / "skills")

  def test_session_scope_registration(self):
    registry = self._registry()
    registry.register(Skill(id="global", name="Global", description="x", policy="auto", parameters=[], scope="global"))
    session = registry.for_session("s1")
    session.register(Skill(id="local", name="Local", description="y", policy="auto", parameters=[], scope="session"))
    self.assertEqual(session.get("local").scope, "session")
    self.assertEqual(session.get("global").scope, "global")

  def test_session_diagnose_and_conflicts(self):
    registry = self._registry()
    session = registry.for_session("s2")
    session.register(Skill(
      id="local",
      name="Local",
      description="x",
      policy="auto",
      parameters=[],
      dependencies=[SkillDependency(name="missing")],
    ))
    diag = session.diagnose("local")
    self.assertFalse(diag["deps_ok"])
    conflicts = session.check_conflicts()
    self.assertFalse(conflicts["ok"])


class TestRegistryPersistence(unittest.TestCase):
  def test_lifecycle_fields_persist(self):
    tmp = Path(tempfile.mkdtemp()) / "skills"
    registry = SkillRegistry(tmp)
    registry.register(Skill(
      id="persist",
      name="Persist",
      description="x",
      policy="auto",
      parameters=[],
      scope="project",
      version="3.4.5",
      capabilities=["io"],
      dependencies=[SkillDependency(name="base", version_constraint="^1.0.0")],
      source="file:///persist.py",
    ))

    registry2 = SkillRegistry(tmp)
    skill = registry2.get("persist")
    self.assertEqual(skill.scope, "project")
    self.assertEqual(skill.version, "3.4.5")
    self.assertEqual(skill.capabilities, ["io"])
    self.assertEqual(skill.dependencies[0].version_constraint, "^1.0.0")
    self.assertEqual(skill.source, "file:///persist.py")


if __name__ == "__main__":
  unittest.main()
