import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from openpilot.cereal import log
from openpilot.system import proclog_smaps as smaps


def approx(expected, rel=1e-6):
  """pytest.approx replacement supporting scalars and lists."""
  if isinstance(expected, (list, tuple)):
    return [_ApproxScalar(e, rel) for e in expected]
  return _ApproxScalar(expected, rel)


class _ApproxScalar:
  def __init__(self, expected, rel):
    self.expected = expected
    self.rel = rel

  def __eq__(self, actual):
    return abs(actual - self.expected) <= abs(self.expected) * self.rel

  def __repr__(self):
    return f'approx({self.expected})'


class _Patches:
  """monkeypatch-compatible save/restore context."""

  def __init__(self):
    self._saved = []

  def setattr(self, obj, name, value, raising=True):
    had = hasattr(obj, name) if raising else True
    old = getattr(obj, name, None)
    self._saved.append(('attr', obj, name, had, old))
    setattr(obj, name, value)

  def setitem(self, mapping, key, value):
    had = key in mapping
    old = mapping.get(key)
    self._saved.append(('item', mapping, key, had, old))
    mapping[key] = value

  def restore(self):
    for kind, obj, key, had, old in reversed(self._saved):
      if kind == 'item':
        if had:
          obj[key] = old
        else:
          del obj[key]
      else:
        if had:
          setattr(obj, key, old)
        else:
          delattr(obj, key)
    self._saved.clear()


class SmapsTestBase(unittest.TestCase):
  def setUp(self):
    tmp_obj = tempfile.TemporaryDirectory()
    self.addCleanup(tmp_obj.cleanup)
    self.tmp = Path(tmp_obj.name)
    self.patches = _Patches()
    self.addCleanup(self.patches.restore)
    self.clock = SimpleNamespace(now=10.0, cpu=0.0)
    self.patches.setattr(smaps.time, 'monotonic', lambda: self.clock.now)
    self.patches.setattr(smaps.time, 'thread_time', lambda: self.clock.cpu)

  def make_process(self, pid, start=123, data=b'Pss: 10 kB\nPss_Anon: 3 kB\nPss_Shmem: 2 kB\n'):
    path = self.tmp / str(pid)
    path.mkdir(exist_ok=True)
    fields = ['0'] * 50
    fields[0], fields[19] = 'S', str(start)
    (path / 'stat').write_text(f'{pid} (name with ) brackets) ' + ' '.join(fields))
    (path / 'smaps').write_bytes(data)

  def advance(self, sampler):
    self.clock.now = max(self.clock.now, sampler.next_step)
    sampler.step()

  def proclog_module(self):
    """Import the real builder with only Windows-incompatible infrastructure stubbed."""
    import os
    self.patches.setattr(os, 'sysconf', lambda key: 4096 if key == 'SC_PAGE_SIZE' else 100, raising=False)
    self.patches.setattr(os, 'sysconf_names', {'SC_CLK_TCK': 'SC_CLK_TCK', 'SC_PAGE_SIZE': 'SC_PAGE_SIZE'}, raising=False)
    self.patches.setitem(sys.modules, 'openpilot.cereal.messaging', SimpleNamespace())
    self.patches.setitem(sys.modules, 'openpilot.common.swaglog', SimpleNamespace(cloudlog=SimpleNamespace(exception=lambda *_: None)))
    spec = importlib.util.spec_from_file_location('_test_proclogd', Path(__file__).parents[1] / 'proclogd.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # main() must never freeze the test runner's heap.
    self.patches.setattr(module, 'gc', SimpleNamespace(freeze=lambda: None))
    return module


class TestSmapsSampler(SmapsTestBase):
  def test_chunk_boundaries_and_no_partial_publication(self):
    self.patches.setattr(smaps, 'READ_BYTES', 16)
    self.make_process(1, data=b'Pss: 10 kB\nPss_Anon: 3 kB\nPss_Shmem: 2 kB\nPss: 4 kB')
    sampler = smaps.SmapsSampler(self.tmp)
    sampler.update({1: 123})
    sampler.step()
    self.assertEqual(sampler.file.tell(), 16)
    self.assertEqual(sampler.get(1, 123, self.clock.now).mono_time, 0)
    for _ in range(10):
      if sampler.active is None:
        break
      self.advance(sampler)
    self.assertEqual(sampler.get(1, 123, self.clock.now), smaps.SmapsSample(14*1024, 3*1024, 2*1024, 10.0))
    self.assertIsNone(sampler.file)

  def test_many_processes_are_not_swept_in_one_step(self):
    for pid in range(1, 46):
      self.make_process(pid)
    sampler = smaps.SmapsSampler(self.tmp)
    sampler.update(dict.fromkeys(range(1, 46), 123))
    sampler.step()
    self.assertEqual(sampler.active, (1, 123))
    self.assertFalse(sampler.cache)
    sampler.step()  # same time: no second read or process
    self.assertFalse(sampler.cache)
    self.advance(sampler)  # EOF completes only pid1
    self.assertEqual(list(sampler.cache), [1])
    for _ in range(88):
      self.advance(sampler)
    self.assertEqual(set(sampler.cache), set(range(1, 46)))
    self.assertEqual(len({sample.mono_time for sample in sampler.cache.values()}), 45)
    self.assertGreaterEqual(self.clock.now, 10.0 + 89 * smaps.MIN_PAUSE_SECONDS - 1e-9)

  def test_refresh_no_catchup_and_expiry(self):
    self.make_process(1)
    sampler = smaps.SmapsSampler(self.tmp)
    sampler.update({1: 123})
    sampler.step()
    self.advance(sampler)
    sample = sampler.get(1, 123, self.clock.now)
    self.clock.now += 30
    sampler.step()
    self.assertIsNone(sampler.active)
    self.clock.now += 1000
    sampler.step()
    self.assertEqual(sampler.active, (1, 123))
    self.assertEqual(sampler.get(1, 123, self.clock.now).mono_time, 0)  # stale cache is not reported
    self.assertEqual(sampler.cache[1], sample)  # replace only on completed scan
    sampler.close()

  def test_cpu_duty_pause_and_slow_read_do_not_catch_up(self):
    self.make_process(1)
    sampler = smaps.SmapsSampler(self.tmp)
    sampler.update({1: 123})
    original = sampler._parse

    def costly_parse(*args, **kwargs):
      self.clock.cpu += .02
      self.clock.now += .3
      original(*args, **kwargs)

    self.patches.setattr(sampler, '_parse', costly_parse)
    sampler.step()
    self.assertAlmostEqual(sampler.next_step, 10.3 + .02 * 19, delta=abs(10.3 + .02 * 19) * 1e-6)
    pos = sampler.file.tell()
    self.clock.now += .1
    sampler.step()
    self.assertEqual(sampler.file.tell(), pos)
    sampler.close()

  def test_pid_reuse_never_inherits_pss(self):
    for stage in ('before_open', 'during_scan', 'after_cache'):
      with self.subTest(stage=stage):
        self.make_process(1)
        sampler = smaps.SmapsSampler(self.tmp)
        sampler.update({1: 123})
        if stage != 'before_open':
          sampler.step()
        if stage == 'after_cache':
          self.advance(sampler)
          self.assertTrue(sampler.cache[1].pss)
        self.make_process(1, start=456)
        if stage == 'during_scan':
          self.advance(sampler)  # post-read identity check, without another stat snapshot
          self.assertFalse(sampler.cache)
        elif stage == 'before_open':
          sampler.step()
          self.assertIsNone(sampler.file)
        sampler.update({1: 456})
        self.assertEqual(sampler.get(1, 123, self.clock.now).mono_time, 0)
        self.assertEqual(sampler.get(1, 456, self.clock.now).mono_time, 0)
        self.assertIsNone(sampler.file)

  def test_exit_and_small_process_remove_cache_and_close_reader(self):
    self.make_process(1)
    sampler = smaps.SmapsSampler(self.tmp)
    sampler.update({1: 123})
    sampler.step()
    file = sampler.file
    sampler.update({})
    self.assertTrue(file.closed)
    self.assertIsNone(sampler.active)
    self.assertFalse(sampler.due and sampler.cache)

  def test_bad_scan_discards_partial_results(self):
    for data, label in [(b'Pss: bad kB\n', 'invalid_number'), (b'Pss:\n', 'missing_amount'),
                        (b'x' * (smaps.READ_BYTES * 3), 'oversized_line')]:
      with self.subTest(stage=label):
        self.make_process(1, data=data)
        sampler = smaps.SmapsSampler(self.tmp)
        sampler.update({1: 123})
        sampler.step()
        self.advance(sampler)
        self.assertIsNone(sampler.file)
        self.assertFalse(sampler.cache)

  def test_missing_file_is_nonfatal(self):
    self.make_process(1)
    (self.tmp / '1' / 'smaps').unlink()
    sampler = smaps.SmapsSampler(self.tmp)
    sampler.update({1: 123})
    sampler.step()
    self.assertIsNone(sampler.file)
    self.assertGreater(sampler.due[1], self.clock.now)

  def test_rollup_preserves_anonymous_and_shared_pss(self):
    self.make_process(1, data=b'Pss: 99 kB\n')
    (self.tmp / '1' / 'smaps_rollup').write_bytes(b'Pss: 20 kB\nPss_Anon: 8 kB\nPss_Shmem: 7 kB\n')
    sampler = smaps.SmapsSampler(self.tmp)
    sampler.update({1: 123})
    sampler.step()
    self.advance(sampler)
    self.assertEqual(sampler.get(1, 123, self.clock.now), smaps.SmapsSample(20*1024, 8*1024, 7*1024, 10.0))

  def test_incomplete_scan_expires_and_other_processes_progress(self):
    self.make_process(1)
    self.make_process(2)
    sampler = smaps.SmapsSampler(self.tmp)
    sampler.update({1: 123, 2: 123})
    sampler.step()
    self.clock.now += smaps.MAX_AGE_SECONDS + 1
    sampler.step()
    self.assertIsNone(sampler.file) and self.assertFalse(sampler.cache)
    self.advance(sampler)
    self.assertEqual(sampler.active, (2, 123))
    self.advance(sampler)
    self.assertEqual(sampler.cache[2].pss, 10 * 1024)


@unittest.skipUnless(sys.platform == 'linux', 'requires real Linux procfs')
class TestLinuxProcfs(SmapsTestBase):
  def test_linux_procfs_scan_completes(self):
    import os
    sampler = smaps.SmapsSampler()
    pid = os.getpid()
    identity = sampler._starttime(pid)
    sampler.update({pid: identity})
    try:
      for _ in range(2000):
        self.advance(sampler)
        if pid in sampler.cache:
          break
      sample = sampler.get(pid, identity, self.clock.now)
      self.assertGreater(sample.pss, 0)
      self.assertGreaterEqual(sample.pss, sample.pss_anon + sample.pss_shmem)
      self.assertLessEqual(self.clock.now - sample.mono_time, smaps.MAX_AGE_SECONDS)
    finally:
      sampler.close()


class TestProclogPublication(SmapsTestBase):
  def _stat(self, pid=1, starttime=123):
    return {'pid': pid, 'name': 'test' if pid == 1 else 'helper', 'state': 'S', 'ppid': 0, 'utime': 100, 'stime': 200,
            'cutime': 0, 'cstime': 0, 'priority': 20, 'nice': 0, 'num_threads': 1, 'starttime': starttime,
            'vms': 10000000, 'rss': 2000, 'processor': 4}

  def test_proclog_publication_reads_cache_without_smaps_io(self):
    module = self.proclog_module()
    self.patches.setattr(module, '_procs', lambda: [self._stat()])
    self.patches.setattr(module, '_get_proc_extra', lambda *_: {'exe': '', 'cmdline': []})
    self.patches.setattr(module, '_cpu_times', list)
    self.patches.setattr(module, '_mem_info', lambda: dict.fromkeys(
      ['MemTotal:', 'MemFree:', 'MemAvailable:', 'Buffers:', 'Cached:', 'Active:', 'Inactive:', 'Shmem:'], 0))
    sampler = smaps.SmapsSampler(self.tmp)
    sampler.update({1: 123})
    sampler.cache[1] = smaps.SmapsSample(1024, 512, 256, 9.0)

    def fail_step():
      self.fail('publication must not scan')

    self.patches.setattr(sampler, 'step', fail_step)
    event = log.Event.new_message()
    event.init('procLog')
    module.build_proc_log_message(event, sampler)
    proc = event.procLog.procs[0]
    self.assertEqual((proc.cpuUser, proc.cpuSystem, proc.memRss), (1, 2, 2000*4096))
    self.assertEqual((proc.memPss, proc.memPssAnon, proc.memPssShmem, proc.memPssMonoTime), (1024, 512, 256, 9_000_000_000))
    self.clock.now = 130
    module.build_proc_log_message(log.Event.new_message(procLog={}), sampler)
    self.assertEqual(sampler.get(1, 123, self.clock.now).mono_time, 0)

  def test_main_keeps_lightweight_cadence_and_never_replays_missed_slots(self):
    module = self.proclog_module()
    published = []
    sampler = smaps.SmapsSampler(self.tmp)
    original_step = sampler.step
    stalled = [False]

    def step():
      if self.clock.now >= 12 and not stalled[0]:
        self.clock.now += 5  # an individual slow kernel read cannot be preempted
        stalled[0] = True
      original_step()

    class Finished(Exception):
      pass

    def publish(*_):
      published.append(self.clock.now)
      if len(published) == 5:
        raise Finished

    self.patches.setattr(sampler, 'step', step)
    self.patches.setattr(module, 'SmapsSampler', lambda: sampler)
    self.patches.setattr(module, 'build_proc_log_message', lambda *_: None)
    self.patches.setattr(module, 'messaging', SimpleNamespace(
      PubMaster=lambda *_: SimpleNamespace(send=publish), new_message=lambda *_a, **_kw: None))
    self.patches.setattr(module.time, 'sleep', lambda duration: setattr(self.clock, 'now', self.clock.now + duration))
    with self.assertRaises(Finished):
      module.main()
    self.assertEqual(published, approx([10, 12, 17, 19, 21]))
    self.assertIsNone(sampler.file)

  def test_metadata_cache_releases_exited_processes(self):
    import io
    module = self.proclog_module()
    self.patches.setattr(module.os, 'readlink', lambda path: '/bin/helper')
    self.patches.setattr(sys.modules['builtins'], 'open', lambda *_a, **_kw: io.BytesIO(b'helper\0argument\0'))
    persistent = module._get_proc_extra(1, 'helper', 100)
    for generation in range(500):
      pid = generation + 2
      module._prune_proc_cache({1: 100, pid: generation + 200})
      module._get_proc_extra(pid, 'helper', generation + 200)
      self.assertEqual(len(module._proc_cache), 2)
      self.assertIs(module._proc_cache[1], persistent)
    module._prune_proc_cache({1: 100})
    self.assertEqual(module._proc_cache, {1: persistent})

  def test_main_freezes_inherited_heap_before_runtime_resources(self):
    module = self.proclog_module()
    events = []

    class Finished(Exception):
      pass

    def pubmaster(*_):
      events.append('pubmaster')
      raise Finished

    self.patches.setattr(module, 'gc', SimpleNamespace(freeze=lambda: events.append('freeze')))
    self.patches.setattr(module, 'messaging', SimpleNamespace(PubMaster=pubmaster))

    def unexpected_sampler():
      self.fail('unexpected sampler creation')

    self.patches.setattr(module, 'SmapsSampler', unexpected_sampler)
    with self.assertRaises(Finished):
      module.main()
    self.assertEqual(events, ['freeze', 'pubmaster'])

  def test_metadata_pid_reuse_with_same_name_refreshes_command(self):
    import io
    module = self.proclog_module()
    command = [b'helper\0old\0']
    self.patches.setattr(module.os, 'readlink', lambda path: '/bin/helper')
    self.patches.setattr(sys.modules['builtins'], 'open', lambda *_a, **_kw: io.BytesIO(command[0]))
    old = module._get_proc_extra(10, 'helper', 100)
    command[0] = b'helper\0new\0'
    new = module._get_proc_extra(10, 'helper', 200)
    self.assertEqual(old['cmdline'], ['helper', 'old'])
    self.assertEqual(new['cmdline'], ['helper', 'new'])
    module._prune_proc_cache({10: 300})
    self.assertFalse(module._proc_cache)

  def test_publication_prunes_metadata_and_refreshes_reused_pid(self):
    import io
    module = self.proclog_module()
    stat = self._stat()
    stat['name'] = 'helper'
    current = [stat]
    command = [b'helper\0old\0']
    self.patches.setattr(module, '_procs', lambda: current)
    self.patches.setattr(module.os, 'readlink', lambda _: '/bin/helper')
    self.patches.setattr(sys.modules['builtins'], 'open', lambda *_a, **_kw: io.BytesIO(command[0]))
    self.patches.setattr(module, '_cpu_times', list)
    self.patches.setattr(module, '_mem_info', lambda: dict.fromkeys(
      ['MemTotal:', 'MemFree:', 'MemAvailable:', 'Buffers:', 'Cached:', 'Active:', 'Inactive:', 'Shmem:'], 0))
    sampler = SimpleNamespace(update=lambda _: None, get=lambda *_: smaps.SmapsSample())

    def publish():
      event = log.Event.new_message(procLog={})
      module.build_proc_log_message(event, sampler)
      return event

    self.assertEqual(list(publish().procLog.procs[0].cmdline), ['helper', 'old'])
    stat['starttime'] += 1
    command[0] = b'helper\0new\0'
    self.assertEqual(list(publish().procLog.procs[0].cmdline), ['helper', 'new'])
    for pid in range(2, 102):
      current[:] = [stat, {**stat, 'pid': pid}]
      event = publish()
      self.assertEqual([p.pid for p in event.procLog.procs], [1, pid])
      self.assertEqual(len(module._proc_cache), 2)
    current.clear()
    self.assertEqual(len(publish().procLog.procs), 0)
    self.assertFalse(module._proc_cache)


@unittest.skipUnless(sys.platform == 'linux', 'requires fork without freezing the test runner')
class TestForkCollectible(SmapsTestBase):
  def test_main_keeps_new_cycles_collectible(self):
    import gc
    import json
    import os
    import select
    import signal
    import weakref

    module = self.proclog_module()
    parent_frozen = gc.get_freeze_count()
    parent_enabled = gc.isenabled()
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
      os.close(read_fd)
      signal.alarm(10)
      try:
        module.gc = gc

        class Finished(Exception):
          pass

        def verify(*_):
          class Node:
            pass
          node = Node()
          node.cycle = node
          ref = weakref.ref(node)
          del node
          gc.collect()
          result = [gc.get_freeze_count() > parent_frozen, ref() is None, gc.isenabled() == parent_enabled]
          os.write(write_fd, json.dumps(result).encode())
          raise Finished

        module.messaging = SimpleNamespace(PubMaster=verify)
        try:
          module.main()
        except Finished:
          pass
        os._exit(0)
      except BaseException:
        os._exit(1)
    os.close(write_fd)
    try:
      self.assertTrue(select.select([read_fd], [], [], 15)[0], 'child did not complete')
      self.assertEqual(json.loads(os.read(read_fd, 4096)), [True, True, True])
    finally:
      os.close(read_fd)
      _, status = os.waitpid(pid, 0)
    self.assertEqual(os.waitstatus_to_exitcode(status), 0)
    self.assertEqual(gc.get_freeze_count(), parent_frozen)
    self.assertEqual(gc.isenabled(), parent_enabled)


if __name__ == '__main__':
  unittest.main()
