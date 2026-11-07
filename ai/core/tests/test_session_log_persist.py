"""Tests for SessionLog disk persistence."""

import tempfile
import unittest
from pathlib import Path

from ai.core.session.log import EventType, SessionEvent, SessionLog, SurfaceOp


class SessionLogPersistTestCase(unittest.TestCase):
  def test_persists_events_to_jsonl(self):
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / "events.jsonl"
      log = SessionLog("s1", persist_path=path)
      log.append(EventType.USER_MESSAGE, {"content": "hello"}, surface_op=SurfaceOp.APPEND)
      log.append(EventType.ASSISTANT_MESSAGE, {"role": "assistant", "content": "hi"}, surface_op=SurfaceOp.APPEND)
      log.close()

      lines = path.read_text(encoding="utf-8").strip().split("\n")
      # Fresh logs start with a formatVersion header line.
      self.assertGreaterEqual(len(lines), 3)
      self.assertIn("formatVersion", lines[0])
      self.assertIn("user/message", lines[1])
      self.assertIn("assistant/message", lines[2])

  def test_load_persisted_events(self):
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / "events.jsonl"
      log = SessionLog("s1", persist_path=path)
      log.append(EventType.USER_MESSAGE, {"content": "hello"}, surface_op=SurfaceOp.APPEND)
      log.close()

      log2 = SessionLog("s1", persist_path=path, load_persisted=True)
      try:
        self.assertEqual(log2.seq, 1)
        self.assertEqual(log2.events[0].type, EventType.USER_MESSAGE)
        self.assertEqual(log2.derive_messages()[0]["content"], "hello")
      finally:
        log2.close()

  def test_surface_reconstructed_on_load(self):
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / "events.jsonl"
      log = SessionLog("s1", persist_path=path)
      log.append(EventType.USER_MESSAGE, {"content": "a"}, surface_op=SurfaceOp.APPEND)
      log.append(EventType.USER_MESSAGE, {"content": "b"}, surface_op=SurfaceOp.APPEND)
      log.close()

      log2 = SessionLog("s1", persist_path=path, load_persisted=True)
      try:
        self.assertEqual(len(log2.surface), 2)
      finally:
        log2.close()

  def test_seed_after_load(self):
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / "events.jsonl"
      log = SessionLog("s1", persist_path=path)
      log.append(EventType.USER_MESSAGE, {"content": "a"}, surface_op=SurfaceOp.APPEND)
      log.close()

      seed = [SessionEvent(EventType.USER_MESSAGE, seq=0, time=0, data={"content": "seed"}, surface_op=SurfaceOp.APPEND)]
      log2 = SessionLog("s1", seed=seed, persist_path=path, load_persisted=True)
      try:
        self.assertEqual(log2.seq, 2)
      finally:
        log2.close()


if __name__ == "__main__":
  unittest.main()
