"""Select the newest display points, kept apart from the control tracks.

Ported from carrot. sp's car.RadarData has no `displayPoints`/`hasDisplayData`
(it publishes `points`), so support is established from the liveTracks
subscriber health plus the point freshness gate instead of a support flag.
"""
from dataclasses import dataclass
from math import isfinite, sqrt
import time

import numpy as np

from openpilot.common.constants import CV


DISPLAY_MAX_AGE_S = 0.2
DISPLAY_MAX_POINTS = 20
# Circular slot 12-bit range output. Not a physical sensor capability limit.
DISPLAY_MAX_DISTANCE_M = (4095 - 160) / 16
# Both upstream lateral-flip bounds are kept so the normal boundary survives.
DISPLAY_MIN_LATERAL_M = -2048 * .015
DISPLAY_MAX_LATERAL_M = 2048 * .015
DISPLAY_TRACK_ID_LIMIT = 2**31
# Show level that makes the UI prefer the display-only point array over the
# legacy control lead groups. carrot exposes it as a user setting; here the
# overlay has its own killswitch, so it either draws at this level or not at all.
RADAR_POINTS_LEVEL = 3
# carrot draws the point box this far above the road surface
RADAR_POINT_HEIGHT_M = 0.61
# seconds of travel drawn as the predicted vector for a moving point
RADAR_LAT_FACTOR_S = 0.5
# closer than this a point sits on top of the lead chevron
RADAR_MIN_DRAW_DISTANCE_M = 2.5
# below this combined speed a point is drawn as "*" instead of a speed box
RADAR_MIN_MOVING_SPEED_MS = 3.0



@dataclass(frozen=True)
class RadarDisplayPoint:
  dRel: float
  yRel: float
  vLeadK: float
  vLat: float
  radar: bool = True
  modelProb: float = 0.03


def _finite_float(value):
  try:
    result = float(value)
    return result if isfinite(result) else None
  except (TypeError, ValueError, OverflowError):
    return None


def _fresh(now_s, timestamp_s):
  value = _finite_float(timestamp_s)
  return value is not None and value <= now_s <= value + DISPLAY_MAX_AGE_S


def select_radar_display_points(sm, show_radar_info, *, now=None, started_frame=0):
  """None keeps the previous display; an empty tuple means the supported
  receiver lost points for this frame.

  Only measured front-radar points inside the published range survive. A
  predicted or unresolved value never becomes a displayed vehicle, and a
  duplicate track id makes the whole frame fall back instead of showing a
  possibly wrong point.
  """
  if show_radar_info < 3:
    return None
  try:
    data = sm["liveTracks"]
  except (KeyError, TypeError):
    return None
  # Offline callers may pass a builder; read-only access avoids default assigns.
  as_reader = getattr(data, "as_reader", None)
  if callable(as_reader):
    data = as_reader()

  now_s = _finite_float(time.monotonic() if now is None else now)
  if now_s is None:
    return ()
  # carrot keys this off RadarData.hasDisplayData. sp publishes `points`
  # unconditionally, so the closest honest signal is "has this subscriber ever
  # seen the service": unseen means unknown, so hand back None and let the
  # caller keep the previous fallback instead of clearing a healthy display.
  if not getattr(sm, "seen", {}).get("liveTracks", False):
    return None
  for name in ("alive", "valid"):
    if not getattr(sm, name, {}).get("liveTracks", False):
      return ()
  if getattr(sm, "recv_frame", {}).get("liveTracks", -1) < started_frame:
    return ()
  received_s = getattr(sm, "recv_time", {}).get("liveTracks")
  publication_ns = _finite_float(getattr(sm, "logMonoTime", {}).get("liveTracks"))
  if publication_ns is None or publication_ns <= 0 or not _fresh(now_s, received_s) \
          or not _fresh(now_s, publication_ns * 1e-9):
    return ()
  try:
    if any(data.errors.to_dict().values()) or len(data.points) > DISPLAY_MAX_POINTS:
      return ()
  except (AttributeError, TypeError):
    return ()

  result = []
  identities = set()
  for point in data.points:
    # Predicted / unresolved values must not create a displayed vehicle.
    if not bool(getattr(point, "measured", False)) or str(getattr(point, "radarSource", "")) != "frontRadar":
      continue
    fields = [_finite_float(getattr(point, field, None)) for field in ("dRel", "yRel", "vLead", "yvRel")]
    if any(value is None for value in fields):
      continue
    d_rel, y_rel, v_lead, v_lat = fields
    if not 0 < d_rel <= DISPLAY_MAX_DISTANCE_M or not DISPLAY_MIN_LATERAL_M <= y_rel <= DISPLAY_MAX_LATERAL_M:
      continue
    identity = getattr(point, "trackId", None)
    if isinstance(identity, bool) or not isinstance(identity, int) or identity in identities:
      return ()
    if not 0 <= identity < DISPLAY_TRACK_ID_LIMIT:
      return ()
    identities.add(identity)
    # The parent already applied the left/right flip; use it as-is.
    result.append(RadarDisplayPoint(d_rel, y_rel, v_lead, v_lat))
  return tuple(result)


def path_length_idx(x_array, distance: float) -> int:
  """Last index whose x is at or below `distance` (carrot's helper)."""
  if x_array is None or len(x_array) == 0:
    return 0
  indices = np.where(np.asarray(x_array) <= distance)[0]
  return int(indices[-1]) if indices.size > 0 else 0


def radar_point_z(lane_points, d_rel: float):
  """Road height to draw a point at, or None when there is no lane to sample."""
  if lane_points is None or len(lane_points) == 0:
    return None
  lane = np.asarray(lane_points, dtype=np.float32)
  if lane.ndim != 2 or lane.shape[1] < 3 or lane.shape[0] == 0:
    return None
  idx = path_length_idx(lane[:, 0], d_rel)
  if idx >= lane.shape[0]:
    return None
  return float(lane[idx, 2]) - RADAR_POINT_HEIGHT_M


def combined_speed(v: float, v_lat: float) -> tuple[float, float]:
  """(magnitude, signed magnitude) so a receding point keeps its sign."""
  v_abs = sqrt(v * v + v_lat * v_lat)
  return v_abs, v_abs if v >= 0.0 else -v_abs


def speed_text(v_sum: float, is_metric: bool) -> str:
  """Signed relative speed in display units (m/s to km/h or mph)."""
  factor = CV.MS_TO_KPH if is_metric else CV.MS_TO_MPH
  return f"{(v_sum * factor):.0f}"


def predicted_offset(d_rel: float, y_rel: float, v: float, v_lat: float, t: float = RADAR_LAT_FACTOR_S):
  """Where the point is heading, clamped to stay in front of the car."""
  return max(2.0, d_rel + v * t), y_rel + v_lat * t
