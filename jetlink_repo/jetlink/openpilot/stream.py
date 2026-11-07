"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of jetlink and is licensed under the MIT License.
See the LICENSE file in the root directory for more details.

Keeping a lossy video stream decodable across the things that break one.

A raw or lossless frame is self-contained: the next one decodes whatever came
before. An HEVC frame is not. It is a P frame predicted from pictures the
receiver already decoded, so a frame that never arrived leaves every frame
after it undecodable until the encoder emits an IDR the receiver can start on.
That is what this module is: the state machine that decides when an IDR is
owed, and the gate that keeps a new stream's first frames honest until it is.

Three things break a stream, and each has one answer:

- **A new connection.** The receiver's decoder is gone, and the frame numbering
  starts again. Every stream therefore opens with an IDR on both cameras, and
  the sender's frame ids restart. `epoch` counts connections so a frame encoded
  under an old one is never submitted to the new: a reconnect that overlaps a
  frame still in the encoder must not hand the receiver a picture from the
  stream it just dropped.

- **A gap.** A frame the receiver will not get (dropped for the queue, too big
  for the link's own limit, or never encoded) invalidates the prediction chain.
  The next frame must be an IDR, and since the two cameras are two encoders,
  both owe one.

- **A keyframe that did not come out.** A request to the encoder is a request,
  not a guarantee. So the gate below does not trust one: it holds a new
  stream's frames until the *actual* keyframe flag is seen on both cameras, and
  drops the ones in between rather than sending them. That is the reference
  fork's head gate (uplink_sender.h, `序列头门`), and it exists because the
  alternative — a receiver that starts mid-GOP — is a decode failure it cannot
  report.

The gate's frames have to be dropped, not delayed: a frame held while the gate
waits is a frame the model would drive on stale, and the receiver has nothing
to decode it against anyway. On a good link the gate costs at most the two
frames between the connection and the second camera's confirmed IDR.

Pure logic, no IO, no numpy: the frame path calls it, and the tests drive every
transition directly.
"""
from __future__ import annotations

from dataclasses import dataclass

# cameras the model's frame carries: narrow and wide. The gate's confirmed-IDR
# rule is per camera, so these are the streams it tracks. A model with one
# camera is one entry
STREAMS = ('road', 'wide')
# GOP of the reference fork's encoder, and the phases the two cameras use:
# road at 0, 20, 40, ... and wide ten frames later, so their I frames never
# land on the same frame and the bitrate spike of two at once is avoided
GOP = 20
WIDE_PHASE = 10


@dataclass
class Step:
  """What the caller must do for one frame, from the state machine.

  The caller reads these after every event and does them in this order: reset
  the encoders if `reset_encoders`, request the IDRs in `request_idr`, then
  send or drop by `send`. Nothing here performs IO, so a test checks the
  decisions without a socket or a codec.

  A request is only ever surfaced by begin(): open() and gap() change the state
  and say so, and the next begin() reports what the encoder now owes. One place
  to read the requests, so a caller cannot act on one return value and miss
  another.
  """
  reset_encoders: bool = False
  request_idr: tuple[str, ...] = ()        # streams the encoder owes an IDR
  send: bool = False                       # this frame may go to the link
  reason: str = ''                         # why not, when send is False

  def __bool__(self) -> bool:
    return bool(self.request_idr or self.send or self.reset_encoders)


class StreamGate:
  """The head gate and the gap state machine, for one connection.

  One per connection: `epoch` is taken from the connection and stamped on every
  frame's decision, so a frame that was in the encoder when the connection
  dropped is refused by the new gate instead of opening it with a picture from
  the old stream.

  The caller drives it in the frame path's own order:

      gate.open(epoch)                     # a connection came up
      step = gate.begin(epoch, frame_id)   # a frame is about to be encoded
      ... encode both cameras ...
      step = gate.confirm(epoch, frame_id, road_idr=..., wide_idr=...)
      ... send, or drop, by step.send ...

  A gap is reported the moment it is known (gate.gap(...)), and it closes the
  gate again: the frames between the gap and the next confirmed pair are
  dropped, which is what keeps a receiver from decoding a token P frame it has
  no references for.
  """

  def __init__(self, streams: tuple[str, ...] = STREAMS, gop: int = GOP, wide_phase: int = WIDE_PHASE):
    self.streams = tuple(streams)
    self.gop = max(1, int(gop))
    self.wide_phase = int(wide_phase)
    self.epoch = 0
    self.open_ = False
    # streams the gate is shut on, waiting for a confirmed IDR. Emptied one
    # stream at a time as confirm() sees the actual keyframe flag
    self._awaiting: set[str] = set()
    # streams with an IDR request outstanding with the encoder. Kept apart from
    # _awaiting so two frames in a row do not ask the encoder twice for the same
    # IDR, and so a periodic GOP IDR is tracked without shutting the gate
    self._requested: set[str] = set()
    # frames dropped between a connection's start and the first frame the gate
    # let through, and the id of that frame
    self.dropped = 0
    self.opened_at: int | None = None
    self.gaps = 0

  # -- connection --------------------------------------------------------------

  def open(self, epoch: int) -> Step:
    """A connection came up, or an old one replaced it. Every stream owes an
    IDR, the encoders are reset (their references are from the old stream and
    the receiver cannot decode against them), and the gate is shut until both
    cameras have actually produced one.

    The IDRs are not returned here: the next begin() reports them (see Step).
    """
    self.epoch = int(epoch)
    self.open_ = True
    self.opened_at = None
    self._awaiting = set(self.streams)
    self._requested = set()
    return Step(reset_encoders=True, send=False, reason='new connection')

  @property
  def is_open(self) -> bool:
    """Has the gate let a frame through on this connection yet?"""
    return self.opened_at is not None

  def awaiting(self) -> tuple[str, ...]:
    """Streams whose confirmed IDR the gate is still waiting for."""
    return tuple(name for name in self.streams if name in self._awaiting)

  # -- the frame path ----------------------------------------------------------

  def begin(self, epoch: int, frame_id: int) -> Step:
    """A frame is about to be encoded. Returns the IDRs the encoder still owes
    (idempotent: a request already outstanding is not repeated), and whether
    the frame may be sent once encoded.

    A frame from another epoch is refused outright: its bytes belong to a
    stream this connection is not.
    """
    if not self.open_ or int(epoch) != self.epoch:
      return Step(send=False, reason=f'stale epoch {epoch} (current {self.epoch})')
    request = self._request_now(frame_id)
    # while the gate is shut, do not send: the frame is kept out of the receiver
    return Step(request_idr=request, send=self.is_open, reason='' if self.is_open else 'gate shut')

  def confirm(self, epoch: int, frame_id: int, **actual: bool) -> Step:
    """The frame's pictures came out of the encoders: `road_idr=`, `wide_idr=`
    (one keyword per stream, named as the stream is). Decides whether this
    frame opens the gate, or is dropped while the gate waits.

    A stream clears when its flag is seen. The gate opens once every stream has,
    and the frame that does it is sent; a frame that satisfies one camera but
    not the other is dropped, which is the point: a receiver with nothing to
    predict from cannot decode it, and sending it only burns the link.
    """
    if not self.open_ or int(epoch) != self.epoch:
      return Step(send=False, reason=f'stale epoch {epoch} (current {self.epoch})')
    for name in self.streams:
      if bool(actual.get(f'{name}_idr')):
        # the encoder honoured it, so the request is no longer outstanding.
        # Cleared for a periodic GOP IDR too, which is requested with the gate
        # already open and would otherwise be asked for again every frame after
        self._requested.discard(name)
        self._awaiting.discard(name)
    if self._awaiting:
      self.dropped += 1
      return Step(send=False, reason='waiting for an IDR on ' + ', '.join(self.awaiting()))
    if self.opened_at is None:
      self.opened_at = int(frame_id)
    return Step(send=True)

  # -- gaps --------------------------------------------------------------------

  def gap(self, why: str = '') -> Step:
    """Frame(s) the receiver will not get: shut the gate and owe IDRs again.

    Called for a frame that will not reach the receiver for a reason other than
    the gate itself (the send queue's own drop, a frame over the link's size
    limit, an encoding that produced nothing). The connection stays up: the
    stream restarts, the link does not. As with open(), the IDRs are reported by
    the next begin().
    """
    if not self.open_:
      return Step(send=False, reason='gate not open')
    self.gaps += 1
    self.opened_at = None
    self._awaiting = set(self.streams)
    self._requested = set()
    return Step(send=False, reason=why or 'stream gap')

  # -- internals ---------------------------------------------------------------

  def _request_now(self, frame_id: int) -> tuple[str, ...]:
    """The streams that owe the encoder an IDR right now: one still awaiting a
    confirmed keyframe and not yet asked, or one at its periodic GOP phase.

    The periodic IDR is what keeps a healthy stream recoverable: road at
    frame 0, 20, 40, ... and wide ten frames later, the reference fork's
    phases, so the two cameras' keyframes never land together and a receiver
    never waits long for one.
    """
    out = []
    for i, name in enumerate(self.streams):
      if name in self._awaiting and name not in self._requested:
        out.append(name)
        self._requested.add(name)
        continue
      if name not in self._awaiting and name not in self._requested:
        phase = 0 if i == 0 else self.wide_phase
        if (int(frame_id) - phase) % self.gop == 0:
          out.append(name)
          self._requested.add(name)
    return tuple(out)
