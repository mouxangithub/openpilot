"""SQLite spill backend tests."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from ai.spill.sqlite_store import SqliteSpillStore


class SqliteSpillStoreTest(unittest.IsolatedAsyncioTestCase):
  async def test_round_trip_and_deterministic_locator(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / "spill.db"
      store = SqliteSpillStore(path)
      first = await store.save_text({"owner": {"session_id": "s1"}, "content": "alpha"})
      second = await store.save_text({"owner": {"session_id": "s1"}, "content": "alpha"})
      self.assertEqual(first.locator, second.locator)
      self.assertEqual(first.bytes, 5)
      self.assertEqual(await store.get_text(first.locator), "alpha")
      self.assertIsNone(await store.get_text("spill://sqlite/s1/missing"))
      self.assertEqual(len(store.list_summaries("s1")), 1)
      store.close()

  async def test_survives_new_instance(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / "spill.db"
      a = SqliteSpillStore(path)
      ref = await a.save_text({"owner": {"session_id": "s2"}, "content": "persisted"})
      a.close()
      b = SqliteSpillStore(path)
      self.assertEqual(await b.get_text(ref.locator), "persisted")
      self.assertEqual(b.list_summaries("s2")[0]["summary"], "persisted")
      b.close()


if __name__ == "__main__":
  unittest.main()
