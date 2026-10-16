"""Shadow consumer for the experimental moving-red prepare / start-guard.

Stage 1 (this module): read the two tmpfs observations that modeld publishes
when SignalAssistMode > 0, and expose whether the pipeline sees a candidate.
It is *observation only* - it never changes v/a targets or the stop flag, so
enabling mode 1 (shadow) cannot affect longitudinal control. Mode 2 (control)
actuation is wired separately, after shadow data validates the geometry.

Kept dependency-free (json/files only) so it is trivially unit-testable and
cannot pull modeld/planner concerns into the longitudinal path.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

PREPARE_OBSERVATION_PATH = Path('/dev/shm/carrot_signal_prepare_observation.json')
START_OBSERVATION_PATH = Path('/dev/shm/carrot_signal_start_observation.json')
MAX_BYTES = 32768


def _read_observation(path: Path) -> dict | None:
  try:
    raw = Path(path).read_bytes()
    if len(raw) > MAX_BYTES:
      return None
    obj = json.loads(raw)
    if obj.get('version') != 1 or obj.get('stream') != 'road':
      return None
    return obj
  except (OSError, ValueError, TypeError):
    return None


def _red_track_present(obs: dict | None) -> bool:
  if not isinstance(obs, dict):
    return False
  for t in obs.get('tracks', ())[:20]:
    if not isinstance(t, dict):
      continue
    raw = str(t.get('raw', '')).lower()
    if raw.startswith('red') or t.get('seen_red'):
      return True
  return False


@dataclass
class SignalShadowState:
  mode: int = 0
  prepare_seen: bool = False
  start_seen: bool = False
  fresh: bool = False


class SignalShadowObserver:
  """Reads prepare/start observations and caches a cheap shadow summary.

  `mode` follows SignalAssistMode (0 off / 1 shadow / 2 control). While mode<2
  every accessor used for actuation returns safe defaults; only the shadow
  counters move, so the longitudinal path is provibly untouched."""

  def __init__(self, prepare_path: Path = PREPARE_OBSERVATION_PATH,
               start_path: Path = START_OBSERVATION_PATH):
    self.prepare_path = Path(prepare_path)
    self.start_path = Path(start_path)
    self.mode = 0
    self._last_mode_read = 0.0
    self._last_log = -1.0
    self.prepare_count = 0
    self.start_count = 0

  def _read_mode(self) -> int:
    now = time.monotonic()
    if now >= self._last_mode_read:
      try:
        from openpilot.sunnypilot.carrot.signal_mode import signal_mode
        self.mode = int(signal_mode())
      except Exception:
        self.mode = 0
      self._last_mode_read = now + 0.5
    return self.mode

  def update(self, now: float | None = None) -> SignalShadowState:
    now = time.monotonic() if now is None else now
    mode = self._read_mode()
    if mode <= 0:
      return SignalShadowState(mode=0)

    prep = _read_observation(self.prepare_path)
    start = _read_observation(self.start_path)
    prepare_seen = _red_track_present(prep)
    start_seen = _red_track_present(start)
    self.prepare_count += int(prepare_seen)
    self.start_count += int(start_seen)
    return SignalShadowState(mode=mode, prepare_seen=prepare_seen,
                             start_seen=start_seen, fresh=bool(prep or start))

  # --- future actuation surface; always safe in this stage -------------- #
  @property
  def control_enabled(self) -> bool:
    """Mode 2 only. Kept false here until the planner seam is wired."""
    return False
