"""Advisory UI read of the YOLO traffic-light observer. Display only.

The observer (``openpilot.selfdrive.modeld.signal_yolo_shadow``) writes a
self-describing JSON record to tmpfs. This module is the UI's bounded reader:
it re-checks the permission fields the producer stamped, drops anything stale
or oversized, and returns the record for a fresh observation — nothing more.
It never feeds the planner, the arbiters or any control helper; the consumer
(the signal HUD renderer) draws a dot, that is all.
"""
import json
import time
from pathlib import Path

from openpilot.selfdrive.modeld.signal_yolo_shadow import (
  ENABLE_PATH, MAX_OBSERVATION_BYTES, OBSERVATION_PATH,
)

# The producer's cadence on a comma 3 is ~1.6 s (a ~400 ms little-core forward
# plus the duty floor) and faster on a comma 3X; a 3.5 s window rides out a
# couple of dropped frames without showing a light that has long left view.
UI_MAX_AGE = 3.5
# Colours the HUD can show; housings without agreed colour stay silent.
UI_STATES = ('red', 'green')

_observer_requested_cache: tuple[float, bool] = (0., False)


def observer_requested(now: float | None = None, path: Path | None = None) -> bool:
  """The observer's own opt-in, read at most twice a second. Mirrors the
  producer's gate: the SignalYoloEnabled settings toggle OR the legacy CLI file.
  The file check stays uncached so a CLI toggle-off shows up immediately; only
  the param read is cached."""
  global _observer_requested_cache
  now = time.monotonic() if now is None else now
  cached_at, cached = _observer_requested_cache
  if now < cached_at:
    return cached
  try:
    file_value = Path(path or ENABLE_PATH).read_text().strip() == '1'
  except OSError:
    file_value = False
  if file_value:
    value = True
  else:
    try:
      from openpilot.common.params import Params
      value = Params().get_bool('SignalYoloEnabled')
    except Exception:
      value = False
  _observer_requested_cache = (now + .5, value)
  return value


def ui_observation(now: float | None = None, path: Path = OBSERVATION_PATH,
                   max_age: float = UI_MAX_AGE) -> dict | None:
  """A fresh, permission-checked observation record, else None.

  Mirrors the producer's stamps: version, comparison-only mode, no control
  permission, bounded age. ``prediction`` is the single agreed colour across
  the observed housings, or ``unknown``.
  """
  now = time.monotonic() if now is None else now
  try:
    with Path(path).open('rb') as f:
      raw = f.read(MAX_OBSERVATION_BYTES + 1)
    if len(raw) > MAX_OBSERVATION_BYTES:
      return None
    record = json.loads(raw)
    if (record['version'] != 1 or record['mode'] != 'camera_comparison_only'
        or record['control_permission'] is not False
        or record.get('stream') != 'road'
        or not isinstance(record.get('session'), str)
        or not isinstance(record.get('tracks'), list)
        or not 0 <= now - record['timestamp'] <= max_age):
      return None
    return record
  except (OSError, ValueError, TypeError, KeyError):
    return None


class YoloObservationReader:
  """Throttled UI-side reader: at most 5 Hz of file reads, off when unrequested."""

  def __init__(self, path: Path = OBSERVATION_PATH):
    self.path = Path(path)
    self.record: dict | None = None
    self._next_read = 0.

  def read(self, now: float | None = None) -> dict | None:
    now = time.monotonic() if now is None else now
    if not observer_requested(now):
      self.record = None
      return None
    if now >= self._next_read:
      self._next_read = now + .2
      self.record = ui_observation(now, self.path)
    return self.record
