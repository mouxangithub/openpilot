#!/usr/bin/env python3
"""Near-duplicate lead detection and source hysteresis (StarPilot port).

Radarless/model-fused stacks often expose the same physical car as both
leadOne and leadTwo (vision + radar duplicates, or twin vision tracks).
Flipping the MPC source between near-duplicates makes the plan jump between
two nearly identical obstacle profiles every time the argmin flips. This
module detects near-duplicate pairs and provides:

- source hysteresis: bias the *other* lead's obstacle so the tracked source
  sticks until the duplicate genuinely becomes the better follow target.
- identical-radar source hold: when both leads share one radar track, keep
  the previous source while the two obstacle profiles stay close.

Pure logic only -- no Params, no swaglog, safe to import and unit-test on a
PC host.
"""
import numpy as np

from openpilot.common.filter_simple import FirstOrderFilter

# StarPilot verbatim constants (subset used by this fork's two-lead argmin;
# cruise-source holds/biases require the three-source arbiter and are not
# ported).
NEAR_DUPLICATE_LEAD_SOURCE_MIN_SPEED = 4.0
NEAR_DUPLICATE_IDENTICAL_RADAR_SOURCE_MIN_SPEED = 10.0
NEAR_DUPLICATE_LEAD_SOURCE_MIN_MODEL_PROB = 0.9
NEAR_DUPLICATE_LEAD_SOURCE_MAX_LEAD_BRAKE = 0.35
NEAR_DUPLICATE_LEAD_SOURCE_MAX_DREL_DIFF = 1.5
NEAR_DUPLICATE_LEAD_SOURCE_MAX_VREL_DIFF = 0.35
NEAR_DUPLICATE_LEAD_SOURCE_HYSTERESIS_MIN = 1.25
NEAR_DUPLICATE_LEAD_SOURCE_HYSTERESIS_MAX = 2.25
NEAR_DUPLICATE_IDENTICAL_RADAR_SOURCE_KEEP_MARGIN = 0.35

# Comfort smoothing time for a qualified non-urgent duplicate vision follow
DUPLICATE_VISION_LEAD_FILTER_TIME = 0.15


def _lead_status(lead) -> bool:
  # radarState leads expose `present`; some hosts/tests use `status`.
  return bool(getattr(lead, "present", False)) or bool(getattr(lead, "status", False))


def leads_share_identical_radar_track(lead_one, lead_two) -> bool:
  if lead_one is None or lead_two is None:
    return False
  track_one = int(getattr(lead_one, "radarTrackId", -1))
  track_two = int(getattr(lead_two, "radarTrackId", -1))
  return track_one >= 0 and track_one == track_two


def leads_are_near_duplicates(lead_one, lead_two, v_ego, *, vision_min_speed=None) -> bool:
  if lead_one is None or lead_two is None or not _lead_status(lead_one) or not _lead_status(lead_two):
    return False
  if leads_share_identical_radar_track(lead_one, lead_two):
    if float(v_ego) < NEAR_DUPLICATE_IDENTICAL_RADAR_SOURCE_MIN_SPEED:
      return False
    return (
      abs(float(lead_one.dRel) - float(lead_two.dRel)) <= NEAR_DUPLICATE_LEAD_SOURCE_MAX_DREL_DIFF and
      abs(float(lead_one.vRel) - float(lead_two.vRel)) <= max(1.0, NEAR_DUPLICATE_LEAD_SOURCE_MAX_VREL_DIFF)
    )
  min_vision_speed = NEAR_DUPLICATE_LEAD_SOURCE_MIN_SPEED if vision_min_speed is None else float(vision_min_speed)
  if float(v_ego) < min_vision_speed:
    return False
  lead_one_radar = bool(getattr(lead_one, "radar", False))
  lead_two_radar = bool(getattr(lead_two, "radar", False))
  if lead_one_radar or lead_two_radar:
    return False
  if float(getattr(lead_one, "modelProb", 0.0)) < NEAR_DUPLICATE_LEAD_SOURCE_MIN_MODEL_PROB:
    return False
  if float(getattr(lead_two, "modelProb", 0.0)) < NEAR_DUPLICATE_LEAD_SOURCE_MIN_MODEL_PROB:
    return False
  if max(0.0, -float(getattr(lead_one, "aLeadK", 0.0))) > NEAR_DUPLICATE_LEAD_SOURCE_MAX_LEAD_BRAKE:
    return False
  if max(0.0, -float(getattr(lead_two, "aLeadK", 0.0))) > NEAR_DUPLICATE_LEAD_SOURCE_MAX_LEAD_BRAKE:
    return False

  return (
    abs(float(lead_one.dRel) - float(lead_two.dRel)) <= NEAR_DUPLICATE_LEAD_SOURCE_MAX_DREL_DIFF and
    abs(float(lead_one.vRel) - float(lead_two.vRel)) <= NEAR_DUPLICATE_LEAD_SOURCE_MAX_VREL_DIFF
  )


def near_duplicate_lead_source_hysteresis(prev_source, lead_one, lead_two, v_ego):
  """Obstacle bias pair (lead0_bias, lead1_bias) keeping prev_source sticky.

  The tracked source gets no bias; the near-duplicate other lead gets a
  speed-interpolated hysteresis margin so the argmin does not flip-flop.
  """
  if prev_source not in ("lead0", "lead1"):
    return 0.0, 0.0
  if not leads_are_near_duplicates(lead_one, lead_two, v_ego):
    return 0.0, 0.0

  hysteresis = float(np.interp(
    float(v_ego),
    [NEAR_DUPLICATE_LEAD_SOURCE_MIN_SPEED, 35.0],
    [NEAR_DUPLICATE_LEAD_SOURCE_HYSTERESIS_MIN, NEAR_DUPLICATE_LEAD_SOURCE_HYSTERESIS_MAX],
  ))
  if prev_source == "lead0":
    return 0.0, hysteresis
  return hysteresis, 0.0


def identical_radar_duplicate_source_hold(prev_source, lead_one, lead_two,
                                          lead_0_obstacle, lead_1_obstacle):
  """Keep prev_source while both leads share one radar track and their
  obstacle profiles (current-frame) stay within the keep margin."""
  if prev_source not in ("lead0", "lead1"):
    return None
  if not leads_share_identical_radar_track(lead_one, lead_two):
    return None
  if abs(float(lead_0_obstacle) - float(lead_1_obstacle)) > NEAR_DUPLICATE_IDENTICAL_RADAR_SOURCE_KEEP_MARGIN:
    return None
  return prev_source


class DuplicateVisionLeadFilters:
  """Per-lead comfort filters for a qualified non-urgent duplicate-vision follow.

  Mirrors StarPilot's duplicate_lead_*_filters: a ratcheted distance filter
  (never lets the smoothed distance fall behind a new closer measurement --
  closers pass through instantly) plus plain first-order filters for speed and
  accel. `invalidate()` returns to the raw path so leaving the narrow comfort
  scene cannot introduce a state discontinuity.
  """

  def __init__(self, dt):
    self.dt = float(dt)
    self.x_filters = [FirstOrderFilter(0.0, 0.0, self.dt, initialized=False) for _ in range(2)]
    self.a_filters = [FirstOrderFilter(0.0, 0.0, self.dt, initialized=False) for _ in range(2)]
    self.v_filters = [FirstOrderFilter(0.0, 0.0, self.dt, initialized=False) for _ in range(2)]

  def invalidate(self, lead_index=None):
    filters = (self.x_filters, self.a_filters, self.v_filters)
    if lead_index is None:
      for group in filters:
        for f in group:
          f.initialized = False
    else:
      for group in filters:
        group[lead_index].initialized = False

  def apply(self, lead_index, x_lead, v_lead, a_lead):
    """Smooth a duplicate-vision lead measurement. Returns (x, v, a)."""
    x_filter = self.x_filters[lead_index]
    a_filter = self.a_filters[lead_index]
    v_filter = self.v_filters[lead_index]
    for f in (x_filter, a_filter, v_filter):
      f.update_alpha(DUPLICATE_VISION_LEAD_FILTER_TIME)
    # Ratchet: a suddenly closer distance must never be smoothed away.
    if x_filter.initialized and x_lead <= x_filter.x:
      x_filter.x = x_lead
    else:
      x_filter.update(x_lead)
    x_out = x_filter.x
    a_out = a_filter.update(a_lead)
    v_out = v_filter.update(v_lead)
    return float(x_out), float(v_out), float(a_out)
