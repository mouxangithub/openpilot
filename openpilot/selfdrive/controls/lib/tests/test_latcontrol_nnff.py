"""Pure-logic unit tests for the StarPilot NNFF port (PC-safe parts).

Covers FluxModel math against a hand-built model, the model-matching chain
(including the Wildlander PHEV substitute), lookahead/jerk helpers and the
creep-guard style sign helper.
"""
import json
import os
import unittest

import numpy as np

from openpilot.selfdrive.controls.lib.nnff_model import (
  ACTIVATION_FUNCTION_NAMES,
  FluxModel,
  get_lookahead_value,
  get_nn_model_path,
  get_predicted_lateral_jerk,
  roll_pitch_adjust,
  similarity,
  sign,
)
from openpilot.selfdrive.controls.lib.nnff_variables import (
  get_nnff_model_files,
  get_nnff_substitutes,
)

T_IDXS = np.array([10.0 * (i / 12) ** 2 for i in range(13)])


def make_identity_model(path, input_size=4, output_size=1):
  """A model whose output is input[0] (weights implement a selector).

  Follows the real asset conventions: stored W is (out, in) and mean/std are
  (in, 1) column vectors so FluxModel's .T keeps broadcast shapes 2D.
  """
  layers = []
  layers.append({
    "linear_W": np.eye(output_size, input_size, dtype=np.float32).tolist(),
    "linear_b": [0.0] * output_size,
    "activation": "identity",
  })
  params = {
    "input_size": input_size,
    "output_size": output_size,
    "input_mean": [[0.0]] * input_size,
    "input_std": [[1.0]] * input_size,
    "layers": layers,
  }
  with open(path, "w") as f:
    json.dump(params, f)


class TestFluxModel(unittest.TestCase):
  def setUp(self):
    import tempfile
    self.tmp = tempfile.mkdtemp()
    self.path = os.path.join(self.tmp, "TEST_MODEL.json")
    make_identity_model(self.path, input_size=4)

  def test_identity_model_evaluates_input0(self):
    model = FluxModel(self.path)
    self.assertAlmostEqual(model.evaluate([3.0, 1.0, 0.5, 0.1]), 3.0, places=4)

  def test_short_input_pads_zeros(self):
    model = FluxModel(self.path)
    self.assertAlmostEqual(model.evaluate([2.5, 1.0]), 2.5, places=4)

  def test_too_short_input_raises(self):
    model = FluxModel(self.path)
    with self.assertRaises(ValueError):
      model.evaluate([1.0])

  def test_sigmoid_activation_recognized(self):
    # σ (U+03C3) must map to sigmoid
    self.assertEqual(ACTIVATION_FUNCTION_NAMES["σ"], "sigmoid")

  def test_unknown_activation_rejected(self):
    bad = os.path.join(self.tmp, "BAD.json")
    with open(bad, "w") as f:
      json.dump({"input_size": 2, "output_size": 1, "input_mean": [0, 0], "input_std": [1, 1],
                 "layers": [{"linear_W": [[1.0]], "linear_b": [0.0], "activation": "relu6"}]}, f)
    with self.assertRaises(ValueError):
      FluxModel(bad)


class TestModelMatching(unittest.TestCase):
  def test_assets_present(self):
    files = get_nnff_model_files()
    self.assertGreater(len(files), 100)
    self.assertIn("TOYOTA_RAV4_PRIME", files)

  def test_rav4_prime_exact_match(self):
    path = get_nn_model_path("TOYOTA_RAV4_PRIME", "")
    self.assertIsNotNone(path)
    self.assertIn("TOYOTA_RAV4_PRIME", os.path.basename(path))

  def test_wildlander_substitute_matches_rav4_prime(self):
    subs = get_nnff_substitutes()
    self.assertEqual(subs.get("TOYOTA_WILDLANDER_PHEV"), "TOYOTA_RAV4_PRIME")
    path = get_nn_model_path("TOYOTA_WILDLANDER_PHEV", "")
    self.assertIsNotNone(path)
    self.assertIn("TOYOTA_RAV4_PRIME", os.path.basename(path))

  def test_unknown_car_returns_none(self):
    self.assertIsNone(get_nn_model_path("FORD_FOCUS_XYZ_123", ""))

  def test_low_similarity_score_rejected(self):
    # a car whose fuzzy match is below the 0.9 gate must not match
    self.assertIsNone(get_nn_model_path("ZZZ", ""))


class TestHelpers(unittest.TestCase):
  def test_sign(self):
    self.assertEqual(sign(0.5), 1.0)
    self.assertEqual(sign(-0.5), -1.0)
    self.assertEqual(sign(0.0), 0.0)

  def test_lookahead_same_sign_takes_min_abs(self):
    self.assertAlmostEqual(get_lookahead_value([1.0, 2.0], 1.5), 1.0)
    self.assertAlmostEqual(get_lookahead_value([-2.0, -0.5], -1.0), -0.5)

  def test_lookahead_sign_flip_returns_zero(self):
    self.assertAlmostEqual(get_lookahead_value([1.0, -1.0], 0.5), 0.0)

  def test_lookahead_empty_returns_current(self):
    self.assertAlmostEqual(get_lookahead_value([], 0.7), 0.7)

  def test_predicted_lateral_jerk(self):
    accels = [0.0, 1.0, 3.0]
    t_diffs = [0.5, 0.5]
    self.assertEqual(get_predicted_lateral_jerk(accels, t_diffs), [2.0, 4.0])

  def test_roll_pitch_adjust_reduces_roll(self):
    self.assertLess(abs(roll_pitch_adjust(1.0, 0.5)), 1.0)
    self.assertAlmostEqual(roll_pitch_adjust(1.0, 0.0), 1.0)

  def test_similarity_ratio(self):
    self.assertGreater(similarity("TOYOTA_RAV4_PRIME", "TOYOTA_RAV4_PRIME"), 0.99)
    self.assertLess(similarity("AAA", "BBB"), 0.5)


if __name__ == "__main__":
  unittest.main()
