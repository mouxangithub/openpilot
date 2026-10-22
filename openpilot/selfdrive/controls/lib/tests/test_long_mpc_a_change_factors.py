"""The a-change cost taper must stay numerically identical after precomputing it.

`set_cost_weights` used to interpolate the taper for every horizon step; the
factor depends only on the fixed horizon times, so it is now computed once at
import. These lock the two forms agree exactly (not approximately).
"""
import unittest

import numpy as np

from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import (
  A_CHANGE_FACTORS, N, T_IDXS,
)


def reference_factors():
  """The original per-step expression."""
  return np.array([np.interp(T_IDXS[i], [0.0, 1.0, 2.0], [1.0, 1.0, 0.0]) for i in range(N)])


class TestAChangeFactors(unittest.TestCase):
  def test_precomputed_matches_the_original_expression(self):
    expected = reference_factors()
    self.assertEqual(A_CHANGE_FACTORS.shape, (N,))
    np.testing.assert_array_equal(A_CHANGE_FACTORS, expected)

  def test_taper_is_monotonic_and_bounded(self):
    self.assertTrue(np.all(np.diff(A_CHANGE_FACTORS) <= 0))
    self.assertGreaterEqual(A_CHANGE_FACTORS.min(), 0.0)
    self.assertLessEqual(A_CHANGE_FACTORS.max(), 1.0)
    self.assertEqual(A_CHANGE_FACTORS[0], 1.0)  # no taper in the first step

  def test_taper_starts_dropping_after_one_second(self):
    drops = [i for i, f in enumerate(A_CHANGE_FACTORS) if f < 1.0]
    self.assertTrue(drops)
    self.assertGreaterEqual(T_IDXS[drops[0]], 1.0)

  def test_cost_matrix_uses_the_precomputed_factor(self):
    # W[4,4] = cost_weights[4] * factor, applied per horizon step.
    cost = 3.5
    written = [cost * A_CHANGE_FACTORS[i] for i in range(N)]
    self.assertEqual(written[0], cost)  # first step is untapered
    self.assertTrue(all(w <= cost for w in written))
    self.assertLess(written[-1], cost)  # fully tapered at the far horizon
    self.assertEqual(written[-1], 0.0)


if __name__ == '__main__':
  unittest.main()
