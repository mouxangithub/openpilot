#!/usr/bin/env python3
"""Regression tests for carrot_navi import when aiohttp is missing."""
from __future__ import annotations

import os
import subprocess
import sys
import unittest


class TestCarrotNaviWithoutAiohttp(unittest.TestCase):
  """Ensure carrot_navi can be imported and queried when aiohttp is absent."""

  def _run_in_subprocess(self, code: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = "E:/sp/openpilot"
    # Make sure we use the same interpreter as the test runner.
    python = sys.executable
    return subprocess.run(
      [python, "-c", code],
      env=env,
      capture_output=True,
      text=True,
      timeout=30,
    )

  def test_module_imports_without_aiohttp(self) -> None:
    """Blocking aiohttp must not prevent importing carrot_navi."""
    code = """
import sys
sys.modules['aiohttp'] = None
# Force a fresh import of carrot_navi and its submodules.
for name in list(sys.modules):
  if 'carrot_navi' in name:
    del sys.modules[name]

from openpilot.sunnypilot.carrot import carrot_navi as cn
print('available=', cn._AIOHTTP_AVAILABLE)
print('app=', cn.web.Application)
print('appkey=', cn.web.AppKey('receiver', object))
print('msg=', cn.WSMsgType.TEXT)
"""
    result = self._run_in_subprocess(code)
    self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
    self.assertIn("available= False", result.stdout)
    self.assertIn("app= typing.Any", result.stdout)
    self.assertIn("appkey= receiver", result.stdout)
    self.assertIn("msg= TEXT", result.stdout)

  def test_main_idles_without_aiohttp(self) -> None:
    """main() must enter an idle loop instead of crashing or returning."""
    code = """
import sys, threading, time
sys.modules['aiohttp'] = None
for name in list(sys.modules):
  if 'carrot_navi' in name:
    del sys.modules[name]

from openpilot.sunnypilot.carrot import carrot_navi as cn

def mock_main():
  sys.argv = ['carrot_navi', '--no-cereal', '--no-beacon']
  try:
    cn.main()
  except SystemExit:
    pass

stop = threading.Event()
t = threading.Thread(target=mock_main, daemon=True)
t.start()
# main() should sleep for 3600s; wait a short time to confirm it did not return.
stop.wait(2)
print('alive=', t.is_alive())
"""
    result = self._run_in_subprocess(code)
    self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
    self.assertIn("alive= True", result.stdout)


if __name__ == "__main__":
  unittest.main()
