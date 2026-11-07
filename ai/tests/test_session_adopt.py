"""Tests for session adoptability checks (D-P0.5)."""
from __future__ import annotations

import unittest

import ai.tests.bootstrap_pc  # noqa: F401


class _H:
  def __init__(self, **kw):
    self.cwd = kw.get("cwd", "")
    self.parent_session = kw.get("parent_session", "")
    self.origin = kw.get("origin", "")
    self.agent_preset = kw.get("agent_preset", "default")


class TestAdoptable(unittest.TestCase):
  def test_plain_session_adoptable(self):
    from ai.core.session.adopt import check_adoptable
    check = check_adoptable(_H(cwd="/w"), cwd="/w")
    self.assertTrue(check.ok)

  def test_rejects_parent_lineage(self):
    from ai.core.session.adopt import check_adoptable
    check = check_adoptable(_H(parent_session="parent-1"))
    self.assertFalse(check.ok)
    self.assertIn("parent", check.reason)

  def test_rejects_subagent_origin(self):
    from ai.core.session.adopt import check_adoptable
    check = check_adoptable(_H(origin="subagent"))
    self.assertFalse(check.ok)

  def test_rejects_preset_override(self):
    from ai.core.session.adopt import check_adoptable
    check = check_adoptable(_H(agent_preset="tuned"))
    self.assertFalse(check.ok)

  def test_default_preset_allowed(self):
    from ai.core.session.adopt import check_adoptable
    check = check_adoptable(_H(agent_preset="default"))
    self.assertTrue(check.ok)

  def test_cwd_mismatch_rejected(self):
    from ai.core.session.adopt import check_adoptable
    check = check_adoptable(_H(cwd="/other"), cwd="/w")
    self.assertFalse(check.ok)

  def test_empty_record_cwd_allowed(self):
    from ai.core.session.adopt import check_adoptable
    check = check_adoptable(_H(cwd=""), cwd="/w")
    self.assertTrue(check.ok)

  def test_assert_raises(self):
    from ai.core.session.adopt import SessionNotAdoptable, assert_adoptable
    with self.assertRaises(SessionNotAdoptable):
      assert_adoptable(_H(parent_session="x"))

  def test_accepts_dict_header(self):
    from ai.core.session.adopt import check_adoptable
    check = check_adoptable({"cwd": "/w", "parent_session": "", "origin": "", "agent_preset": "default"}, cwd="/w")
    self.assertTrue(check.ok)


if __name__ == "__main__":
  unittest.main()