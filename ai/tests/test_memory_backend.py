"""Tests for the unified memory backend abstraction (T-P1.2)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import ai.tests.bootstrap_pc  # noqa: F401


class TestMemoryBackend(unittest.TestCase):
  def setUp(self):
    from ai.common.memory_backend import NotesMemoryBackend
    self._notes = NotesMemoryBackend(None)

  def _patch_daily(self):
    from ai.common import memory_backend
    real_dir = None
    store = {}
    import ai.tools.domains.core.daily_memory as dm
    real_append = dm.append_daily_memory
    def _fake_append(bullets, session_id="", title=None):
      store["_last"] = {"bullets": bullets, "session_id": session_id, "title": title}
      return {"ok": True}
    dm.append_daily_memory = _fake_append
    self.addCleanup(lambda: setattr(dm, "append_daily_memory", real_append))
    return store

  def test_default_backends_two(self):
    from ai.common.memory_backend import default_backends
    backends = default_backends(None)
    self.assertEqual(len(backends), 2)

  def test_notes_append(self):
    from ai.common.memory_backend import NotesMemoryBackend
    backend = NotesMemoryBackend(None)
    res = backend.append("test note", tags=["t"])
    self.assertTrue(res.get("ok", True))
    self.assertGreaterEqual(backend.count(), 1)

  def test_append_unified_fans_out(self):
    from ai.common.memory_backend import append_unified_memory
    store = self._patch_daily()
    result = append_unified_memory("unified observation", tags=["u"], session_id="s1", title="T")
    self.assertTrue(result["ok"])
    self.assertIn("notesmemory", result["backends"])
    self.assertIn("dailymemory", result["backends"])
    self.assertEqual(store["_last"]["title"], "T")

  def test_backend_kind_default(self):
    from ai.common.memory_backend import DailyMemoryBackend, NotesMemoryBackend
    self.assertEqual(NotesMemoryBackend(None).kind(), "notesmemory")
    self.assertEqual(DailyMemoryBackend().kind(), "dailymemory")


if __name__ == "__main__":
  unittest.main()