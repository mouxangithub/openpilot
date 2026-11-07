"""Tests for ai.todo.store."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai.todo.models import TodoItem
from ai.todo.store import TodoStore


class TestTodoStore(unittest.TestCase):
  def setUp(self) -> None:
    self.tmp = tempfile.TemporaryDirectory()
    self.store = TodoStore(Path(self.tmp.name) / "todos")

  def tearDown(self) -> None:
    self.tmp.cleanup()

  def test_write_and_get(self) -> None:
    result = self.store.write([
      {"content": "First", "status": "in_progress"},
      {"content": "Second", "status": "pending"},
    ])
    self.assertEqual(result["counts"]["inProgress"], 1)
    self.assertEqual(result["counts"]["pending"], 1)

    state = self.store.get()
    self.assertEqual(len(state["todos"]), 2)

  def test_whole_list_replace(self) -> None:
    self.store.write([{"content": "Old", "status": "completed"}])
    result = self.store.write([{"content": "New", "status": "pending"}])
    self.assertEqual(len(result["todos"]), 1)
    self.assertEqual(result["todos"][0]["content"], "New")

  def test_empty_content_rejected(self) -> None:
    with self.assertRaises(ValueError):
      self.store.write([{"content": "   ", "status": "pending"}])

  def test_duplicate_content_rejected(self) -> None:
    with self.assertRaises(ValueError):
      self.store.write([
        {"content": "Dup", "status": "pending"},
        {"content": "Dup", "status": "pending"},
      ])

  def test_single_active_policy(self) -> None:
    with self.assertRaises(ValueError):
      self.store.write([
        {"content": "A", "status": "in_progress"},
        {"content": "B", "status": "in_progress"},
      ], allow_parallel=False)

  def test_todo_item_objects(self) -> None:
    result = self.store.write([
      TodoItem(content="Task A", status="completed"),
    ])
    self.assertEqual(result["counts"]["completed"], 1)

  def test_clear(self) -> None:
    self.store.write([{"content": "A", "status": "pending"}])
    result = self.store.clear()
    self.assertEqual(len(result["todos"]), 0)
    self.assertEqual(result["counts"]["pending"], 0)


if __name__ == "__main__":
  unittest.main()
