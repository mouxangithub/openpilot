#!/usr/bin/env python3
"""NNFF model loading and matching (pure logic, PC-testable).

FluxModel evaluates the per-vehicle JSON MLP; the matcher picks the best
model file for a car fingerprint (+ EPS firmware) using substitutes and a
similarity gate. Split from latcontrol_nnff so test hosts without the
LatControl import chain can still exercise the math.
"""
import json
import math
import os
from difflib import SequenceMatcher

import numpy as np

# At higher speeds (25+mph) we can assume:
# Lateral acceleration achieved by a specific car correlates to
# torque applied to the steering rack. It does not correlate to
# wheel slip, or to speed.

# dict used to rename activation functions whose names aren't valid python identifiers
ACTIVATION_FUNCTION_NAMES = {"σ": "sigmoid"}

PALISADE_NNFF_LAT_JERK_FRICTION_FACTOR = 0.25
DEFAULT_NNFF_LAT_JERK_FRICTION_FACTOR = 0.4

LOW_SPEED_X = [0, 10, 20, 30]
LOW_SPEED_Y = [12, 3, 1, 0]

LAT_PLAN_MIN_IDX = 5


def get_nnff_lat_jerk_friction_factor(car_fingerprint) -> float:
  if "PALISADE" in car_fingerprint:
    return PALISADE_NNFF_LAT_JERK_FRICTION_FACTOR
  return DEFAULT_NNFF_LAT_JERK_FRICTION_FACTOR


class FluxModel:
  def __init__(self, params_file):
    with open(params_file) as f:
      params = json.load(f)

    self.input_size = params["input_size"]
    self.output_size = params["output_size"]

    self.input_mean = np.array(params["input_mean"], dtype=np.float32).T
    self.input_std = np.array(params["input_std"], dtype=np.float32).T

    self.layers = []
    for layer_params in params["layers"]:
      bias_array = np.array(layer_params[next(key for key in layer_params.keys() if key.endswith("_b"))], dtype=np.float32).T
      weight_array = np.array(layer_params[next(key for key in layer_params.keys() if key.endswith("_W"))], dtype=np.float32).T

      activation = layer_params["activation"]
      for name, replacement in ACTIVATION_FUNCTION_NAMES.items():
        activation = activation.replace(name, replacement)

      self.layers.append((weight_array, bias_array, activation))

    self.validate_layers()
    self.check_for_friction_override()

  # Begin activation functions.
  @staticmethod
  def identity(x):
    return x

  @staticmethod
  def sigmoid(x):
    return 1 / (1 + np.exp(-x))
  # End activation functions

  def check_for_friction_override(self):
    self.friction_override = self.evaluate([10.0, 0.0, 0.2]) < 0.1

  def evaluate(self, input_array):
    if len(input_array) != self.input_size:
      # If the input is length 2-4, then it's a simplified evaluation.
      # In that case, add zeros to fill out the input to the model length.
      if len(input_array) >= 2:
        input_array = list(input_array) + [0] * (self.input_size - len(input_array))
      else:
        raise ValueError(f"Input length {len(input_array)} must be 2 or greater")

    # Rescale the input array using the input_mean and input_std
    output = self.forward((np.array(input_array, dtype=np.float32) - self.input_mean) / self.input_std)
    return float(output[0, 0])

  def forward(self, x):
    for weights, bias, activation in self.layers:
      x = getattr(self, activation)(x @ weights + bias)
    return x

  def validate_layers(self):
    for _, _, activation in self.layers:
      if not hasattr(self, activation):
        raise ValueError(f"Unknown activation function: {activation}")


def get_lookahead_value(future_values, current_value):
  if not future_values:
    return current_value

  if any(sign(value) != sign(current_value) for value in future_values):
    return 0.0

  return min(future_values + [current_value], key=abs)


def get_nn_model_path(car, eps_firmware) -> str | None:
  from openpilot.selfdrive.controls.lib.nnff_variables import NNFF_MODELS_PATH, get_nnff_model_files, get_nnff_substitutes

  def best_model_path(query):
    candidates = get_nnff_model_files()
    if not candidates:
      return None, 0.0

    best = max(candidates, key=lambda model: similarity(model, query))
    return os.path.join(NNFF_MODELS_PATH, f"{best}.json"), similarity(best, query)

  def find_valid_model(*queries_with_candidates):
    for query, candidate in queries_with_candidates:
      path, score = best_model_path(query)
      if path and candidate in path and score >= 0.9:
        return path
    return None

  substitutes = get_nnff_substitutes()
  sub_candidate = substitutes.get(car, car)

  candidates_to_check = [car]
  if car != sub_candidate:
    candidates_to_check.append(sub_candidate)

  queries = []
  for candidate in candidates_to_check:
    query_with_fw = f"{candidate} {eps_firmware}" if len(eps_firmware) > 3 else candidate
    queries.append((query_with_fw, candidate))
    queries.append((candidate, candidate))

  return find_valid_model(*queries)


def get_nn_model(car, eps_firmware) -> FluxModel | None:
  model_path = get_nn_model_path(car, eps_firmware)
  if model_path:
    return FluxModel(model_path)
  return None


def get_predicted_lateral_jerk(lat_accels, t_diffs):
  # finite difference between subsequent model lateral accelerations
  return (np.diff(lat_accels) / t_diffs).tolist()


def roll_pitch_adjust(roll, pitch):
  # At a given roll, if pitch magnitude increases, the gravitational
  # component points more longitudinally, decreasing the lateral component.
  return roll * math.cos(pitch)


def sign(x):
  return 1.0 if x > 0 else -1.0 if x < 0 else 0.0


def similarity(s1: str, s2: str) -> float:
  return SequenceMatcher(None, s1, s2).ratio()


