"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""DEC trigger gating.

The switch layer sits in front of the controller's own decision, so the one
property that matters most is that it changes nothing when no one has touched
it: with every trigger on, the decision has to be bit-for-bit the one the
controller made before the switches existed. That is what
`TestDefaultsAreBehaviourPreserving` exhausts over the signal space.
"""

import itertools
import unittest

from openpilot.sunnypilot.selfdrive.controls.lib.dec.triggers import (
  TRIGGERS,
  TRIGGER_CURVE,
  TRIGGER_LEAD,
  TRIGGER_LOW_SPEED,
  TRIGGER_PARAM_KEYS,
  TRIGGER_SIGNAL,
  TRIGGER_STOP_LIGHT,
  trigger_allowed,
  triggers_from_values,
)

# The controller's own constants, restated here so this test does not import
# the module that pulls in cereal.
MODEL_TRUST_MIN = 0.5
DECEL_INTENT_CURVE_OVERRIDE = 0.9
DECEL_INTENT_TRIGGER = 0.5


def should_blend(decel_intent, curve_detected, model_trust, creeping):
  """The controller's decision, before the switch layer existed."""
  degraded = model_trust < MODEL_TRUST_MIN
  curve_gate = decel_intent >= DECEL_INTENT_CURVE_OVERRIDE or not curve_detected
  slowdown_detected = not degraded and decel_intent >= DECEL_INTENT_TRIGGER and curve_gate
  return slowdown_detected or creeping


def should_blend_with_triggers(decel_intent, curve_detected, model_trust, creeping, triggers):
  """The same decision with the switch layer applied, as `dec.py` does it."""
  if triggers is not None:
    curve_detected = curve_detected if triggers.get(TRIGGER_CURVE, True) else False
    creeping = creeping if triggers.get(TRIGGER_LOW_SPEED, True) else False
  return should_blend(decel_intent, curve_detected, model_trust, creeping)


class TestTriggerTable(unittest.TestCase):
  def test_every_trigger_has_a_parameter(self):
    for trigger in TRIGGERS:
      self.assertIn(trigger, TRIGGER_PARAM_KEYS)

  def test_the_parameter_names_are_distinct(self):
    keys = list(TRIGGER_PARAM_KEYS.values())
    self.assertEqual(len(keys), len(set(keys)))

  def test_the_expected_triggers_exist(self):
    self.assertEqual(set(TRIGGERS), {TRIGGER_CURVE, TRIGGER_LEAD, TRIGGER_SIGNAL,
                                     TRIGGER_STOP_LIGHT, TRIGGER_LOW_SPEED})


class TestTriggerAllowed(unittest.TestCase):
  def test_an_explicit_on_is_on(self):
    self.assertTrue(trigger_allowed(TRIGGER_CURVE, {TRIGGER_CURVE: True}))

  def test_an_explicit_off_is_off(self):
    self.assertFalse(trigger_allowed(TRIGGER_CURVE, {TRIGGER_CURVE: False}))

  def test_a_missing_map_allows(self):
    # A settings store that predates the switches must not turn anything off.
    self.assertTrue(trigger_allowed(TRIGGER_CURVE, None))
    self.assertTrue(trigger_allowed(TRIGGER_CURVE, {}))

  def test_an_unknown_trigger_is_allowed(self):
    self.assertTrue(trigger_allowed("not_a_trigger", {TRIGGER_CURVE: False}))

  def test_a_missing_entry_for_a_known_trigger_is_allowed(self):
    self.assertTrue(trigger_allowed(TRIGGER_LEAD, {TRIGGER_CURVE: False}))


class TestTriggersFromValues(unittest.TestCase):
  def test_no_values_means_all_on(self):
    self.assertEqual(triggers_from_values(None), dict.fromkeys(TRIGGERS, True))
    self.assertEqual(triggers_from_values({}), dict.fromkeys(TRIGGERS, True))

  def test_string_zeros_read_as_off(self):
    for raw in ("0", "false", "False", ""):
      self.assertFalse(triggers_from_values({TRIGGER_CURVE: raw})[TRIGGER_CURVE], raw)

  def test_string_ones_read_as_on(self):
    for raw in ("1", "true", "True"):
      self.assertTrue(triggers_from_values({TRIGGER_CURVE: raw})[TRIGGER_CURVE], raw)

  def test_booleans_pass_through(self):
    self.assertFalse(triggers_from_values({TRIGGER_CURVE: False})[TRIGGER_CURVE])
    self.assertTrue(triggers_from_values({TRIGGER_CURVE: True})[TRIGGER_CURVE])

  def test_an_unmentioned_trigger_stays_on(self):
    values = triggers_from_values({TRIGGER_CURVE: "0"})
    self.assertFalse(values[TRIGGER_CURVE])
    for trigger in TRIGGERS:
      if trigger != TRIGGER_CURVE:
        self.assertTrue(values[trigger], trigger)


class TestDefaultsAreBehaviourPreserving(unittest.TestCase):
  def test_every_trigger_on_matches_the_original_over_the_whole_signal_space(self):
    all_on = dict.fromkeys(TRIGGERS, True)
    mismatches = []
    for decel_intent, curve, trust, creeping in itertools.product(
        (0.0, 0.4, 0.5, 0.8, 0.9, 1.0), (True, False), (0.0, 0.4, 0.5, 1.0), (True, False)):
      before = should_blend(decel_intent, curve, trust, creeping)
      after = should_blend_with_triggers(decel_intent, curve, trust, creeping, all_on)
      if before != after:
        mismatches.append((decel_intent, curve, trust, creeping, before, after))
    self.assertEqual(mismatches, [])

  def test_a_missing_trigger_map_matches_the_original(self):
    # `None` is what the controller holds before its first param read.
    for decel_intent, curve, trust, creeping in itertools.product(
        (0.0, 0.5, 0.9), (True, False), (0.0, 1.0), (True, False)):
      self.assertEqual(
        should_blend(decel_intent, curve, trust, creeping),
        should_blend_with_triggers(decel_intent, curve, trust, creeping, None),
      )


class TestTriggersRestrict(unittest.TestCase):
  """A switch may only ever stop a blend, never cause one."""

  def test_turning_the_curve_trigger_off_drops_the_curve_gate(self):
    # A curve was detected and the intent is weak, so the original withholds
    # the blend. With curves no longer participating, the blend happens.
    self.assertFalse(should_blend(0.6, True, 1.0, False))
    self.assertTrue(should_blend_with_triggers(0.6, True, 1.0, False, {TRIGGER_CURVE: False}))

  def test_turning_the_low_speed_trigger_off_drops_creep(self):
    self.assertTrue(should_blend(0.0, False, 1.0, True))
    self.assertFalse(should_blend_with_triggers(0.0, False, 1.0, True, {TRIGGER_LOW_SPEED: False}))

  def test_no_switch_combination_ever_adds_a_blend_that_the_signals_did_not_cause(self):
    # With no signal firing at all, no setting may produce a blend.
    for combo in itertools.product((True, False), repeat=len(TRIGGERS)):
      triggers = dict(zip(TRIGGERS, combo, strict=True))
      # No decel intent, no curve, degraded trust, not creeping.
      self.assertFalse(should_blend_with_triggers(0.0, False, 0.0, False, triggers), triggers)


if __name__ == "__main__":
  unittest.main()
