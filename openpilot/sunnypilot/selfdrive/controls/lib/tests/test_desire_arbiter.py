"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from types import SimpleNamespace

from openpilot.common.test import OpenpilotTestCase

from openpilot.sunnypilot.selfdrive.controls.lib.desire_arbiter import DesireArbiter, RawDesire


def _log_desire():
  from openpilot.cereal import log
  return log.Desire


class TestDesireArbiter(OpenpilotTestCase):
  def test_default_is_none(self):
    arb = DesireArbiter()
    arb.enabled = True
    log_desire = _log_desire()
    assert arb.resolve(False, False, False, False, False, False, False, False, log_desire=log_desire) == log_desire.none

  def test_sustained_turn_left(self):
    arb = DesireArbiter()
    arb.enabled = True
    log_desire = _log_desire()
    for _ in range(5):
      arb.update(True, False, False, False, False, False, False, False)
    assert arb.desire == RawDesire.TURN_LEFT
    assert arb.resolve(True, False, False, False, False, False, False, False, log_desire=log_desire) == log_desire.turnLeft

  def test_turn_wins_over_lane_change(self):
    arb = DesireArbiter()
    arb.enabled = True
    for _ in range(5):
      arb.update(False, True, False, False, False, False, True, False)
    assert arb.desire == RawDesire.TURN_RIGHT

  def test_conflict_turn_both_directions_is_none(self):
    arb = DesireArbiter()
    arb.enabled = True
    for _ in range(5):
      arb.update(True, True, False, False, False, False, False, False)
    assert arb.desire == RawDesire.NONE

  def test_safety_veto_clears_desire(self):
    arb = DesireArbiter()
    arb.enabled = True
    for _ in range(5):
      arb.update(True, False, False, False, False, False, False, False)
    assert arb.desire == RawDesire.TURN_LEFT
    arb.update(True, False, False, False, False, False, False, False, safety_veto=True)
    assert arb.desire == RawDesire.NONE
