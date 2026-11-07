"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of jetlink and is licensed under the MIT License.
See the LICENSE file in the root directory for more details.

Adaptive pacing: a host that cannot keep 20 Hz gets fewer frames, not holds.

A phone's NPU at full duty cycle heats up, throttles, and then holds most
frames -- each one the host queueing work it answers late anyway. The governor
here reads the hold rhythm the model state already measures and steps the
large model's rate down (20 -> 15 -> 10 Hz) while the host is behind, and back
up after it has kept up for a while. A paced frame sends nothing and runs
nothing on the host: the drive gets the last plan again, which is exactly what
a held frame publishes, minus a frame the host queues.

The steps are self-limiting: a host that keeps up never holds, so it never
steps down -- a Jetson or a Mac runs at 20 Hz forever, and a phone that is
comfortable does too. Paced frames are the governor's own doing, so they never
count toward the hold limits that hand the drive back.

`JETLINK_NO_ADAPTIVE_PACE=1` turns it off and every frame is sent.
"""
from __future__ import annotations

import os
import time
from collections import deque

DISABLE = os.getenv('JETLINK_NO_ADAPTIVE_PACE') == '1'

CAPS = (20.0, 15.0, 10.0)
# held frames running that drop one cap level: a host answering every frame
# late for a seventh of a second is behind, whatever the cause
STEP_DOWN_IN_A_ROW = 3
# held frames inside the window that drop one cap level on their own
STEP_DOWN_HELD = 8
STEP_WINDOW = 5.0
# seconds without a held frame before one level comes back
STEP_UP_QUIET = 10.0


class Governor:
  """The frame rate's cap, stepped by the hold rhythm of the link.

  Not thread-safe: the model state's frame thread owns it, as it owns the
  link. A held frame is `note(True)`; a frame answered on time is
  `note(False)`. `skip` is asked before each frame is prepared.
  """

  def __init__(self, log=None):
    self.log = log
    self._level = 0
    # earliest the next frame may be sent, monotonic; 0 sends at once
    self._next = 0.0
    self._in_a_row = 0
    self._held: deque[float] = deque()
    self._quiet_since: float | None = None
    # frames paced out, for the log line that says the governor is acting
    self.paced = 0

  @property
  def cap(self) -> float:
    """The rate the large model runs at now, frames a second."""
    return CAPS[self._level]

  def skip(self, now: float) -> bool:
    """True when this frame is paced out: nothing is prepared, sent or run on
    the host, and the caller publishes its last output again. At the full 20
    Hz cap this is always False: a camera's frames are the budget themselves,
    and pacing them on jitter would drop frames no host needs dropped."""
    if DISABLE or self._level == 0:
      return False
    if now < self._next:
      self.paced += 1
      return True
    self._next = now + 1.0 / self.cap
    return False

  def note(self, held: bool, now: float | None = None) -> None:
    """A frame's outcome, held or answered on time, from the model state's
    own hold accounting."""
    if DISABLE:
      return
    now = time.monotonic() if now is None else now
    if not held:
      self._in_a_row = 0
      if self._level == 0:
        return
      if self._quiet_since is None:
        self._quiet_since = now
      elif now - self._quiet_since >= STEP_UP_QUIET:
        self._level -= 1
        self._quiet_since = now
        self._say(f"host keeping up, large model back to {self.cap:.0f} Hz")
      return
    self._quiet_since = None
    self._in_a_row += 1
    self._held.append(now)
    while self._held and now - self._held[0] > STEP_WINDOW:
      self._held.popleft()
    behind = self._in_a_row >= STEP_DOWN_IN_A_ROW or len(self._held) >= STEP_DOWN_HELD
    if behind and self._level + 1 < len(CAPS):
      self._level += 1
      self._held.clear()
      self._in_a_row = 0
      # the next frame is already paced: the host just said three times over
      # that it is behind, so it does not get one more it answers late
      self._next = now + 1.0 / self.cap
      self._say(f"host behind, large model paced to {self.cap:.0f} Hz")

  def _say(self, message: str) -> None:
    if self.log is not None:
      self.log.warning("jetlink: %s", message)
