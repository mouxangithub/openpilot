"""Tests for ai.goal.store."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai.goal.models import CreateGoalRequest, EditGoalRequest, GoalError
from ai.goal.store import GoalStore


class TestGoalStore(unittest.TestCase):
  def setUp(self) -> None:
    self.tmp = tempfile.TemporaryDirectory()
    self.store = GoalStore(Path(self.tmp.name) / "goals")

  def tearDown(self) -> None:
    self.tmp.cleanup()

  def test_create_and_get(self) -> None:
    view = self.store.create(CreateGoalRequest(objective="Test objective"))
    self.assertEqual(view.objective, "Test objective")
    self.assertEqual(view.phase, "active")
    self.assertEqual(view.revision, 1)
    self.assertEqual(view.activation, "armed")

    got = self.store.get()
    self.assertIsNotNone(got)
    self.assertEqual(got.objective, "Test objective")

  def test_duplicate_create_fails(self) -> None:
    self.store.create(CreateGoalRequest(objective="First"))
    with self.assertRaises(GoalError) as ctx:
      self.store.create(CreateGoalRequest(objective="Second"))
    self.assertEqual(ctx.exception.code, "GOAL_ALREADY_EXISTS")

  def test_replace_completed_goal(self) -> None:
    view = self.store.create(CreateGoalRequest(objective="First"))
    self.store.complete(view.ref)
    view2 = self.store.create(CreateGoalRequest(objective="Second"))
    self.assertEqual(view2.objective, "Second")

  def test_edit(self) -> None:
    view = self.store.create(CreateGoalRequest(objective="Old", max_goal_rounds=10))
    updated = self.store.edit(view.ref, EditGoalRequest(objective="New", max_goal_rounds=20))
    self.assertEqual(updated.objective, "New")
    self.assertEqual(updated.max_goal_rounds, 20)
    self.assertEqual(updated.revision, 2)

  def test_edit_empty_request_fails(self) -> None:
    view = self.store.create(CreateGoalRequest(objective="A"))
    with self.assertRaises(GoalError) as ctx:
      self.store.edit(view.ref, EditGoalRequest())
    self.assertEqual(ctx.exception.code, "GOAL_INVALID_EDIT")

  def test_stale_revision(self) -> None:
    view = self.store.create(CreateGoalRequest(objective="A"))
    self.store.edit(view.ref, EditGoalRequest(objective="B"))
    with self.assertRaises(GoalError) as ctx:
      self.store.edit(view.ref, EditGoalRequest(objective="C"))
    self.assertEqual(ctx.exception.code, "GOAL_STALE_REVISION")

  def test_pause_and_resume(self) -> None:
    view = self.store.create(CreateGoalRequest(objective="A"))
    paused = self.store.pause(view.ref)
    self.assertEqual(paused.phase, "paused")
    resumed = self.store.resume(paused.ref)
    self.assertEqual(resumed.phase, "active")
    self.assertEqual(resumed.activation, "armed")

  def test_complete(self) -> None:
    view = self.store.create(CreateGoalRequest(objective="A"))
    completed = self.store.complete(view.ref)
    self.assertEqual(completed.phase, "complete")

  def test_block(self) -> None:
    view = self.store.create(CreateGoalRequest(objective="A"))
    blocked = self.store.block(view.ref, {"code": "needs-input", "message": "Waiting for user"})
    self.assertEqual(blocked.phase, "blocked")
    self.assertEqual(blocked.blocked_reason.code, "needs-input")

  def test_clear(self) -> None:
    view = self.store.create(CreateGoalRequest(objective="A"))
    tombstone = self.store.clear(view.ref)
    self.assertEqual(tombstone.id, view.id)
    self.assertEqual(tombstone.revision, 2)
    self.assertIsNone(self.store.get())

  def test_invalid_transition(self) -> None:
    view = self.store.create(CreateGoalRequest(objective="A"))
    paused = self.store.pause(view.ref)
    with self.assertRaises(GoalError) as ctx:
      self.store.pause(paused.ref)
    self.assertEqual(ctx.exception.code, "GOAL_INVALID_TRANSITION")

  def test_round_increment(self) -> None:
    view = self.store.create(CreateGoalRequest(objective="A", max_goal_rounds=3))
    self.assertEqual(view.rounds_started, 0)
    updated = self.store.increment_round()
    self.assertIsNotNone(updated)
    self.assertEqual(updated.rounds_started, 1)

  def test_dict_ref_input(self) -> None:
    view = self.store.create({"objective": "Dict create"})
    ref_dict = {"id": view.id, "revision": view.revision}
    paused = self.store.pause(ref_dict)
    self.assertEqual(paused.phase, "paused")


if __name__ == "__main__":
  unittest.main()
