#!/usr/bin/env python3
"""Adjacent-lane stopped-vehicle detector (StarPilot port).

Stop-line hint: a vehicle that decelerated to a stop in a neighbouring lane.
The qualifier is the DECELERATION HISTORY, not the current speed: roadside
furniture and curb-parked cars never show a moving -> stopped transition, so
testing for "anything slow in the next lane" instead would brake early for
parked cars.

Selection takes the FARTHEST qualifying vehicle, then drops the hint entirely
if a queue reaches past it. Cars already stopped when we acquire them never
show the moving -> stopped transition, so the qualifying set is biased toward
the back of a line; without the queue check the hint would mark a mid-queue
bumper and stop us short of the bar.

Pure logic only -- numpy + plain objects, safe to import on a PC host.
"""
import numpy as np

# StarPilot verbatim constants
ADJACENT_STOP_MOVING_V = 5.0      # m/s — must have genuinely been moving
ADJACENT_STOP_REST_V = 1.5        # m/s — and then genuinely at rest
ADJACENT_STOP_MOVING_FRAMES = 15  # 0.75 s at 20 Hz, both ways: rejects speed noise
ADJACENT_STOP_REST_FRAMES = 15
ADJACENT_STOP_MIN_Y = 1.8         # m — inside this is our own lane
ADJACENT_STOP_MAX_Y = 7.5         # m — beyond this is roadside, not an adjacent lane
ADJACENT_STOP_MAX_D = 110.0       # m
ADJACENT_STOP_QUEUE_GAP_M = 5.0   # m — anything stopped beyond the furthest qualifier means
                                  # the bar is past it too, so the hint would stop us short


class AdjacentStopHistory:
  """Per-track moving -> rest frame counters.

  Only sustained runs count, so one noisy speed sample can neither arm nor
  trip the detector. Coasting between the two bands restarts both runs.
  """

  def __init__(self):
    self.moving_frames = 0
    self.rest_frames = 0
    self.seen_moving = False

  def update_history(self, v_lead: float):
    if v_lead > ADJACENT_STOP_MOVING_V:
      self.moving_frames += 1
      self.rest_frames = 0
      if self.moving_frames >= ADJACENT_STOP_MOVING_FRAMES:
        self.seen_moving = True
    elif abs(v_lead) < ADJACENT_STOP_REST_V:
      self.moving_frames = 0
      self.rest_frames += 1
    else:
      self.moving_frames = 0
      self.rest_frames = 0


def in_adjacent_lane(d_rel, y_rel, lane_lines) -> bool:
  """Lane geometry only, no deceleration history — also used to spot a queue.

  lane_lines: (left_x, left_y, right_x, right_y) model lane line arrays.
  Model y == -yRel; laneLines[1] is the left boundary and [2] the right, plus
  an outer bound so roadside returns past the neighbouring lane don't qualify.
  """
  if not (ADJACENT_STOP_MIN_Y < abs(y_rel) < ADJACENT_STOP_MAX_Y):
    return False
  if not (0.0 < d_rel < ADJACENT_STOP_MAX_D):
    return False

  left_x, left_y, right_x, right_y = lane_lines
  model_y = -y_rel
  left_lane = np.interp(d_rel, left_x, left_y)
  right_lane = np.interp(d_rel, right_x, right_y)
  return bool(model_y < left_lane or model_y > right_lane)


def is_adjacent_stopped(track, lane_lines, lead_track_ids=()) -> bool:
  """A neighbouring-lane vehicle that was seen moving and has now come to rest."""
  history = getattr(track, "stop_history", None)
  if history is None or not (history.seen_moving and history.rest_frames >= ADJACENT_STOP_REST_FRAMES):
    return False

  if int(getattr(track, "identifier", -1)) in lead_track_ids:
    return False

  return in_adjacent_lane(float(track.dRel), float(track.yRel), lane_lines)


def detect_adjacent_stopped(tracks, lane_lines, lead_track_ids=()) -> dict:
  """Return {'status': True, dRel, yRel, radarTrackId} for the stop-line hint
  or {'status': False}. Tracks need dRel/yRel/vLead/identifier/stop_history."""
  if lane_lines is None:
    return {"status": False}

  candidates = [c for c in tracks if is_adjacent_stopped(c, lane_lines, lead_track_ids)]
  if not candidates:
    return {"status": False}

  furthest = max(candidates, key=lambda c: float(c.dRel))
  for c in tracks:
    if (float(c.dRel) > float(furthest.dRel) + ADJACENT_STOP_QUEUE_GAP_M and
        abs(float(c.vLead)) < ADJACENT_STOP_REST_V and
        in_adjacent_lane(float(c.dRel), float(c.yRel), lane_lines)):
      return {"status": False}
  return {
    "status": True,
    "dRel": float(furthest.dRel),
    "yRel": float(furthest.yRel),
    "radarTrackId": int(furthest.identifier),
  }
