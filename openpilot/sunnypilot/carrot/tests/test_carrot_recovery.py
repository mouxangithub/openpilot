"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Tests for the 6999 recovery server's two safety properties.

CarrotPilot's `recovery/server.py` runs always and ships four third-party destinations baked
in. This fork changed exactly two things when porting it, and both are the kind of change that
is easy to undo by accident, so they are pinned here:

1. the server is **opt-in** - it serves an unauthenticated login shell, so it must not come up
   unless `CarrotRecoveryEnabled` says so; and
2. the third-party destinations are **empty by default** - no upload host, no Discord webhook,
   and no boot-time beacon, until one is configured.

The module is standard-library only (plus a guarded fcntl/pty import), so this runs anywhere.
"""
import os
import tempfile
import unittest
from unittest import mock

from openpilot.sunnypilot.carrot.recovery import server as rec


class TestOptInGate(unittest.TestCase):
  def setUp(self):
    self._dir = tempfile.mkdtemp()
    self._saved = rec.PARAMS_DIR
    rec.PARAMS_DIR = self._dir
    os.makedirs(os.path.join(self._dir, "d"), exist_ok=True)

  def tearDown(self):
    rec.PARAMS_DIR = self._saved

  def _write(self, value):
    with open(os.path.join(self._dir, "d", "CarrotRecoveryEnabled"), "w", encoding="utf-8") as fh:
      fh.write(value)

  def test_absent_param_means_disabled(self):
    # the default on every device that has never touched it
    self.assertFalse(rec._recovery_enabled())

  def test_false_values_mean_disabled(self):
    for value in ("0", "", "false", "off", "no", "garbage"):
      with self.subTest(value=value):
        self._write(value)
        self.assertFalse(rec._recovery_enabled())

  def test_truthy_values_mean_enabled(self):
    for value in ("1", "true", "TRUE", "yes", "on", " 1 "):
      with self.subTest(value=value):
        self._write(value)
        self.assertTrue(rec._recovery_enabled())

  def test_main_exits_without_serving_when_disabled(self):
    # The gate is checked before the socket is bound, so a disabled device never opens 6999.
    with mock.patch.object(rec, "ThreadingHTTPServer") as httpd, \
         mock.patch("sys.argv", ["carrot_recovery", "--port", "6999"]):
      rec.main()
    httpd.assert_not_called()


class TestNoBakedInEgress(unittest.TestCase):
  """Every third-party destination must be unset out of the box."""

  def test_upload_hosts_are_empty(self):
    self.assertEqual(rec.DEFAULT_WEB_UPLOAD_URL, "")
    self.assertEqual(rec.DEFAULT_TMUX_WEB_UPLOAD_URL, "")

  def test_obfuscated_webhooks_are_empty(self):
    self.assertEqual(rec.EXCEPTION_DISCORD_WEBHOOK_OBFUSCATED, "")
    self.assertEqual(rec._SUPPORT_OBFUSCATED_WEBHOOK_URL, "")
    self.assertEqual(rec.CWP_REPORT_URL_BYTES, ())

  def test_web_upload_base_url_refuses_when_unset(self):
    with mock.patch.dict(os.environ, {"CARROT_WEB_UPLOAD_URL": ""}, clear=False), \
         mock.patch.object(rec, "CARROT_DATA_DIR", tempfile.mkdtemp()):
      with self.assertRaises(ValueError):
        rec._web_upload_base_url()

  def test_carrot_logs_url_refuses_when_unset(self):
    with mock.patch.dict(os.environ, {"CARROT_TMUX_WEB_UPLOAD_URL": ""}, clear=False):
      with self.assertRaises(ValueError):
        rec._carrot_logs_url()

  def test_support_webhook_resolves_to_nothing(self):
    for key in ("CARROT_SUPPORT_DISCORD_WEBHOOK_URL", "CARROT_DISCORD_WEBHOOK_URL", "DISCORD_WEBHOOK_URL"):
      os.environ.pop(key, None)
    self.assertEqual(rec._support_webhook_url(), "")

  def test_exception_webhook_resolves_to_nothing(self):
    os.environ.pop("CARROT_EXCEPTION_DISCORD_WEBHOOK_DISABLE", None)
    for key in ("CARROT_EXCEPTION_DISCORD_WEBHOOK_URL", "CARROT_DISCORD_WEBHOOK_URL", "DISCORD_WEBHOOK_URL"):
      os.environ.pop(key, None)
    self.assertEqual(rec._exception_webhook_url(), "")

  def test_cwp_request_reports_not_configured(self):
    os.environ.pop("CWEB_PUSH_REPORT_URL", None)
    result = rec._cwp_request("/recovery/status", {"deviceId": "x"})
    self.assertFalse(result["ok"])
    self.assertFalse(result["configured"])

  def test_sending_tmux_logs_fails_cleanly_with_no_destination(self):
    # No destination is configured, so the send must report failure rather than reaching out.
    with mock.patch.dict(os.environ, {"CARROT_WEB_UPLOAD_URL": "", "CARROT_TMUX_WEB_UPLOAD_URL": ""}, clear=False), \
         mock.patch.object(rec, "CARROT_DATA_DIR", tempfile.mkdtemp()), \
         mock.patch.object(rec.urllib.request, "urlopen") as urlopen:
      result = rec._send_tmux_destinations("test")
    urlopen.assert_not_called()
    self.assertFalse(result["ok"])


if __name__ == "__main__":
  unittest.main()
