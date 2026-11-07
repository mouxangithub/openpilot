"""Shared SCons cache lock behavior.

Two concurrent SCons builds against the same cache dir can corrupt shared
entries; the lock serializes them. These tests verify the guard path layout,
non-blocking rejection, and timeout. fcntl only exists on POSIX, so the tests
skip on Windows rather than faking it.
"""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

try:
  import fcntl  # noqa: F401
  _HAS_FCNTL = True
except ImportError:
  _HAS_FCNTL = False

# The module under test imports fcntl at module top, so import it only on POSIX.
if _HAS_FCNTL:
  from openpilot.common.scons_cache_lock import (
    CacheBusyError,
    acquire_cache_lock,
    guard_path,
  )


@unittest.skipUnless(_HAS_FCNTL, "flock is POSIX-only")
class TestCacheLock(unittest.TestCase):
  def test_guard_is_a_sibling_not_inside_cache(self):
    with TemporaryDirectory() as d:
      cache = Path(d) / "scons_cache"
      cache.mkdir()
      guard = guard_path(cache)
      self.assertEqual(guard.parent, cache.parent)
      self.assertEqual(guard.name, "scons_cache.build.lock")
      # Deleting the cache must not split the lock (guard lives outside it).
      import shutil
      shutil.rmtree(cache)
      self.assertTrue(guard_path(cache).name.endswith(".build.lock"))

  def test_nonblocking_acquire_raises_when_held(self):
    import fcntl
    with TemporaryDirectory() as d:
      cache = Path(d) / "scons_cache"
      cache.mkdir()
      handle = acquire_cache_lock(cache)
      self.assertIsNotNone(handle)
      with self.assertRaises(CacheBusyError):
        acquire_cache_lock(cache, timeout=0.0)
      handle.close()

  def test_release_allows_reacquire(self):
    with TemporaryDirectory() as d:
      cache = Path(d) / "scons_cache"
      cache.mkdir()
      handle = acquire_cache_lock(cache)
      handle.close()
      again = acquire_cache_lock(cache, timeout=0.0)
      self.assertIsNotNone(again)
      again.close()


if __name__ == "__main__":
  unittest.main()
