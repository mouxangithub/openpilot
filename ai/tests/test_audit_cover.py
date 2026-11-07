"""Tests for platform tool audit coverage wrapper (T-P1.4)."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import ai.tests.bootstrap_pc  # noqa: F401


class TestAuditCover(unittest.TestCase):
  def test_wrap_records_audit_for_audited_tool(self):
    from ai.tools.domains.platform.audit_cover import wrap_with_audit

    calls = []

    def h_write(args):
      calls.append(args)
      return {"ok": True}

    with patch("ai.tools.domains.platform.audit_cover.record_audit") as mock_record:
      handlers = wrap_with_audit({"update_workspace_file": h_write})
      result = handlers["update_workspace_file"]({"key": "user", "content": "secret"})

    self.assertTrue(result["ok"])
    self.assertEqual(len(calls), 1)
    self.assertEqual(mock_record.call_count, 1)
    detail = mock_record.call_args.kwargs.get("detail") or mock_record.call_args[1].get("detail")
    self.assertEqual(detail["args"]["content"], "<redacted>")

  def test_wrap_skips_read_only_tool(self):
    from ai.tools.domains.platform.audit_cover import wrap_with_audit

    def h_read(_args):
      return {"ok": True, "items": []}

    with patch("ai.tools.domains.platform.audit_cover.record_audit") as mock_record:
      handlers = wrap_with_audit({"sessions_list": h_read})
      handlers["sessions_list"]({})

    self.assertEqual(mock_record.call_count, 0)

  def test_session_id_from_args(self):
    from ai.tools.domains.platform.audit_cover import wrap_with_audit

    def h_send(args):
      return {"ok": True}

    with patch("ai.tools.domains.platform.audit_cover.record_audit") as mock_record:
      handlers = wrap_with_audit({"sessions_send": h_send})
      handlers["sessions_send"]({"session_id": "s-42", "message": "hi"})

    kwargs = mock_record.call_args.kwargs or mock_record.call_args[1]
    self.assertEqual(kwargs.get("session_id"), "s-42")


if __name__ == "__main__":
  unittest.main()
