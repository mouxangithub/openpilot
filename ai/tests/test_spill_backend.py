"""Tests for spill backend hardening (D-P0.4)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class TestLocalSpillBackend(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.base = Path(self.tmp.name)

  def tearDown(self):
    self.tmp.cleanup()

  def test_store_load_roundtrip(self):
    from ai.tools.spill_backend import LocalSpillBackend
    backend = LocalSpillBackend(self.base, harden=True)
    res = backend.store("ref-1", b"hello", session_id="s1", tool_name="echo", ext="txt")
    self.assertTrue(res["ok"])
    self.assertEqual(backend.load("ref-1"), b"hello")
    self.assertIn("ref-1", backend.list_refs())

  def test_remove(self):
    from ai.tools.spill_backend import LocalSpillBackend
    backend = LocalSpillBackend(self.base, harden=True)
    backend.store("ref-2", b"x", session_id="s2", tool_name="t", ext="bin")
    self.assertTrue(backend.remove("ref-2"))
    self.assertIsNone(backend.load("ref-2"))

  def test_symlink_refused(self):
    from ai.tools.spill_backend import LocalSpillBackend
    backend = LocalSpillBackend(self.base, harden=True)
    # Create a symlink dir and try to write through it.
    target = self.base / "real"
    target.mkdir()
    (target / "victim.txt").write_text("keep")
    link = self.base / "link"
    try:
      link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
      self.skipTest("symlink unsupported on this platform")
    # The backend builds paths under its own base_dir; a pre-existing symlink
    # file in the write path must be rejected. Simulate by making the target
    # file a symlink.
    sym = self.base / "s1" / "echo_ref-3.txt"
    sym.parent.mkdir(parents=True, exist_ok=True)
    try:
      sym.symlink_to(target / "victim.txt")
    except OSError:
      self.skipTest("symlink unsupported")
    if not sym.is_symlink():
      self.skipTest("platform did not create a usable symlink")
    res = backend.store("ref-3", b"evil", session_id="s1", tool_name="echo", ext="txt")
    self.assertFalse(res["ok"])
    self.assertEqual((target / "victim.txt").read_text(), "keep")


if __name__ == "__main__":
  unittest.main()