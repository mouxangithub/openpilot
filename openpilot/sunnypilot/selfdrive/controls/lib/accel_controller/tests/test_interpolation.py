import unittest

from openpilot.sunnypilot.selfdrive.controls.lib.accel_controller.interpolation import akima_interp


class TestAkimaInterp(unittest.TestCase):
  def test_clamps_outside_range(self):
    xp = [0.0, 3.0, 12.0, 24.0]
    fp = [1.75, 1.50, 0.40, 0.15]
    self.assertEqual(1.75, akima_interp(-1.0, xp, fp))
    self.assertEqual(1.75, akima_interp(0.0, xp, fp))
    self.assertEqual(0.15, akima_interp(24.0, xp, fp))
    self.assertEqual(0.15, akima_interp(99.0, xp, fp))

  def test_shape_differs_from_linear(self):
    # Zero-slope-at-knots smoothstep: at t=0.25 it is ABOVE the chord on a
    # falling pair (h=0.15625 vs linear 0.25) - the "no step at knots" shape.
    xp = [0.0, 10.0]
    fp = [2.0, 0.0]
    self.assertAlmostEqual(1.79296875, akima_interp(2.5, xp, fp), places=9)
    self.assertGreater(akima_interp(2.5, xp, fp), 1.5)  # linear would say 1.5

  def test_passes_through_knots_and_symmetry(self):
    xp = [0.0, 5.0, 12.0, 24.0]
    fp = [1.9, 1.6, 0.7, 0.3]
    for x, y in zip(xp, fp):
      self.assertAlmostEqual(y, akima_interp(x, xp, fp), places=9)
    # Symmetric falling ramp: halfway between two knots lands at the mean.
    self.assertAlmostEqual(1.0, akima_interp(8.5, [6.0, 11.0], [2.0, 0.0]), places=9)

  def test_degenerate_inputs(self):
    self.assertEqual(3.0, akima_interp(1.0, [2.0], [3.0]))  # single point
    with self.assertRaises(ValueError):
      akima_interp(1.0, [], [])
    with self.assertRaises(ValueError):
      akima_interp(1.0, [0.0, 1.0], [1.0])

  def test_duplicated_breakpoint_takes_right_endpoint(self):
    self.assertEqual(0.5, akima_interp(1.0, [0.0, 1.0, 1.0, 2.0], [1.0, 0.5, 0.5, 0.0]))


if __name__ == "__main__":
  unittest.main()
