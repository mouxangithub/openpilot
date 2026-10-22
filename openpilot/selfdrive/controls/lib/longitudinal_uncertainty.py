#!/usr/bin/env python3
"""Model-uncertainty tracking and panic-bypass gate (StarPilot port).

Combines the model's desire-prediction entropy with an exponentially decayed
brake-press risk into a single scene-uncertainty metric, tracked by two
first-order filters (slow/fast). A fast uncertainty rise or a high sustained
magnitude while closing on a nearby lead triggers a "panic bypass": downstream
comfort smoothing (follow policy shaping) must not delay the braking response.

Pure logic only -- no Params, no swaglog, no hardware imports, safe to import
and unit-test on a PC host.
"""
import numpy as np

from openpilot.common.filter_simple import FirstOrderFilter

# Model frame period. Kept local (same value as common.realtime.DT_MDL) so the
# module stays free of the realtime->utils->zstandard import chain on PC hosts.
DT_MDL = 0.05

# Uncertainty-based filter disable thresholds (StarPilot verbatim)
UNCERT_SLOPE_TRIG = 0.12  # per second
UNCERT_MAG_TRIG = 0.50
UNCERT_PANIC_MIN_CLOSING_SPEED = 2.0
UNCERT_PANIC_MIN_CLOSING_SPEED_GAIN = 0.08
UNCERT_PANIC_MAX_GAP_BUFFER_MIN = 8.0
UNCERT_PANIC_MAX_GAP_BUFFER_GAIN = 0.35

# Two uncertainty tracks (slow/fast) for asymmetric gating (StarPilot init)
UNCERT_SLOW_TAU = 1.6  # ~lam=0.6
UNCERT_FAST_TAU = 0.9  # faster cool-down for accel decisions

# Brake-blip clip: tiny blips are halved so they don't inflate uncertainty
UNCERT_BRAKE_BLIP_CLIP = 0.015
# Exponential decay rate for brake-press probabilities (per second)
UNCERT_BRAKE_DECAY_LAM = 0.6
# Panic closing window already matches a distant or pace-matched lead guard:
# closing speed must beat max(2.0, 0.08 * v_ego)
UNCERT_MIN_CLOSING_SPEED = 0.75
UNCERT_MIN_TTC = 7.0

DESIRE_EPS = 1e-10


def compute_raw_uncertainty(model_meta):
  """Raw uncertainty = normalized desire entropy + decayed brake-press risk.

  model_meta is sm['modelV2'].meta (or a stand-in with the same fields).
  Returns a float roughly in [0, 2]. Pure function.
  """
  if model_meta is None:
    return 0.0

  # Desire prediction entropy (maneuver uncertainty), normalized to [0, 1]
  desire_entropy = 0.0
  desire_probs = getattr(model_meta, "desirePrediction", None)
  if desire_probs is not None and len(desire_probs) > 1:
    probs = np.asarray(desire_probs, dtype=float)
    total = float(np.sum(probs))
    if total > 1e-6:
      p = probs / total
      entropy = -np.sum(p * np.log(p + DESIRE_EPS))
      max_entropy = np.log(len(p))
      desire_entropy = float(entropy / max(max_entropy, DESIRE_EPS))
    # all-zero vector guards to 0.0

  # Disengage prediction risk (intervention likelihood)
  disengage_risk = 0.0
  disengage = getattr(model_meta, "disengagePredictions", None)
  brake_probs = getattr(disengage, "brakePressProbs", None) if disengage is not None else None
  if brake_probs is not None and len(brake_probs) > 0:
    probs = np.asarray(brake_probs, dtype=float)
    # Clip tiny brake blips so they don't inflate uncertainty
    if float(np.max(probs)) < UNCERT_BRAKE_BLIP_CLIP:
      probs = probs * 0.5
    # Exponentially decayed max over the full horizon
    t = np.arange(len(probs), dtype=float) * DT_MDL
    weights = np.exp(-UNCERT_BRAKE_DECAY_LAM * t)
    disengage_risk = float(np.max(probs * weights))

  return float(desire_entropy + disengage_risk)


class UncertaintyTracker:
  """Dual-track uncertainty state (StarPilot planner state, standalone).

  update() returns (uncertainty, uncertainty_accel, uncert_slope) where
  uncertainty is the slow-track value, uncertainty_accel is the permissive
  min(slow, fast) track for accel decisions, and uncert_slope is the
  per-second slope of the slow track.
  """

  def __init__(self, dt):
    self.dt = float(dt)
    self.uncert_slow = FirstOrderFilter(0.0, UNCERT_SLOW_TAU, self.dt)
    self.uncert_fast = FirstOrderFilter(0.0, UNCERT_FAST_TAU, self.dt)
    self._uncert_last = 0.0
    self._uncert_last_t = None

  def update(self, raw_uncertainty, now_t):
    self.uncert_slow.update(float(raw_uncertainty))
    self.uncert_fast.update(float(raw_uncertainty))
    uncertainty = self.uncert_slow.x

    if self._uncert_last_t is None:
      uncert_slope = 0.0
    else:
      dt_u = max(1e-3, float(now_t) - self._uncert_last_t)
      uncert_slope = (uncertainty - self._uncert_last) / dt_u
    self._uncert_last = uncertainty
    self._uncert_last_t = float(now_t)

    uncertainty_accel = min(self.uncert_slow.x, self.uncert_fast.x)
    return uncertainty, uncertainty_accel, float(uncert_slope)


def panic_window_flags(lead, scene_v_ego, scene_desired_gap):
  """(panic_close_window, closing_speed, closing_fast) for the active lead.

  scene_desired_gap must be computed by the caller from the fork's
  desired_follow_distance signature (comfort-brake/stop-distance aware).
  """
  if lead is None or not (bool(getattr(lead, "present", False)) or bool(getattr(lead, "status", False))):
    return False, 0.0, False

  close_gap_window = max(
    UNCERT_PANIC_MAX_GAP_BUFFER_MIN,
    UNCERT_PANIC_MAX_GAP_BUFFER_GAIN * float(scene_v_ego),
  )
  panic_close_window = float(lead.dRel) <= float(scene_desired_gap) + close_gap_window
  closing_speed = max(0.0, float(scene_v_ego) - float(lead.vLead))
  closing_fast = closing_speed >= max(
    UNCERT_PANIC_MIN_CLOSING_SPEED,
    UNCERT_PANIC_MIN_CLOSING_SPEED_GAIN * float(scene_v_ego),
  )
  return bool(panic_close_window), float(closing_speed), bool(closing_fast)


def should_panic_bypass(uncertainty, uncert_slope, panic_close_window, closing_fast):
  """Only bypass comfort smoothing when closing meaningfully and already near
  the follow window. Far or pace-matched leads stay on the smoothed path."""
  return bool(panic_close_window and closing_fast and (
    uncert_slope > UNCERT_SLOPE_TRIG or uncertainty >= UNCERT_MAG_TRIG
  ))


def is_urgent_lead_scenario(lead, v_ego):
  """Raw-lead urgency guard: closing fast inside the physical TTC window means
  the scene is urgent regardless of any duplicate-vision comfort smoothing."""
  if lead is None:
    return False
  closing_speed = max(0.0, float(v_ego) - float(lead.vLead))
  if closing_speed <= UNCERT_MIN_CLOSING_SPEED:
    return False
  d_rel = max(0.0, float(getattr(lead, "dRel", 0.0)))
  ttc = d_rel / max(closing_speed, 1e-3)
  return bool(ttc < UNCERT_MIN_TTC)
