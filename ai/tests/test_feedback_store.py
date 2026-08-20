"""Tests for message feedback persistence."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))


class _FakeParams:
  pass


class TestFeedbackStore(unittest.TestCase):
  def setUp(self) -> None:
    self.storage: dict[str, str] = {}
    self.params = _FakeParams()

  def _read(self, _params, key, default=None):
    return self.storage.get(key, default)

  def _write(self, _params, key, value):
    self.storage[key] = value if isinstance(value, str) else str(value)

  def test_record_up_and_clear(self):
    from ai.tools.domains.platform import feedback_store as fs

    with patch.object(fs, "read_param", side_effect=self._read), patch.object(fs, "write_param", side_effect=self._write):
      result = fs.record_feedback(self.params, {
        "sessionId": "s_test",
        "messageIndex": 1,
        "rating": "up",
        "messagePreview": "hello",
      })
      self.assertTrue(result["ok"])
      self.assertEqual(result["summary"]["up"], 1)

      listed = fs.list_feedback(self.params, limit=10)
      self.assertEqual(len(listed["entries"]), 1)
      self.assertEqual(listed["entries"][0]["rating"], "up")

      cleared = fs.clear_feedback(self.params, session_id="s_test", message_index=1)
      self.assertTrue(cleared["ok"])
      self.assertEqual(cleared["summary"]["up"], 0)

  def test_record_down_requires_reason(self):
    from ai.tools.domains.platform import feedback_store as fs

    with patch.object(fs, "read_param", side_effect=self._read), patch.object(fs, "write_param", side_effect=self._write):
      bad = fs.record_feedback(self.params, {
        "sessionId": "s_test",
        "messageIndex": 2,
        "rating": "down",
      })
      self.assertFalse(bad["ok"])

      good = fs.record_feedback(self.params, {
        "sessionId": "s_test",
        "messageIndex": 2,
        "rating": "down",
        "reason": "code_error",
        "messagePreview": "bad code",
      })
      self.assertTrue(good["ok"])
      self.assertEqual(good["summary"]["down"], 1)
      self.assertEqual(good["summary"]["by_reason"]["code_error"], 1)

  def test_upsert_same_message(self):
    from ai.tools.domains.platform import feedback_store as fs

    with patch.object(fs, "read_param", side_effect=self._read), patch.object(fs, "write_param", side_effect=self._write):
      fs.record_feedback(self.params, {
        "sessionId": "s_test",
        "messageIndex": 3,
        "rating": "up",
      })
      fs.record_feedback(self.params, {
        "sessionId": "s_test",
        "messageIndex": 3,
        "rating": "down",
        "reason": "unclear",
      })
      listed = fs.list_feedback(self.params, limit=10)
      self.assertEqual(len(listed["entries"]), 1)
      self.assertEqual(listed["entries"][0]["rating"], "down")
      self.assertEqual(listed["summary"]["up"], 0)
      self.assertEqual(listed["summary"]["down"], 1)


if __name__ == "__main__":
  unittest.main()
