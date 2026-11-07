"""Tests for the unified session resume path (A-P0.3)."""
from __future__ import annotations

import unittest

import ai.tests.bootstrap_pc  # noqa: F401


class TestUnifiedResume(unittest.TestCase):
  def test_resume_fresh_session(self):
    from ai.core.session.resume import unified_resume
    log = unified_resume("fresh-session-xyz")
    self.assertEqual(log.session_id, "fresh-session-xyz")
    self.assertEqual(log.seq, 0)

  def test_resume_rejects_unadoptable(self):
    from ai.core.session.log import EventType, SessionLog, get_session_store
    from ai.core.session.resume import ResumeError, unified_resume
    store = get_session_store()
    sid = "parent-lineage-session"
    log = SessionLog(sid)
    store._sessions[sid] = log
    # Inject a header with a parent lineage via the session header field.
    from ai.core.session.log import SessionHeader
    log._session_header = SessionHeader(cwd="/w", parent_session="p1", origin="", agent_preset="default")
    with self.assertRaises(ResumeError):
      unified_resume(sid, cwd="/w")

  def test_resume_adoptable_header(self):
    from ai.core.session.log import SessionLog, SessionHeader, get_session_store
    from ai.core.session.resume import unified_resume
    store = get_session_store()
    sid = "ok-header-session"
    log = SessionLog(sid)
    store._sessions[sid] = log
    log._session_header = SessionHeader(cwd="/w", parent_session="", origin="", agent_preset="default")
    resumed = unified_resume(sid, cwd="/w")
    self.assertEqual(resumed.session_id, sid)


if __name__ == "__main__":
  unittest.main()