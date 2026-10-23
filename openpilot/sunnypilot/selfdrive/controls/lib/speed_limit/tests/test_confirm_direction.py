"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Per-direction confirmation of speed-limit changes.

The existing confirm-speed-threshold rule answers "is this change big or
low enough to ask about"; this one answers "is this change going the
direction I want to be asked about". The two are combined with an OR, so the
new rule can only ever add a prompt. The tests pin that, because a rule that
could suppress the threshold prompt would let a speed limit drop on the
driver without a word.
"""

import unittest

from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.confirm_direction import (
  CONFIRM_BOTH,
  CONFIRM_HIGHER,
  CONFIRM_LOWER,
  CONFIRM_NEVER,
  confirm_needed_for_direction,
)


class TestDirectionConfirmation(unittest.TestCase):
  def test_never_asks_for_anything(self):
    self.assertFalse(confirm_needed_for_direction(60, 40, CONFIRM_NEVER))
    self.assertFalse(confirm_needed_for_direction(60, 80, CONFIRM_NEVER))

  def test_lower_only_asks_when_the_limit_drops(self):
    self.assertTrue(confirm_needed_for_direction(60, 40, CONFIRM_LOWER))
    self.assertFalse(confirm_needed_for_direction(60, 80, CONFIRM_LOWER))

  def test_higher_only_asks_when_the_limit_rises(self):
    self.assertFalse(confirm_needed_for_direction(60, 40, CONFIRM_HIGHER))
    self.assertTrue(confirm_needed_for_direction(60, 80, CONFIRM_HIGHER))

  def test_both_asks_either_way(self):
    self.assertTrue(confirm_needed_for_direction(60, 40, CONFIRM_BOTH))
    self.assertTrue(confirm_needed_for_direction(60, 80, CONFIRM_BOTH))

  def test_an_unchanged_limit_never_asks(self):
    for policy in (CONFIRM_NEVER, CONFIRM_LOWER, CONFIRM_HIGHER, CONFIRM_BOTH):
      self.assertFalse(confirm_needed_for_direction(60, 60, policy), policy)

  def test_no_current_limit_never_asks(self):
    # Nothing to confirm against: the first limit of a drive is not a change.
    for policy in (CONFIRM_NEVER, CONFIRM_LOWER, CONFIRM_HIGHER, CONFIRM_BOTH):
      self.assertFalse(confirm_needed_for_direction(0, 60, policy), policy)

  def test_no_new_limit_never_asks(self):
    for policy in (CONFIRM_NEVER, CONFIRM_LOWER, CONFIRM_HIGHER, CONFIRM_BOTH):
      self.assertFalse(confirm_needed_for_direction(60, 0, policy), policy)

  def test_an_unknown_policy_reads_as_never(self):
    # An unreadable setting must not start prompting on roads where the fork
    # never prompted before.
    self.assertFalse(confirm_needed_for_direction(60, 40, 99))
    self.assertFalse(confirm_needed_for_direction(60, 80, -1))


class TestTheNewRuleOnlyAddsPrompts(unittest.TestCase):
  """The direction rule is OR-ed with the threshold rule, never replaces it.

  These cases compute the combined decision the way `speed_limit_assist`
  does, and check that turning the direction policy on can only move a case
  from "no prompt" to "prompt".
  """

  @staticmethod
  def _combined(threshold_asks: bool, current: int, new: int, policy: int) -> bool:
    return threshold_asks or confirm_needed_for_direction(current, new, policy)

  def test_a_threshold_prompt_survives_every_policy(self):
    for policy in (CONFIRM_NEVER, CONFIRM_LOWER, CONFIRM_HIGHER, CONFIRM_BOTH):
      for current, new in ((60, 40), (60, 80), (60, 60)):
        self.assertTrue(self._combined(True, current, new, policy), (policy, current, new))

  def test_no_policy_can_turn_a_prompt_off(self):
    for policy in (CONFIRM_NEVER, CONFIRM_LOWER, CONFIRM_HIGHER, CONFIRM_BOTH):
      for current, new in ((60, 40), (60, 80)):
        self.assertTrue(self._combined(True, current, new, policy))

  def test_the_policy_can_add_a_prompt_where_the_threshold_did_not(self):
    # A limit dropping at speed: the threshold rule skips it, the policy catches it.
    self.assertFalse(self._combined(False, 60, 40, CONFIRM_NEVER))
    self.assertTrue(self._combined(False, 60, 40, CONFIRM_LOWER))


class TestTheDirectionRuleCanActuallyFire(unittest.TestCase):
  """The rule needs a *previous* value to compare against.

  This is a regression guard. The first version of this code compared the
  frame's converted limit against itself (`speed_limit_final_conv` was
  assigned from the same source as `speed_limit_final_last_conv`), so the two
  arguments were always equal and the rule could never fire - a setting that
  looked wired up in the UI and did nothing on the road.

  The sequence below mirrors `update_calculations`, which carries the value
  forward one frame at a time.
  """

  @staticmethod
  def _frames(limits, policy):
    """Run the carry-forward the controller does, frame by frame."""
    this_conv = 0
    prev_conv = 0
    results = []
    for limit_conv in limits:
      prev_conv = this_conv
      this_conv = limit_conv
      results.append(confirm_needed_for_direction(prev_conv, this_conv, policy))
    return results

  def test_a_real_limit_drop_fires(self):
    results = self._frames([60, 60, 40, 40], CONFIRM_LOWER)
    self.assertEqual(results, [False, False, True, False])

  def test_a_real_limit_rise_fires_under_the_higher_policy(self):
    results = self._frames([40, 40, 60, 60], CONFIRM_HIGHER)
    self.assertEqual(results, [False, False, True, False])

  def test_a_drop_does_not_fire_under_the_higher_policy(self):
    results = self._frames([60, 60, 40, 40], CONFIRM_HIGHER)
    self.assertEqual(results, [False, False, False, False])

  def test_the_first_frame_never_fires(self):
    # There is no previous limit to compare against on the first frame.
    self.assertFalse(self._frames([60], CONFIRM_BOTH)[0])

  def test_comparing_a_value_with_itself_never_fires(self):
    # The shape of the original bug, asserted so it cannot come back.
    for policy in (CONFIRM_LOWER, CONFIRM_HIGHER, CONFIRM_BOTH):
      self.assertFalse(confirm_needed_for_direction(40, 40, policy), policy)


if __name__ == "__main__":
  unittest.main()
