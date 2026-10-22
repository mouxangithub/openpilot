"""Advisory signal HUD rules (ported from carrot).

Kept free of pyray and cereal, so the colour and visibility decisions run
off-device as well as on it. The drawing that consumes them lives in
``sunnypilot.onroad.signal_hud``.
"""
import unittest
from types import SimpleNamespace as NS

from openpilot.selfdrive.ui.signal_status import (
  POINT_COLOR_LOW_CONFIDENCE, POINT_COLOR_VISION_ONLY, SIGNAL_DOT_COLORS, SIGNAL_GREEN, SIGNAL_MIXED,
  SIGNAL_PALETTE, SIGNAL_RED, SIGNAL_SUSPENDED_DIM, SIGNAL_UNKNOWN, point_box_color, signal_action,
  signal_colors, signal_suspended, signal_visible,
)


def _plan(action=0, suspended=False):
  return NS(signalAssistAction=action, signalDetectionSuspended=suspended)


class TestSignalAction(unittest.TestCase):
  def test_reads_the_planner_field(self):
    self.assertEqual(signal_action(_plan(3)), SIGNAL_MIXED)

  def test_unknown_values_collapse_to_unknown(self):
    for action in (0, 4, 9, -1):
      self.assertEqual(signal_action(_plan(action)), SIGNAL_UNKNOWN)

  def test_non_numeric_collapses_to_unknown(self):
    self.assertEqual(signal_action(_plan('red')), SIGNAL_UNKNOWN)

  def test_broken_message_is_swallowed(self):
    self.assertEqual(signal_action(object()), SIGNAL_UNKNOWN)


class TestSignalSuspended(unittest.TestCase):
  def test_reads_the_planner_field(self):
    self.assertTrue(signal_suspended(_plan(suspended=True)))

  def test_defaults_to_false(self):
    self.assertFalse(signal_suspended(_plan()))

  def test_broken_message_is_swallowed(self):
    self.assertFalse(signal_suspended(object()))


class TestSignalVisible(unittest.TestCase):
  def test_nothing_to_show_when_unknown_and_running(self):
    self.assertFalse(signal_visible(0, False))

  def test_known_action_is_shown(self):
    for action in (SIGNAL_RED, SIGNAL_GREEN, SIGNAL_MIXED):
      self.assertTrue(signal_visible(action, False))

  def test_suspended_alone_is_shown(self):
    self.assertTrue(signal_visible(SIGNAL_UNKNOWN, True))


class TestSignalColors(unittest.TestCase):
  def test_unknown_ring_is_grey_without_dot(self):
    ring, dot = signal_colors(SIGNAL_UNKNOWN, False)
    self.assertEqual(ring, SIGNAL_PALETTE[SIGNAL_UNKNOWN])
    self.assertIsNone(dot)

  def test_unexpected_values_fall_back_to_grey(self):
    for action in (9, -1, 'red', None):
      ring, dot = signal_colors(action, False)
      self.assertEqual(ring, SIGNAL_PALETTE[SIGNAL_UNKNOWN])
      self.assertIsNone(dot)

  def test_dot_matches_the_palette_mapping(self):
    for action in (SIGNAL_RED, SIGNAL_GREEN, SIGNAL_MIXED):
      _, dot = signal_colors(action, False)
      self.assertEqual(dot, SIGNAL_DOT_COLORS[action])

  def test_mixed_never_reads_as_a_green_departure(self):
    # carrot's swap: green evidence paints amber, mixed evidence paints green.
    _, green_evidenced = signal_colors(SIGNAL_GREEN, False)
    _, mixed = signal_colors(SIGNAL_MIXED, False)
    self.assertEqual(green_evidenced, SIGNAL_PALETTE[SIGNAL_MIXED])
    self.assertEqual(mixed, SIGNAL_PALETTE[SIGNAL_GREEN])
    self.assertNotEqual(green_evidenced, mixed)

  def test_suspended_dims_the_ring_but_keeps_the_dot(self):
    dimmed, dot = signal_colors(SIGNAL_RED, True)
    full = SIGNAL_PALETTE[SIGNAL_RED]
    self.assertEqual(dimmed[:3], tuple(int(v * SIGNAL_SUSPENDED_DIM) for v in full[:3]))
    self.assertEqual(dimmed[3], 255)
    self.assertTrue(all(d < f for d, f in zip(dimmed[:3], full[:3], strict=True)))
    self.assertEqual(dot, SIGNAL_DOT_COLORS[SIGNAL_RED])


class TestPointBoxColor(unittest.TestCase):
  def test_vision_only_is_blue(self):
    self.assertEqual(point_box_color(1.0, False, 0.03), POINT_COLOR_VISION_ONLY)

  def test_low_confidence_match_is_green(self):
    self.assertEqual(point_box_color(1.0, True, 0.01), POINT_COLOR_LOW_CONFIDENCE)

  def test_closing_is_amber_and_opening_is_red(self):
    self.assertEqual(point_box_color(1.0, True, 0.03), SIGNAL_PALETTE[SIGNAL_MIXED])
    self.assertEqual(point_box_color(-1.0, True, 0.03), SIGNAL_PALETTE[SIGNAL_RED])


if __name__ == "__main__":
  unittest.main()
