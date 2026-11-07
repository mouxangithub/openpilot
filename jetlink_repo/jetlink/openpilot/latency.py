"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of jetlink and is licensed under the MIT License.
See the LICENSE file in the root directory for more details.

Telling a late reply from an answered one, with one number.

The frame path gives up on a reply at a deadline and publishes the previous
output instead (JetlinkModelState.end, the hold). The reply usually still
arrives: a host 2 ms late answers the same frame moments later, and that answer
is read by whatever reads the link next (JetlinkClient.drain). It is *late*,
not lost, and that is the case that matters: a link that is late sometimes is a
link about to start dropping frames, and a link late always is a host that
cannot keep up.

Deciding it with a counter means a window, a threshold and a time bound, and
then arguing about all three. The frame order gives it for free: replies come
back in order, so once the caller has given up on frame N, *no reply with an id
at or below N can ever be on time again*. That is the whole test:

    late  <=>  frame_id <= the highest id the caller has given up on

One integer, no window, no threshold. This is the reference fork's rule
(BigReplyLatch._gave_up_t_eof, one comparison), kept here with frame ids in
place of sensor timestamps, since frame ids are what jetlink's wire already
orders by.

Kept apart from the action: whether to hand back to the small model is the hold
deadline's decision (model_state._note_hold). This counts and classifies, so a
degrading link is visible in the log and in the leave before it starts dropping
frames.
"""
from __future__ import annotations

import time
from collections import deque

# late replies kept, for the rhythm of them: a minute at 20 Hz
KEPT = 1200
# marker for the first late reply, which has no previous one to measure against
_NO_GAP = -1.0


class LateTracker:
  """The watermark, and what it classifies.

  `gave_up(frame_id)` when the frame path stops waiting for a reply, and
  `arrived(frame_id)` when any reply is read, which returns whether it was late.
  `summary()` is what the leave carries and the panels show.
  """

  def __init__(self, kept: int = KEPT):
    self._watermark: int | None = None
    # when each late reply was read, and the frame id it answered
    self._lately: deque[tuple[int, float]] = deque(maxlen=kept)
    # last read time, for the gap to the next: none until one is read
    self._last_at: float | None = None
    # frames given up on and not yet answered: the link's real losses, as
    # opposed to its lateness
    self._outstanding: deque[int] = deque(maxlen=256)
    self.answered = 0
    self.late = 0

  def gave_up(self, frame_id: int) -> None:
    """The caller has stopped waiting for this frame's reply. Everything at or
    below it is late from here on, whatever any clock says."""
    frame_id = int(frame_id)
    if self._watermark is None or frame_id > self._watermark:
      self._watermark = frame_id
    self._outstanding.append(frame_id)

  def arrived(self, frame_id: int, now: float | None = None) -> bool:
    """A reply was read. True when it was late by the watermark rule.

    A reply at or below the watermark is late; one above it was answered within
    its frame's budget, the normal case, and costs one comparison.
    """
    frame_id = int(frame_id)
    self.answered += 1
    if self._watermark is None or frame_id > self._watermark:
      self._last_at = time.monotonic() if now is None else now
      return False
    self.late += 1
    at = time.monotonic() if now is None else now
    self._lately.append((frame_id, at))
    self._last_at = at
    # the frame it belonged to is accounted for, so it is no longer outstanding
    try:
      self._outstanding.remove(frame_id)
    except ValueError:
      pass
    return True

  def settled(self) -> int:
    """Frames the caller gave up on and no reply ever came for: the link's real
    losses, where `late` is its lateness. Read after a batch of replies has been
    taken in; a reply still in flight is neither."""
    return len(self._outstanding)

  @property
  def watermark(self) -> int | None:
    """The highest frame id the caller has given up on, or None before one."""
    return self._watermark

  def summary(self) -> dict:
    """answered, late, settled, and the late replies' own rhythm: how many, and
    the longest and median gap between two of them, in ms.

    Deliberately no latency figure: this sees when a reply was *read*, not when
    its frame started, so any ms it printed would be the reader's lag and not
    the link's. The figures with a clock behind them are model_state.Trips'.
    """
    out = {'answered': self.answered, 'late': self.late, 'settled': self.settled()}
    gaps = self._gaps()
    if gaps:
      ordered = sorted(gaps)
      out.update(late_gap_p50_ms=round(ordered[len(ordered) // 2], 1),
                 late_gap_max_ms=round(ordered[-1], 1))
    return out

  def _gaps(self) -> list[float]:
    """Milliseconds between consecutive late replies: the first is dropped, as
    it has no predecessor. Two read in the same batch are a 0 gap, which is the
    truth of them."""
    at = [t for _, t in self._lately]
    return [(after - before) * 1e3 for before, after in zip(at, at[1:], strict=False)]
