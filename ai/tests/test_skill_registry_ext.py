"""Tests for skill rank / invocation policy / change events (D-P0.3, D-P1.3)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import ai.tests.bootstrap_pc  # noqa: F401


def _make_skill(sid, **kw):
  from ai.skill.models import Skill
  defaults = dict(
    id=sid, name=sid, description=sid, policy="auto",
    parameters=[], scope="global",
  )
  defaults.update(kw)
  return Skill(**defaults)


class TestSkillRegistryExt(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    from ai.skill.registry import SkillRegistry
    self.reg = SkillRegistry(Path(self.tmp.name))

  def tearDown(self):
    self.tmp.cleanup()

  def test_rank_sorting(self):
    self.reg.register(_make_skill("a", rank=600))
    self.reg.register(_make_skill("b", rank=250))
    self.reg.register(_make_skill("c", rank=600))
    names = [s.id for s in self.reg.list_skills_sorted()]
    self.assertEqual(names, ["b", "a", "c"])

  def test_rank_roundtrip_through_dict(self):
    s = _make_skill("x", rank=250)
    from ai.skill.models import Skill
    s2 = Skill.from_dict(s.to_dict())
    self.assertEqual(s2.rank, 250)

  def test_invocation_policy_blocks_model(self):
    from ai.skill.models import SkillError, SkillInvocationPolicy
    s = _make_skill("m-only", invocation_policy=SkillInvocationPolicy(model_invocable=False, user_invocable=True))
    s.handler = lambda **kw: {"ok": True}
    self.reg.register(s)
    with self.assertRaises(SkillError):
      self.reg.request_invocation("m-only", {}, caller="model")
    # user may still invoke
    inv = self.reg.request_invocation("m-only", {}, caller="user")
    self.assertEqual(inv.status, "success")

  def test_invocation_policy_blocks_user(self):
    from ai.skill.models import SkillError, SkillInvocationPolicy
    s = _make_skill("u-only", invocation_policy=SkillInvocationPolicy(model_invocable=True, user_invocable=False))
    s.handler = lambda **kw: {"ok": True}
    self.reg.register(s)
    with self.assertRaises(SkillError):
      self.reg.request_invocation("u-only", {}, caller="user")
    inv = self.reg.request_invocation("u-only", {}, caller="model")
    self.assertEqual(inv.status, "success")

  def test_default_policy_permissive(self):
    s = _make_skill("legacy")
    s.handler = lambda **kw: {"ok": True}
    self.reg.register(s)
    inv = self.reg.request_invocation("legacy", {}, caller="model")
    self.assertEqual(inv.status, "success")

  def test_change_events_fire(self):
    events = []
    unsub = self.reg.on_change(events.append)
    self.reg.register(_make_skill("e1"))
    self.reg.register(_make_skill("e2"))
    self.reg.unregister("e1")
    self.assertIn("skill/register", events)
    self.assertIn("skill/remove", events)
    self.assertGreaterEqual(self.reg.revision, 3)
    # unsubscribe
    n0 = len(events)
    unsub()
    self.reg.register(_make_skill("e3"))
    self.assertEqual(len(events), n0)


if __name__ == "__main__":
  unittest.main()