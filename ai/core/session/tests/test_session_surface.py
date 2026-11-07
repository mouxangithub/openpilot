"""U1 compatibility-incremental tests: format version/header + strict surface seam.

Verifies that:
 - new logs write (and reload) a format-version header without breaking legacy logs;
 - legacy JSONL (no header) still loads unchanged;
 - the strict surface fold rejects illegal events (seq discontinuity, missing surface
   marker, unbounded REPLACE, tool/result REPLACE changing tool_call_id) while the
   default (non-strict) path preserves the legacy append-only behavior.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ai.core.session.log import (
  SESSION_FORMAT_VERSION_STR,
  SESSION_HEADER_KEY,
  EventType,
  SessionEvent,
  SessionHeader,
  SessionLog,
  SurfaceOp,
  SurfaceValidationError,
  fold_surface,
)


def _persist_lines(lines: list[str]) -> Path:
  tmp = Path(tempfile.mkstemp(suffix=".jsonl")[1])
  with open(tmp, "w", encoding="utf-8") as f:
    for line in lines:
      f.write(line + "\n")
  return tmp


class FormatVersionTest(unittest.TestCase):
  def test_fresh_log_writes_version_header(self) -> None:
    tmp = Path(tempfile.mkstemp(suffix=".jsonl")[1])
    log = SessionLog("s1", persist_path=tmp)
    try:
      raw = json.loads(tmp.read_text(encoding="utf-8").splitlines()[0])
      self.assertEqual(raw[SESSION_HEADER_KEY], SESSION_FORMAT_VERSION_STR)
      self.assertEqual(log.version, SESSION_FORMAT_VERSION_STR)
    finally:
      log.close()
      try:
        tmp.unlink(missing_ok=True)
      except OSError:
        pass

  def test_reload_reads_header_version_and_meta(self) -> None:
    tmp = Path(tempfile.mkstemp(suffix=".jsonl")[1])
    header = SessionHeader(cwd="/tmp/ws", parent_session="parent-1", origin="user")
    log = SessionLog("s2", persist_path=tmp, header=header)
    log.append(EventType.USER_MESSAGE, {"role": "user", "content": "hi"}, surface_op=SurfaceOp.APPEND)
    log.close()

    try:
      log2 = SessionLog("s2", persist_path=tmp, load_persisted=True)
      try:
        self.assertEqual(log2.version, SESSION_FORMAT_VERSION_STR)
        self.assertEqual(len(log2.events), 1)
        self.assertIsNotNone(header := log2.session_header())
        self.assertEqual(header.cwd, "/tmp/ws")
        self.assertEqual(header.parent_session, "parent-1")
        self.assertEqual(header.origin, "user")
      finally:
        log2.close()
    finally:
      try:
        tmp.unlink(missing_ok=True)
      except OSError:
        pass

  def test_legacy_log_without_header_still_loads(self) -> None:
    tmp = _persist_lines([
      json.dumps({"type": "user/message", "data": {"role": "user", "content": "old"}, "surfaceOp": "append"}),
      json.dumps({"type": "assistant/message", "data": {"content": "old reply"}, "surfaceOp": "append"}),
    ])
    try:
      log = SessionLog("s-legacy", persist_path=tmp, load_persisted=True)
      try:
        # Legacy format has no version header -> version stays None, events intact.
        self.assertIsNone(log.version, "legacy log must load with version=None")
        self.assertIsNone(log.session_header())
        self.assertEqual(len(log.events), 2)
        self.assertEqual(log.events[1].type, EventType.ASSISTANT_MESSAGE)
      finally:
        log.close()
    finally:
      try:
        tmp.unlink(missing_ok=True)
      except OSError:
        pass

  def test_legacy_log_blank_bad_lines_skipped_not_abort(self) -> None:
    tmp = _persist_lines([
      "not-json",
      json.dumps({"weird": "line", "no": "type"}),
      json.dumps({"type": "user/message", "data": {"content": "ok"}, "surfaceOp": "append"}),
    ])
    try:
      log = SessionLog("s-skip", persist_path=tmp, load_persisted=True)
      try:
        self.assertEqual(len(log.events), 1, "bad lines skipped, good event preserved")
      finally:
        log.close()
    finally:
      try:
        tmp.unlink(missing_ok=True)
      except OSError:
        pass


class SessionHeaderTest(unittest.TestCase):
  def test_round_trip_omits_none_fields(self) -> None:
    header = SessionHeader(cwd="/x", seed_length=3, delegation_depth=1)
    as_dict = header.to_dict()
    self.assertEqual(as_dict["cwd"], "/x")
    self.assertEqual(as_dict["seedLength"], 3)
    self.assertNotIn("parentSession", as_dict)
    self.assertNotIn("origin", as_dict)
    back = SessionHeader.from_dict(as_dict)
    self.assertEqual(back, header)


class StrictSurfaceTest(unittest.TestCase):
  def test_message_event_requires_surface_marker(self) -> None:
    log = SessionLog("s-strict", strict=True)
    with self.assertRaises(SurfaceValidationError):
      log.append(EventType.USER_MESSAGE, {"role": "user", "content": "hi"}, surface_op=None)

  def test_seq_discontinuity_rejected(self) -> None:
    events = [
      SessionEvent(EventType.USER_MESSAGE, 0, 0, {}, surface_op=SurfaceOp.APPEND),
      SessionEvent(EventType.ASSISTANT_MESSAGE, 2, 0, {}, surface_op=SurfaceOp.APPEND),  # gap
    ]
    with self.assertRaises(SurfaceValidationError):
      fold_surface(events, strict=True)

  def test_replace_requires_provenance(self) -> None:
    show = SessionEvent(EventType.TOOL_RESULT, 0, 0, {"tool_call_id": "t1", "content": "a"}, surface_op=SurfaceOp.APPEND)
    bad = SessionEvent(EventType.TOOL_RESULT, 1, 0, {"tool_call_id": "t1", "content": "b"}, surface_op=SurfaceOp.REPLACE, source_seqs=None)
    with self.assertRaises(SurfaceValidationError):
      fold_surface([show, bad], strict=True)

  def test_tool_result_replace_changing_id_rejected(self) -> None:
    show = SessionEvent(EventType.TOOL_RESULT, 0, 0, {"tool_call_id": "t1", "content": "a"}, surface_op=SurfaceOp.APPEND)
    bad = SessionEvent(
      EventType.TOOL_RESULT, 1, 0,
      {"tool_call_id": "t2", "content": "b"},
      surface_op=SurfaceOp.REPLACE,
      source_seqs=(0,),
    )
    with self.assertRaises(SurfaceValidationError):
      fold_surface([show, bad], strict=True)

  def test_valid_strict_surface_folds_and_replaces_by_provenance(self) -> None:
    a1 = SessionEvent(EventType.TOOL_RESULT, 0, 0, {"tool_call_id": "t1", "content": "a"}, surface_op=SurfaceOp.APPEND)
    a2 = SessionEvent(EventType.TOOL_RESULT, 1, 0, {"tool_call_id": "t2", "content": "b"}, surface_op=SurfaceOp.APPEND)
    repl = SessionEvent(EventType.TOOL_RESULT, 2, 0, {"tool_call_id": "t2", "content": "b2"}, surface_op=SurfaceOp.REPLACE, source_seqs=(1,))
    folded = fold_surface([a1, a2, repl], strict=True)
    self.assertEqual(len(folded), 2)
    self.assertEqual(folded[1].data["content"], "b2")
    self.assertEqual(folded[1].seq, 2)

  def test_non_strict_preserves_legacy_behavior(self) -> None:
    # Non-strict (default) must not raise even on "illegal" events.
    log = SessionLog("s-lenient")
    log.append(EventType.USER_MESSAGE, {"role": "user", "content": "no-marker"})
    self.assertEqual(len(log.events), 1)


if __name__ == "__main__":
  unittest.main()