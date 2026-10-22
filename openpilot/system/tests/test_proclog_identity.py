"""proclogd must treat a PID as an identity, not a name.

Two defects are locked here. First, the metadata cache was keyed by PID (with a
name fallback), so a short-lived helper's exe/cmdline stayed resident for the
life of the daemon and a reused PID could report the previous process's argv.
Second, the daemon inherits the manager's imported heap across fork; a garbage
collection pass that merely walks it turns shared pages private, so collection
must be frozen before any daemon resource exists.
"""
import ast
import unittest
from pathlib import Path

try:
  from openpilot.system import proclogd
  HAVE_PROCLOGD = True
except ImportError:  # local host without the opendbc checkout
  proclogd = None
  HAVE_PROCLOGD = False


@unittest.skipUnless(HAVE_PROCLOGD, 'proclogd needs cereal and the opendbc checkout')
class TestProcIdentity(unittest.TestCase):
  def setUp(self):
    proclogd._proc_cache.clear()
    proclogd._smaps_cache.clear()
    proclogd._smaps_identity.clear()
    self.pid = proclogd.os.getpid()
    self.start = next(r['starttime'] for r in proclogd._procs() if r['pid'] == self.pid)

  def test_repeated_reads_reuse_one_entry(self):
    first = proclogd._get_proc_extra(self.pid, 'python', self.start)
    second = proclogd._get_proc_extra(self.pid, 'python', self.start)
    self.assertIs(first, second)

  def test_same_name_and_pid_with_a_new_starttime_is_a_new_process(self):
    proclogd._get_proc_extra(self.pid, 'python', self.start)
    replaced = proclogd._get_proc_extra(self.pid, 'python', self.start + 1)
    self.assertEqual(replaced['starttime'], self.start + 1)
    self.assertEqual(proclogd._proc_cache[self.pid]['starttime'], self.start + 1)

  def test_rename_with_the_same_identity_refreshes_the_name(self):
    proclogd._get_proc_extra(self.pid, 'old-name', self.start)
    renamed = proclogd._get_proc_extra(self.pid, 'new-name', self.start)
    self.assertEqual(renamed['name'], 'new-name')

  def test_prune_drops_exited_pids(self):
    proclogd._proc_cache[self.pid] = {'pid': self.pid, 'starttime': self.start, 'name': 'x', 'exe': '', 'cmdline': []}
    proclogd._proc_cache[999999] = {'pid': 999999, 'starttime': 1, 'name': 'gone', 'exe': '', 'cmdline': []}
    proclogd._prune_proc_cache({self.pid: self.start})
    self.assertIn(self.pid, proclogd._proc_cache)
    self.assertNotIn(999999, proclogd._proc_cache)

  def test_prune_drops_a_reused_pid(self):
    proclogd._proc_cache[self.pid] = {'pid': self.pid, 'starttime': self.start, 'name': 'x', 'exe': '', 'cmdline': []}
    proclogd._prune_proc_cache({self.pid: self.start + 5})
    self.assertNotIn(self.pid, proclogd._proc_cache)

  def test_prune_also_bounds_the_smaps_cache(self):
    proclogd._smaps_cache[999999] = {'pss': 1, 'pss_anon': 1, 'pss_shmem': 0}
    proclogd._smaps_identity[999999] = 1
    proclogd._prune_proc_cache({})
    self.assertNotIn(999999, proclogd._smaps_cache)
    self.assertNotIn(999999, proclogd._smaps_identity)

  def test_smaps_cache_is_invalidated_by_a_new_starttime(self):
    calls = []
    original = proclogd._read_smaps

    def counting(pid):
      calls.append(pid)
      return original(pid)

    proclogd._read_smaps = counting
    proclogd._smaps_cycle = 1  # an active cycle: only identity can force a re-read
    try:
      proclogd._get_smaps_cached(self.pid, self.start)
      proclogd._get_smaps_cached(self.pid, self.start)
      self.assertEqual(len(calls), 1)  # identity unchanged: cache hit
      proclogd._get_smaps_cached(self.pid, self.start + 1)
      self.assertEqual(len(calls), 2)  # reused PID: must re-read
    finally:
      proclogd._read_smaps = original
      proclogd._smaps_cycle = 0


@unittest.skipUnless(HAVE_PROCLOGD, 'proclogd needs cereal and the opendbc checkout')
class TestCollectionIsFrozenAtStartup(unittest.TestCase):
  def test_main_freezes_gc_before_creating_daemon_resources(self):
    source = Path(proclogd.__file__).read_text()
    main = next(n for n in ast.parse(source).body
                if isinstance(n, ast.FunctionDef) and n.name == 'main')
    body = ast.unparse(main)
    self.assertIn('gc.freeze()', body)
    self.assertLess(body.index('gc.freeze()'), body.index('PubMaster'))


if __name__ == '__main__':
  unittest.main()
