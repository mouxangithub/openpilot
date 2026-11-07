"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of jetlink and is licensed under the MIT License.
See the LICENSE file in the root directory for more details.

The comma side of the frame's own timing: where the frame's 50 ms went before
the server saw any of it. What the server's telemetry cannot see.

The server reports its own stages (INFER_RESP's gpu/queue/total us), and the
comma logs the round trip (model_state.Trips). Neither says which part of the
comma's half a slow frame was: the warp, the send, or waiting on a host that
has gone quiet. On a link that is marginal (a phone over Wi-Fi) that is the
question, and answering it from the round trip alone is guesswork.

So a frame is timed in six stages, each one beginning where the last ended:

    capture     the sensor's read-out -> the frame's turn on the frame thread
    warp        -> the warped frame is ready (openpilot's warp on the GPU)
    send        -> the request is written to the link
    reply_wait  -> the reply is in hand
    publish     -> the outputs are parsed and handed to modeld
    overhead    the rest of the frame, to the next frame's own start

The six sum to the frame period (the next frame's start minus this one's), so
a gap between frames shows up as overhead rather than vanishing. A stage a link
does not have reports 0: there is no encode before the frame is warped, and no
hold before there is an output to hold.

This is the reference fork's six-stage ring (frame_stages.h) in the shape
jetlink's frame path actually has: jetlink's seams are prepare/send/end, where
the reference's are capture/warp/pair/encode/send/reply. The ring is keyed on
the frame id, so a late event for a frame the ring has since reused is dropped
rather than corrupting a newer frame's numbers.

Pure logic, no IO: the frame loop fills it, the status reader summarises it,
and the tests drive it directly.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from statistics import median

# stages, in the order a frame goes through them. A name is also a column of
# the summary and a field of StageMs, so adding one is additive
STAGES = ('capture', 'warp', 'send', 'reply_wait', 'publish', 'overhead')
# how many frames the ring holds: a minute at 20 Hz
RING = 1200


def percentile(values: list[float], frac: float) -> float:
  """The nearest-rank percentile of `values`: no interpolation, so a number in
  the answer is always a number that was measured. 0.0 on an empty list."""
  if not values:
    return 0.0
  ordered = sorted(values)
  return ordered[max(0, min(int(frac * (len(ordered) - 1)), len(ordered) - 1))]


@dataclass
class StageMs:
  """One frame's six stages, in ms. A stage a link does not have is 0."""
  capture: float = 0.0
  warp: float = 0.0
  send: float = 0.0
  reply_wait: float = 0.0
  publish: float = 0.0
  overhead: float = 0.0

  @property
  def total_ms(self) -> float:
    """The whole frame, the six summed: the frame period they were measured over."""
    return self.capture + self.warp + self.send + self.reply_wait + self.publish + self.overhead

  def as_dict(self) -> dict[str, float]:
    return {name: round(getattr(self, name), 2) for name in STAGES}


@dataclass
class _Frame:
  """A frame being timed. Each stamp is a monotonic second, None until set: 0.0
  is a legitimate stamp (a clock started at boot), so it cannot also mean unset."""
  frame_id: int
  t_frame: float = 0.0       # the frame thread took it up
  t_eof: float | None = None  # the sensor's read-out, on the same clock
  t_captured: float | None = None
  t_warped: float | None = None
  t_sent: float | None = None
  t_replied: float | None = None
  t_published: float | None = None


class FrameStages:
  """The comma's six stages, per frame, in a ring.

  One writer (the frame loop) and any number of readers (the status snapshot,
  the leave's summary), so every public method is safe to call from either.
  The frame loop's cost is a handful of float assignments a frame.
  """

  def __init__(self, ring: int = RING):
    self.ring = max(1, int(ring))
    self._slots: list[_Frame | None] = [None] * self.ring
    # the finished frames, oldest first, as (stages, held). The stages are kept
    # rather than the id: the ring reuses ids, and a summary must never count a
    # reused id's numbers twice
    self._done: deque[tuple[StageMs, bool]] = deque(maxlen=self.ring)
    # The running sum per stage, over the frames the ring holds, so a reader
    # that only wants the mean does not walk the ring: the modeld record is
    # written once a second and must not sort 1200 frames to say what it costs.
    self._sum = [0.0] * len(STAGES)
    self._held = 0

  # -- the frame loop ---------------------------------------------------------

  def start(self, frame_id: int, now: float, t_eof: float | None = None) -> None:
    """A frame begins: the frame thread has taken it up. `t_eof` is the
    camera's timestamp for it on the same monotonic clock, when there is one;
    the capture stage is measured from it, so the sensor's own read-out delay is
    in the numbers rather than invisible."""
    self._slots[frame_id % self.ring] = _Frame(frame_id=frame_id, t_frame=now, t_eof=t_eof)

  def captured(self, frame_id: int, now: float) -> None:
    self._at(frame_id, 't_captured', now)

  def warped(self, frame_id: int, now: float) -> None:
    self._at(frame_id, 't_warped', now)

  def sent(self, frame_id: int, now: float) -> None:
    self._at(frame_id, 't_sent', now)

  def replied(self, frame_id: int, now: float) -> None:
    self._at(frame_id, 't_replied', now)

  def finished(self, frame_id: int, now: float, held: bool = False) -> StageMs | None:
    """The frame is over: fill in what is left and return its stages, or None
    for a frame the ring has already reused (its stamps are another frame's).
    `held` records that the reply was late and the previous output published."""
    slot = self._find(frame_id)
    if slot is None:
      return None
    if slot.t_published is None:
      slot.t_published = now
    stages = self._stages(slot, now)
    # the ring drops its oldest when it is full; the sum has to drop it too, or
    # `means` counts a frame the ring no longer holds
    if len(self._done) == self._done.maxlen:
      old, was_held = self._done[0]
      for i, name in enumerate(STAGES):
        self._sum[i] -= getattr(old, name)
      self._held -= 1 if was_held else 0
    self._done.append((stages, bool(held)))
    for i, name in enumerate(STAGES):
      self._sum[i] += getattr(stages, name)
    self._held += 1 if held else 0
    self._slots[frame_id % self.ring] = None
    return stages

  def reset(self) -> None:
    """Forget every frame: a new connection, whose frame ids start again."""
    self._slots = [None] * self.ring
    self._done.clear()
    self._sum = [0.0] * len(STAGES)
    self._held = 0

  # -- readers -----------------------------------------------------------------

  def last(self) -> StageMs | None:
    """The most recent finished frame's stages, None before one has finished."""
    return self._done[-1][0] if self._done else None

  def means(self) -> dict:
    """Each stage's mean in ms over the frames the ring holds, and the frame
    total's, in O(1): what a record written once a second can afford, where
    `summary`'s percentiles want a sort. An empty ring is `{'frames': 0}`."""
    count = len(self._done)
    if count == 0:
      return {'frames': 0}
    out: dict = {'frames': count, 'held': self._held}
    for i, name in enumerate(STAGES):
      out[name] = round(self._sum[i] / count, 2)
    out['frame'] = round(sum(self._sum) / count, 2)
    return out

  def summary(self, window: int = RING) -> dict:
    """The last `window` finished frames, summarised; safe before any has.

    Per stage, p50 and p95 in ms, and the frame total's the same, over the
    frames the ring still holds. Enough to say which stage a slow link spends
    its time in, which is the whole point; the raw per-frame numbers stay on
    the comma.
    """
    frames = list(self._done)[-max(1, int(window)):]
    stages = [s for s, _ in frames]
    out: dict = {'frames': len(stages), 'held': sum(1 for _, held in frames if held)}
    for name in STAGES:
      values = [getattr(s, name) for s in stages]
      out[name] = {'p50_ms': round(percentile(values, 0.50), 2), 'p95_ms': round(percentile(values, 0.95), 2)}
    totals = [s.total_ms for s in stages]
    out['frame'] = {'p50_ms': round(percentile(totals, 0.50), 2), 'p95_ms': round(percentile(totals, 0.95), 2)}
    return out

  # -- internals ---------------------------------------------------------------

  def _at(self, frame_id: int, attr: str, now: float) -> None:
    """Stamp a stage once: a repeated event for a frame keeps the first, which
    is the one the stage's start is."""
    slot = self._find(frame_id)
    if slot is not None and getattr(slot, attr) is None:
      setattr(slot, attr, now)

  def _find(self, frame_id: int) -> _Frame | None:
    slot = self._slots[frame_id % self.ring]
    return slot if slot is not None and slot.frame_id == frame_id else None

  def _stages(self, slot: _Frame, now: float) -> StageMs:
    """The six stages of `slot`, each clipped at 0: a stamp missing or out of
    order reads as 0 rather than as a negative that would wreck a median. A
    missing start falls back to the frame's own start, so a stage the caller
    never stamped is folded into the next rather than lost."""

    def gap(a: float | None, b: float | None) -> float:
      if a is None or b is None or b < a:
        return 0.0
      return (b - a) * 1e3

    start = slot.t_frame
    captured = slot.t_captured if slot.t_captured is not None else start
    eof = slot.t_eof if slot.t_eof is not None else start
    return StageMs(
      capture=gap(eof, captured),
      warp=gap(captured, slot.t_warped),
      send=gap(slot.t_warped, slot.t_sent),
      reply_wait=gap(slot.t_sent, slot.t_replied),
      publish=gap(slot.t_replied, slot.t_published),
      overhead=gap(slot.t_published, now),
    )


class StageTracker:
  """A bounded rolling view of the stages, for the leave and the log.

  FrameStages keeps the ring; this keeps the totals of the last few hundred
  frames, so a link that degrades mid-drive says so in one number rather than
  only in a scrolling log. Deliberately the same shape as model_state.Trips:
  the two are read together and a reader should not have to hold two idioms.
  """

  def __init__(self, kept: int = 300):
    self._frames: deque[StageMs] = deque(maxlen=kept)

  def record(self, stages: StageMs | None) -> None:
    if stages is not None:
      self._frames.append(stages)

  def summary(self) -> dict:
    """Per stage, med and max ms over the frames kept, and the frame total's."""
    if not self._frames:
      return {'frames': 0}
    out: dict = {'frames': len(self._frames)}
    for name in STAGES:
      values = [getattr(s, name) for s in self._frames]
      out[name] = {'med_ms': round(median(values), 2), 'max_ms': round(max(values), 2)}
    totals = [s.total_ms for s in self._frames]
    out['frame'] = {'med_ms': round(median(totals), 2), 'max_ms': round(max(totals), 2)}
    return out
