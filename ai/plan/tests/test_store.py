"""Tests for ai.plan.store."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai.plan.store import PlanStore


class TestPlanStore(unittest.TestCase):
  def setUp(self) -> None:
    self.tmp = tempfile.TemporaryDirectory()
    self.store = PlanStore(Path(self.tmp.name) / "plans")

  def tearDown(self) -> None:
    self.tmp.cleanup()

  def test_create_and_get(self) -> None:
    plan = self.store.create("Tune review", steps=[{"id": "s1", "description": "Read params"}])
    self.assertEqual(plan.title, "Tune review")
    self.assertEqual(plan.status, "draft")
    self.assertEqual(len(plan.steps), 1)

    got = self.store.get(plan.id)
    self.assertIsNotNone(got)
    assert got is not None
    self.assertEqual(got.title, "Tune review")

  def test_update_status(self) -> None:
    plan = self.store.create("Health check")
    updated = self.store.update(plan.id, {"status": "active"})
    self.assertEqual(updated.status, "active")

  def test_set_step_status_completes_plan(self) -> None:
    plan = self.store.create(
      "Health check",
      steps=[
        {"id": "s1", "description": "Check engage", "status": "pending"},
        {"id": "s2", "description": "Check panda", "status": "pending"},
      ],
    )
    self.store.activate(plan.id)
    self.store.set_step_status(plan.id, "s1", "completed")
    self.store.set_step_status(plan.id, "s2", "completed")
    got = self.store.get(plan.id)
    assert got is not None
    self.assertEqual(got.status, "complete")

  def test_list_and_delete(self) -> None:
    p1 = self.store.create("A")
    p2 = self.store.create("B")
    self.assertEqual(len(self.store.list_all()), 2)
    self.assertTrue(self.store.delete(p1.id))
    self.assertEqual(len(self.store.list_all()), 1)
    self.assertIsNone(self.store.get(p1.id))

  def test_mode(self) -> None:
    projection = self.store.set_mode(True)
    self.assertTrue(projection.active)


if __name__ == "__main__":
  unittest.main()
