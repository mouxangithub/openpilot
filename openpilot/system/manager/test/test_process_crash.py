"""Crash diagnostics: no live vehicle, external uploads or native device imports.
Ported from carrot (unittest conversion)."""
import ast
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import unittest
from types import SimpleNamespace
from unittest import mock

from openpilot.system.manager import process_crash as crash


def event(index=1):
  return {'id': f'1-2-{index}', 'name': 'carrot_man', 'pid': 2, 'exitcode': -int(signal.SIGABRT),
          'git_branch': 'test', 'git_commit': 'test-commit', 'dongle_id': 'test-device'}


def collector(root, **kwargs):
  return crash.CrashCollector(root=root, capture=lambda _: 'original traceback',
                              payload=lambda _: {'tmux_why': 'process_crash'}, **kwargs)


def wait_until(predicate, timeout=5):
  deadline = time.monotonic() + timeout
  while time.monotonic() < deadline:
    if predicate():
      return
    time.sleep(0.01)
  assert predicate()


class TestCrashSender(unittest.TestCase):
  def test_sender_bounded_retry_and_no_success_exit_report(self):
    delivered = []
    state = {'available': False}

    class Socket:
      def __enter__(self):
        return self

      def __exit__(self, *_):
        pass

      def setblocking(self, value):
        assert value is False

      def sendto(self, data, address):
        assert address == 'test-socket'
        if not state['available']:
          raise BlockingIOError()
        delivered.append(json.loads(data))

    with mock.patch.object(crash.socket, 'socket', lambda *_: Socket()), \
         mock.patch.object(crash.socket, 'AF_UNIX', 1, create=True):
      sender = crash.CrashSender('test-socket')
      for code in (None, 0):
        sender.report('worker', 1, code)
      self.assertEqual(list(sender.pending), [])
      for pid in range(1, 50):
        sender.report('worker', pid, -6)
      self.assertEqual(len(sender.pending), crash.MAX_PENDING)
      state['available'] = True
      sender.flush()
      self.assertEqual(list(sender.pending), [])
    self.assertEqual([e['pid'] for e in delivered], list(range(18, 50)))

  def test_diagnostics_failure_cannot_break_manager(self):
    def fail(*_):
      raise RuntimeError('diagnostics broken')
    with mock.patch.object(crash._sender, 'report', fail), mock.patch.object(crash._sender, 'flush', fail):
      crash.report_process_exit('worker', 1, -6)
      crash.flush_crash_reports()


class CollectorCase(unittest.TestCase):
  def setUp(self):
    self._tmp = tempfile.TemporaryDirectory()
    self.root = Path(self._tmp.name)
    self.addCleanup(self._tmp.cleanup)


class TestCollector(CollectorCase):
  def test_snapshot_bounded_and_exit_metadata_survives_missing_params(self):
    c = collector(self.root)
    c.capture = lambda _: 'x' * (crash.MAX_TEXT + 100)
    c.payload = lambda _: (_ for _ in ()).throw(OSError('params unavailable'))
    for index in range(crash.MAX_REPORTS + 3):
      c.record(event(index))
    reports = sorted(self.root.glob('*.json'))
    self.assertEqual(len(reports), len(list(self.root.glob('*.txt'))), crash.MAX_REPORTS)
    self.assertEqual(len(reports), crash.MAX_REPORTS)
    self.assertFalse((self.root / '1-2-0.json').exists())
    data = json.loads(reports[-1].read_text())
    self.assertEqual(data['event']['signal'], 'SIGABRT')
    self.assertEqual(data['payload']['git_commit'], 'test-commit')
    self.assertEqual(data['payload']['tmux_why'], 'process_crash')
    text = reports[-1].with_suffix('.txt').read_text()
    self.assertTrue(text.startswith('PROCESS_EXIT '))
    self.assertEqual(len(text.split('\n\n', 1)[1]), crash.MAX_TEXT)

  def test_bad_event_rejected(self):
    for field, value in [('id', '../escape'), ('id', '1' * 300), ('name', 'a/b'), ('exitcode', '-6')]:
      with self.subTest(field=field):
        e = event()
        e[field] = value
        with self.assertRaises(ValueError):
          collector(self.root).record(e)
        self.assertEqual(list(self.root.iterdir()), [])

  def test_saved_capture_retry_and_per_destination_ack_survive_restart(self):
    calls = []
    state = {'online': False}

    def upload(target, payload, path):
      calls.append((target, path.read_text()))
      assert payload['tmux_why'] == 'process_crash'
      if target == 'dsm' and not state['online']:
        raise OSError('offline')
      return True

    c = collector(self.root, upload=upload)
    c.record(event())
    original = (self.root / '1-2-1.txt').read_text()
    c.upload_pending(now=0)
    self.assertEqual([x[0] for x in calls], ['dsm', 'carrot_logs'])
    c.capture = lambda _: 'new pane contents'
    c.record(event())  # Duplicate cannot replace evidence or acknowledgements.
    c.upload_pending(now=1)
    self.assertEqual(len(calls), 2)
    state['online'] = True
    restarted = collector(self.root, upload=upload)
    restarted.upload_pending(now=2)
    restarted.upload_pending(now=100)
    self.assertEqual([x[0] for x in calls], ['dsm', 'carrot_logs', 'dsm'])
    self.assertTrue(all(x[1] == original for x in calls))
    self.assertEqual(json.loads((self.root / '1-2-1.json').read_text())['sent'], ['carrot_logs', 'dsm'])

  def test_tmux_capture_failure_still_persists_exit(self):
    def fail(*args, **kwargs):
      assert kwargs['timeout'] == 3
      raise subprocess.TimeoutExpired(args[0], 3)
    c = collector(self.root)
    with mock.patch.object(crash.subprocess, 'run', fail):
      c.capture = crash.capture_tmux
      c.record(event())
    self.assertIn('TimeoutExpired', (self.root / '1-2-1.txt').read_text())
    self.assertEqual(json.loads((self.root / '1-2-1.json').read_text())['event']['exitcode'], -int(signal.SIGABRT))

  def test_launcher_reports_child_exception_and_propagates(self):
    source = Path(crash.__file__).with_name('process.py')
    definition = next(n for n in ast.parse(source.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == 'launcher')

    def fail_import(_):
      raise RuntimeError('original child failure')

    logged = []
    ns = {'enable_fault_handler': lambda: None, 'traceback': traceback,
          'importlib': SimpleNamespace(import_module=fail_import), 'setproctitle': lambda *_: None,
          'messaging': SimpleNamespace(reset_context=lambda: None),
          'cloudlog': SimpleNamespace(bind=lambda **_: None, exception=lambda *a, **k: logged.append(a))}
    exec(compile(ast.Module(body=[definition], type_ignores=[]), str(source), 'exec'), ns)
    with self.assertRaises(RuntimeError):
      ns['launcher']('test_worker', 'worker')
    self.assertTrue(logged)

  @unittest.skipIf(os.name != 'posix', 'device transport requires POSIX Unix datagrams')
  def test_real_socket_captures_while_uploader_is_blocked(self):
    blocked, release = threading.Event(), threading.Event()

    def upload(*_):
      blocked.set()
      release.wait(5)
      return True

    reports = self.root / 'reports'
    c = collector(reports, address=str(self.root / 'socket'), upload=upload).start()
    sender = crash.CrashSender(c.address)
    try:
      sender.report('worker', 101, -6)
      self.assertTrue(blocked.wait(3))
      started = time.monotonic()
      sender.report('worker', 102, -9)
      self.assertLess(time.monotonic() - started, 0.5)
      wait_until(lambda: len(list(reports.glob('*.json'))) == 2)
      data = [json.loads(p.read_text())['event'] for p in reports.glob('*.json')]
      self.assertEqual({e['signal'] for e in data}, {'SIGABRT', 'SIGKILL'})
      self.assertFalse(sender.pending)
      self.assertEqual(os.stat(c.address).st_mode & 0o777, 0o600)
    finally:
      release.set()
      c.close()

  @unittest.skipIf(os.name != 'posix' or not shutil.which('tmux'), 'Linux tmux integration')
  def test_fatal_signal_stack_is_in_real_tmux_snapshot(self):
    # An isolated tmux server runs a disposable Python child, never the vehicle.
    server = f'crash-test-{os.getpid()}'
    prefix = ['tmux', '-L', server]
    real_run = subprocess.run
    code = ('import resource, os; resource.setrlimit(resource.RLIMIT_CORE, (0, 0)); '
            + 'from openpilot.system.manager.process_crash import enable_fault_handler; '
            + 'enable_fault_handler(); os.abort()')
    root = Path(crash.__file__).resolve().parents[3]
    command = f'cd {shlex.quote(str(root))} && {shlex.quote(sys.executable)} -c {shlex.quote(code)}; sleep 15'
    try:
      real_run(prefix + ['new-session', '-d', '-s', 'crash', command], check=True, capture_output=True, timeout=5)

      def isolated_run(cmd, **kwargs):
        assert cmd[0] == 'tmux'
        return real_run(prefix + cmd[1:], **kwargs)

      with mock.patch.object(crash.subprocess, 'run', isolated_run):
        e = event()
        e['pane'] = 'crash:0.0'
        wait_until(lambda: 'Fatal Python error: Aborted' in crash.capture_tmux(e))
        c = collector(self.root)
        c.capture = crash.capture_tmux
        c.record(e)
        text = (self.root / '1-2-1.txt').read_text()
        self.assertIn('SIGABRT', text)
        self.assertIn('Fatal Python error: Aborted', text)
        self.assertIn('File "<string>", line 1', text)
    finally:
      real_run(prefix + ['kill-server'], capture_output=True, timeout=5)

  def test_upload_uses_existing_tmux_destinations_and_snapshot(self):
    import requests
    from openpilot.sunnypilot.carrot import web_upload
    from openpilot.sunnypilot.carrot.server.services import web_settings

    path = self.root / 'crash.txt'
    path.write_text('saved crash snapshot')
    calls = []

    def post(url, **kwargs):
      calls.append(url)
      if url.endswith('/session'):
        assert kwargs['json']['purpose'] == 'tmux'
        return SimpleNamespace(status_code=200, json=lambda: {'ok': True, 'token': 'test-session'})
      assert kwargs['files'][0][1][1].read() == b'saved crash snapshot'
      assert kwargs['data']['tmux_why'] == 'process_crash'
      assert kwargs['timeout'] == 30
      return SimpleNamespace(status_code=200)

    with mock.patch.dict(os.environ, {'CARROT_WEB_UPLOAD_URL': 'https://nas.invalid',
                                      'CARROT_TMUX_WEB_UPLOAD_URL': 'https://logs.invalid/upload'}):
      os.environ.pop('FAKEUPLOAD', None)
      os.environ.pop('CARROT_WEB_UPLOAD_TOKEN', None)
      with mock.patch.object(web_settings, 'read_web_settings', dict), \
           mock.patch.object(requests, 'post', post):
        payload = {'tmux_why': 'process_crash', 'dongle_id': 'test'}
        self.assertTrue(crash.upload_report('dsm', payload, path))
        self.assertTrue(crash.upload_report('carrot_logs', payload, path))
        self.assertEqual(calls, ['https://nas.invalid/api/v1/session', 'https://nas.invalid/api/v1/tmux/upload',
                                 web_upload.carrot_logs_web_target()[0]])


if __name__ == '__main__':
  unittest.main()
