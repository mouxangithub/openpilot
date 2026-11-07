"""Single decision point for which navigation GPS source is currently usable.

Three producers can supply the navigation position and they refresh at
different rates, so freshness is tracked per source instead of one global
timestamp. Priority is fixed: a fresh external-navi fix beats the standalone
phone block, which beats the device's own fused position.

Every source is gated on plausibility (range, not the null island) and on its
own freshness window. A phone fix additionally needs a plausible accuracy,
because a coarse fix anchors the route curvature chain on the wrong segment
without ever reporting an error.

This module is deliberately pure: no Params, no messaging, no clock of its own.
Callers pass the arrival stamp, which keeps the decisions replayable.
"""
from dataclasses import dataclass
import math

# Freshness windows (s) from each producer's last arrival.
WINDOWS = {
  'external_navi': 3.0,
  'phone': 3.0,
  'device': 3.0,
}
# A phone fix worse than this is not trusted as a stand-in.
PHONE_MAX_ACCURACY_M = 15.0
# Navigation never legitimately needs a 324 km/h fix; reject teleports.
MAX_SPEED_MPS = 90.0

PRIORITY = ('external_navi', 'phone', 'device')
# Public names kept stable for the UI/diagnostics contract.
LABELS = {'external_navi': 'navi', 'phone': 'phone', 'device': 'device'}


@dataclass(frozen=True)
class Fix:
  """One source's most recent position, with the time it arrived."""
  lat: float = 0.0
  lon: float = 0.0
  heading: float | None = None  # degrees; None leaves the previous heading
  speed: float = 0.0            # m/s
  accuracy: float = 0.0         # metres; 0 means "not reported"
  stamp: float = -math.inf      # monotonic arrival time


def _finite(value) -> bool:
  return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def plausible(fix: Fix) -> bool:
  """Reject out-of-range coordinates, the null island and teleport speeds."""
  if not (_finite(fix.lat) and _finite(fix.lon) and _finite(fix.speed)):
    return False
  if not (-90.0 <= fix.lat <= 90.0 and -180.0 <= fix.lon <= 180.0):
    return False
  if fix.lat == 0.0 and fix.lon == 0.0:
    return False
  return 0.0 <= fix.speed <= MAX_SPEED_MPS


def fresh(fix: Fix, now: float, source: str) -> bool:
  """True when this source produced a fix inside its own freshness window."""
  if not _finite(now) or not _finite(fix.stamp):
    return False
  age = now - fix.stamp
  return 0.0 <= age <= WINDOWS[source] + 1e-9


def usable(fix: Fix, now: float, source: str) -> bool:
  """Freshness, plausibility and the per-source quality gate."""
  if not (fresh(fix, now, source) and plausible(fix)):
    return False
  if source == 'phone':
    return 0.0 <= fix.accuracy < PHONE_MAX_ACCURACY_M
  return True


def select(fixes: dict[str, Fix], now: float) -> tuple[str, Fix | None]:
  """Return (public source label, fix) for the highest-priority usable source."""
  for source in PRIORITY:
    fix = fixes.get(source)
    if fix is not None and usable(fix, now, source):
      return LABELS[source], fix
  return 'none', None
