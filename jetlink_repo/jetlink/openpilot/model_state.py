"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of jetlink and is licensed under the MIT License.
See the LICENSE file in the root directory for more details.

A ModelState whose policy runs on the Jetson.

Everything that touches the car stays on the comma: cameras, calibration, the
warp, the parser, controlsd, panda, CAN. The Jetson is a pure function, warped
frames and context in, 18452 floats out, and holds no control state.

The split is at `run_policy`. The warp stays on the comma's GPU: its input is a
2 MB camera buffer already there and its output the 393 KB the link carries
anyway. The history queues live on the Jetson, shipping them would cost ~10 MB
a frame instead of ~0.5 MB. modeld runs its warp as a JIT of its own, and
the link runs the same one; see warp.

A model that keeps its own history (openpilot #38916, Cinque Terre V3 on)
takes the same warped frame and the same scalars; its hidden state never
leaves the Jetson, so there is no prev_feat to send back. The spec says which.

What openpilot's modeld reads off a ModelState comes from the fork's adapter
(ModelFace): comma's constants, parser, smoothing and action function.
tinygrad is warp.Warp's to import: only modeld has it.
"""
from __future__ import annotations

import os
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from jetlink import codecs, hevc
from jetlink.openpilot import stream as stream_mod
from jetlink.openpilot.latency import LateTracker
from jetlink.openpilot.pace import Governor
from jetlink.openpilot.stages import FrameStages as StageStages
from jetlink.protocol import NotFinite


class NotReady(RuntimeError):
  """This frame has no output to publish, and no link failure to blame.

  An HEVC stream opens with frames withheld until both cameras have produced a
  keyframe (stream.StreamGate), and for the first of them there is no earlier
  output to publish again either. That is a frame the small model must run, and
  nothing more: the stream is coming up, not failing.

  Distinct from a NotFinite, which is a host that answered wrongly and hands the
  drive back; a caller that catches this runs the small model for one frame and
  keeps the link.
  """
  retryable = True

SEND_RAW_PRED = os.getenv('SEND_RAW_PRED')
SLOW_FRAME = 0.05  # the full 20 Hz budget, not just the largest outliers
# How far into a frame end() waits for the reply before publishing the
# previous frame's output again (a held frame). Past this the camera frame
# would be dropped: modeld's own work around run() takes the rest of the 50 ms.
# A held frame is a plan one frame old, which the 10 s plan and the actuator
# delay both dwarf, where a dropped frame is the same stale plan plus a count
# toward selfdrived's modeldLagging. None waits the client's full deadline
HOLD_FRAME = 0.046
# Held frames the large model may make before it is behind rather than
# tailing: this many in a row, or more than HOLDS_ALLOWED within HOLD_WINDOW.
# A host at 40 ms a frame with a tail past 46 (an iPhone) holds a few frames
# in a hundred, each a plan one frame old; one at 60 ms holds every frame.
# More in a row than the client's deadline (link.INFERENCE_TIMEOUT, 0.2 s)
# lets a quiet host run to, so a run of holds is always a host that answers,
# late; one that has stopped answering fails the link first
# (JetlinkClient.infer_begin), as a lost link
HOLDS_IN_A_ROW = 5
HOLDS_ALLOWED = 20
HOLD_WINDOW = 10.0
# The first frames after a swap, which the fork holds engagement off for (a
# second at 20 Hz): a single held frame among them is behind. A host cold from
# a reconnect proves itself here, before anyone can engage, rather than at the
# wheel, where a slow host's return is a soft disable within a second
PROVING_FRAMES = 20
# the first of them never hand back, held or not: the first after a join
# carries the history reset, and a Mac's is ~100 ms of CoreML warm-up. A
# single slow frame later is the comma's own stall, a warp or a send, which
# handing back would not fix; only held frames say the host is behind
SETTLING_FRAMES = 3
# A phone's NPU runs the inference at ~33-43 ms; with the Wi-Fi round trip
# and the comma's own warp/send (~5 ms) a frame's wait is ~45 ms, right at the
# 20 Hz budget. The USB-tuned 46 ms hold leaves only ~41 ms after that work, so
# a phone behind either link holds most frames. These link-specific budgets let
# the large model stay swapped on a phone without weakening the strict defaults
# a fast Jetson/Mac keeps. A held frame still publishes the previous output
# (a plan one frame old), not a dropped camera frame; the 0.2 s client deadline
# and modeld's camera-drop filter hand back on a real stall.
#
# Over the USB cable (usb/ios): the CDC-NCM link adds almost no network time,
# but the same phone NPU does, so a modestly wider hold and a tolerant proof.
CABLE_HOLD_FRAME = 0.05
CABLE_SETTLING_FRAMES = 5
CABLE_HOLDS_IN_A_ROW = 10
CABLE_HOLDS_ALLOWED = 80
# Over Wi-Fi: a 55 ms wait window covers the measured ~45 ms reply; more
# settling frames and a wider steady-state tolerance for marginal holds.
WIFI_HOLD_FRAME = 0.055
WIFI_SETTLING_FRAMES = 8
WIFI_HOLDS_IN_A_ROW = 15
WIFI_HOLDS_ALLOWED = 150
# frames between asks for the server's telemetry, which rides on the response:
# every second one, as modeld sent a chestnut's state (20 Hz over 10 Hz)
TELEMETRY_EVERY = 2
# telemetry goes to the log at most this often
TELEMETRY_PERIOD = 1.0
# frames Trips keeps the timings of: a minute at 20 Hz
TRIPS_KEPT = 1200


class Trips:
  """What the comma measures of its frames over the link: the whole run, warp
  to parsed output, which is the frame as modeld waits on it, against the
  server's own total, which is all the server can see. Summarised for the
  leave (JetlinkClient.leave), so a phone's log carries the half of the frame
  budget it cannot measure. Bounded to the last TRIPS_KEPT frames."""

  def __init__(self):
    self.frames = 0          # frames waited for and published
    self.over = 0            # frames past SLOW_FRAME, the whole 20 Hz budget
    self.held = 0            # frames whose reply was late and published the previous one
    self.started = time.monotonic()
    self._whole_ms: deque[float] = deque(maxlen=TRIPS_KEPT)
    self._server_ms: deque[float] = deque(maxlen=TRIPS_KEPT)

  def record(self, whole_s: float, server_us: int) -> None:
    self.frames += 1
    if whole_s > SLOW_FRAME:
      self.over += 1
    self._whole_ms.append(whole_s * 1e3)
    self._server_ms.append(server_us / 1e3)

  def summary(self) -> dict:
    """frames, over, held, span_s, and over the frames kept: p50_ms, p99_ms,
    max_ms of the whole frame and server_ms, the server's mean total."""
    out = {'frames': self.frames, 'over': self.over, 'held': self.held,
           'span_s': round(time.monotonic() - self.started, 1)}
    if self._whole_ms:
      whole = sorted(self._whole_ms)
      out.update(p50_ms=round(whole[len(whole) // 2], 1), p99_ms=round(whole[int(0.99 * (len(whole) - 1))], 1),
                 max_ms=round(whole[-1], 1), server_ms=round(sum(self._server_ms) / len(self._server_ms), 1))
    return out


@dataclass
class Frame:
  """One frame on its way to the host: when its warp started, was launched
  and finished, then its seq and send time once sent. The bytes are the
  warp's output (Warp.output)."""
  t0: float
  t1: float
  t2: float
  seq: int | None = None
  sent: float = 0.0
  telemetry: bool = False


class JetlinkModelState:
  """Duck-types openpilot's modeld ModelState, and modeld_v2's where it differs.

  The small model is whatever bundle the user picked, on whichever modeld that
  bundle needs. sunnypilot's modeld_v2 reads constants, smoothing and the
  action function off the ModelState; stock modeld has them as module
  constants. This is comma's large model, so they are comma's.

  A frame is prepare(), send() and end(); run() is all three, as modeld calls
  it. The joining model (joining.JoiningModelState) reads `behind` after each
  frame.
  """

  prev_desire: np.ndarray  # for tracking the rising edge of the pulse

  def __init__(self, client, spec, warp, *, face, log, event,
               hold_frame: float | None = None, settling_frames: int | None = None,
               holds_in_a_row: int | None = None, holds_allowed: int | None = None,
               proving_holds_fatal: bool = True, stages: object | None = None,
               late: object | None = None, pace: bool = False):
    self._log = log
    # Per-link overrides. None means "read the module constant each frame", so
    # the strict USB/Jetson defaults stay live constants the tests can mock and
    # a Wi-Fi/USB phone build pins a wider value at construction (see joining).
    self._hold_frame_override = hold_frame
    self._settling_frames_override = settling_frames
    self._holds_in_a_row_override = holds_in_a_row
    self._holds_allowed_override = holds_allowed
    # USB: any held frame in the proof window proves the host too slow. Over
    # Wi-Fi a phone NPU sits right at the frame budget and holds most frames by
    # a millisecond or two (still a fresh-enough, one-frame-old plan), so the
    # proof uses the steady-state rules (a run of holds / too many holds); only
    # a genuinely stalling host hands back.
    self._proving_holds_fatal = bool(proving_holds_fatal)
    # (name, **fields): a structured log line, cloudlog.event on a comma
    self._event = event
    self.face = face
    # the joining model sets it from the small model before the first frame,
    # and modeld writes it every frame after
    self.lat_delay = 0.0
    self.constants = face.constants
    self.LAT_SMOOTH_SECONDS = face.lat_smooth_seconds
    self.LONG_SMOOTH_SECONDS = face.long_smooth_seconds
    self.PLANPLUS_CONTROL = 1.0
    self.get_action_from_model = face.get_action_from_model

    self.client = client
    self.spec = spec
    # not chestnut hardware, but the same role: modelV2.big, the UI and the
    # model manager key off this flag
    self.chestnut = True

    # a warp.Warp or the adapter's model_warp, loaded and warmed ahead: its
    # first call links the JIT, and this runs on modeld's frame thread. Frames
    # go out of its output as they are, over either transport
    self.warp = warp

    # a lossless warp's errors go packed to a server that takes them
    # (jetlink.lossless): half the bytes of the frame, for Wi-Fi
    self._packer = None
    if getattr(warp, 'errors', None) is not None and getattr(client, 'takes_lossless', False):
      from jetlink.lossless import Packer
      self._packer = Packer(spec.warped_shape)

    # an HEVC link's two encoders and its gate (jetlink.hevc, stream): the
    # frame path encodes instead of sending the warped bytes, and the gate
    # decides when a keyframe is owed. Built only where the server listed the
    # codec and the caller chose it (client.codec, codecs.pick)
    self._hevc = None
    self._gate = None
    self._metas = None
    self._epoch = 0
    if getattr(client, 'codec', None) == codecs.HEVC and getattr(client, 'takes_hevc', False):
      self._build_hevc(spec)

    # the frame rate's governor, on phone hosts only (joining passes pace for
    # wifi and cable-to-phone links): a host that falls behind (its holds) is
    # sent fewer frames instead of work it answers late, and paced frames are
    # never counted toward the hold limits that hand the drive back (pace.py)
    self._pace = Governor(log=self._log) if pace else None

    self.input_shapes = spec.input_shapes
    self.output_slices = spec.output_slices
    # from the spec, not ModelConstants: the server derives its history stride
    # from the same field
    self.frame_skip = spec.frame_skip

    # compile_modeld.make_input_queues' packed_npy_inputs, minus the warp's
    # inputs and the GPU queues the server owns; for a stateful graph, minus
    # prev_feat too
    self.packed = np.zeros(spec.packed_nelem, dtype=np.float32)
    self.npy = {k: self.packed[at].reshape(shape) for k, (at, shape) in spec.packed_layout.items()}

    self.prev_desire = np.zeros(face.desire_len, dtype=np.float32)
    self.parser = face.parser()
    # the camera buffers modeld hands over, whatever the graph calls its inputs
    self.vision_input_names = ['img', 'big_img']
    self._need_reset = True
    self._frame_id = 0
    self._last_logged = 0.0
    self._last_hold_logged = 0.0
    # when the comma last told the host its own six stages (report_stages)
    self._stages_reported = 0.0
    self.trips = Trips()
    # The comma's own six stages (stages.FrameStages): where the frame's half of
    # the budget went, which neither the server's telemetry nor the round trip
    # can say. A caller may pass one to share (the join's, across rebuilds); one
    # is made here otherwise, so a frame is always timed and nothing is optional
    self.stages = stages if stages is not None else StageStages()
    # late replies, by the watermark rule (latency.LateTracker): a reply past
    # the hold is late, not lost, and a link that is late is one about to drop
    self.late = late if late is not None else LateTracker()
    # the frame prepared and not yet ended, if any
    self._frame: Frame | None = None
    # the newest output parsed, with what it parsed to: a held frame
    # publishes the dict again rather than parsing the array a second time,
    # which it must not, the parser's softmax working in place
    self._parsed: tuple[np.ndarray, dict] | None = None
    # when the large model held a frame, within HOLD_WINDOW, and how many in
    # a row; `behind` says why it should hand back after the last frame
    self._holds: deque[float] = deque()
    self._holds_in_a_row = 0
    self.behind: str | None = None
    # whether the last frame published the one before it: the runtime record's
    self.held = False

  def _build_hevc(self, spec) -> None:
    """The HEVC path's state: two encoders (one camera each), the gate that
    owes keyframes, and the cache that finds a frame's context when its encoder
    answers.

    The encoders come from the adapter a fork supplies (codecs.HEVCEncoder):
    the comma's is the Venus block, reachable only from the device, so this
    builds nothing itself and a link whose fork has no encoder never negotiates
    the codec (codecs.available at the pick).

    `_encoders` is empty and the path stays off where the builder refuses,
    which is how a link falls back to the codec it was already using rather
    than sending frames a server cannot decode.
    """
    h, w = spec.model_hw
    self._gate = stream_mod.StreamGate()
    self._metas = hevc.MetaCache()
    self._epoch = 0
    self._encoders: dict[str, object] = {}
    # two different questions about the same frame: how many bytes it is, and
    # how those bytes are arranged. An encoder is configured from the second,
    # and a length cannot be split back into it.
    self._hevc_size = hevc.nv12_shape((h, w))
    self._hevc_geometry = hevc.nv12_geometry((h, w))
    self._warp_shape = spec.warped_shape
    self._hevc = True
    # a connection is up and the stream starts here
    self._open_hevc_stream()

  def _open_hevc_stream(self) -> None:
    """A connection is up, or a stream must restart: the gate owes IDRs and
    the encoders drop their references, so the first frames out are ones a
    receiver with nothing can decode."""
    if not self._hevc:
      return
    self._epoch += 1
    self._metas.clear()
    self._gate.open(self._epoch)

  def _encode_frame(self, frame_id: int) -> tuple | None:
    """The two cameras' HEVC access units for this frame, or None while the
    gate is shut or an encoder has nothing ready.

    The warp's output is both cameras as one (2, 6, H, W); each is reassembled
    into NV12 and through its own encoder. A frame that comes back short (an
    encoder still buffering) is not a failure: it is a frame the server is not
    sent, and the gate is told, so the next one owes an IDR if it was lossy.
    """
    if not self._hevc or self._gate is None:
      return None
    step = self._gate.begin(self._epoch, frame_id)
    encoders = self._encoder_for()
    if encoders is None:
      return None
    try:
      planes = self._planes()
    except Exception:
      self._log.exception("jetlink: could not read the warped frame for HEVC")
      return None
    units: dict[str, bytes] = {}
    idrs: dict[str, bool] = {}
    for name, enc in encoders.items():
      nv12 = hevc.to_nv12(planes[int(name == stream_mod.STREAMS[1])])
      data, key = enc.encode(nv12, force_keyframe=(name in step.request_idr))
      if not data:
        # nothing ready: the gate must not open on a frame that is not sent
        self._gate.gap(f'{name} encoder had no output')
        return None
      units[name], idrs[name] = bytes(data), bool(key)
    acted = self._gate.confirm(self._epoch, frame_id, **{f'{k}_idr': v for k, v in idrs.items()})
    if not acted.send:
      # the gate is still waiting for a keyframe: the frame is dropped, and
      # the caller reads this as a frame not sent (a hold, not a link failure)
      return None
    return units[stream_mod.STREAMS[0]], units[stream_mod.STREAMS[1]]

  def _planes(self):
    """The warp's output as (2, 6, H, W) uint8, a view and not a copy."""
    out = self.warp.output
    return np.frombuffer(out, np.uint8).reshape(*self._warp_shape)

  def _encoder_for(self) -> dict | None:
    """This link's two encoders, made on first use. None where the adapter
    supplies no builder, which keeps the link on the codec it had.

    The builder is handed `(rows, cols)` and the flat byte count: the first is
    what an encoder configures itself from, the second is what a test compares a
    produced frame against. Handing it the byte count twice, as this did, left
    every backend with nothing to take a width and a height out of.
    """
    if self._encoders:
      return self._encoders
    maker = getattr(self.face, 'hevc_encoder', None)
    if maker is None:
      self._hevc = False
      return None
    try:
      for name in stream_mod.STREAMS:
        self._encoders[name] = maker(self._hevc_geometry, tuple(self._hevc_size))
    except Exception:
      self._log.exception("jetlink: could not build the HEVC encoder, staying on the frame carrier in use")
      self._hevc = False
      self._encoders = {}
      return None
    return self._encoders

  def _frame_eof(self, inputs: dict) -> float | None:
    """The camera's own read-out stamp for this frame, on modeld's monotonic
    clock, when the loop supplies one: the capture stage is measured from it.
    None when it does not, and then the stage is measured from the frame's
    start and the sensor's own delay is not counted (see stages.FrameStages)."""
    stamp = inputs.get('timestamp_eof') or inputs.get('timestampEof')
    if stamp is None:
      return None
    try:
      # modeld's stamp is monotonic nanoseconds, the same clock perf_counter
      # reads: only the units differ
      return float(stamp) / 1e9
    except (TypeError, ValueError):
      return None

  def slice_outputs(self, model_outputs: np.ndarray, output_slices: dict[str, slice]) -> dict[str, np.ndarray]:
    return {k: model_outputs[np.newaxis, v] for k, v in output_slices.items()}

  def log_telemetry(self) -> None:
    """The server's health, piggybacked on the previous response, to the log
    at 1 Hz. chestnutState is comma's board on the wire and a Jetson's
    telemetry has no message of its own yet."""
    telemetry = self.client.last_state
    if not telemetry:
      return
    now = time.monotonic()
    if now - self._last_logged < TELEMETRY_PERIOD:
      return
    self._last_logged = now
    self._event("jetlinkTelemetry", dead=bool(self.client.dead), **telemetry)
    send = getattr(self.client.t, 'last_send', None)
    if send:
      self._event("jetlinkSend", nonce=self.client.nonce, frame=self._frame_id, totals=self.client.t.send_totals.copy(), **send)

  def prepare(self, bufs: dict, transforms: dict[str, np.ndarray], inputs: dict[str, np.ndarray]) -> None:
    """Take this frame up: start the warp, and while the GPU runs it, read
    what the host has answered so far (a held frame's late reply) and pack
    the rest of the inputs. send() puts it on the link and end() waits for
    its answer."""
    t0 = time.perf_counter()
    # the frame's own timing starts here; the sensor's stamp, when the caller
    # passes one, is where the capture stage is measured from
    self.stages.start(self._frame_id + 1, t0, t_eof=self._frame_eof(inputs))
    self.warp.start(_address(bufs['img']), _address(bufs['big_img']), transforms['img'], transforms['big_img'])
    t1 = time.perf_counter()
    self.stages.captured(self._frame_id + 1, t0)
    # the GPU is warping; nothing below is an input to it
    self.client.drain()
    self.log_telemetry()

    # Model decides when action is completed, so desire input is just a pulse triggered on rising edge.
    # Under whichever name the loop keyed it: stock modeld's desire_pulse, or a modeld_v2 bundle's own
    desire = inputs[next(k for k in inputs if k.startswith('desire'))]
    desire[0] = 0
    self.npy['desire'][:] = np.where(desire - self.prev_desire > .99, desire, 0)
    self.prev_desire[:] = desire
    self.npy['traffic_convention'][:] = inputs['traffic_convention']
    self.npy['action_t'][:] = inputs['action_t']

    # free again once infer_begin returns: the gadget's io_submit and the
    # cable's sendmsg have copied it by then, before the next warp writes it
    self.warp.wait()
    self.stages.warped(self._frame_id + 1, time.perf_counter())
    self._frame = Frame(t0, t1, time.perf_counter())

  def send(self, want_telemetry: bool = False) -> None:
    """The prepared frame to the host. It asks for the server's telemetry
    when the log is due for it, or when told to: modeld asks on the frames it
    would have sent a chestnut's state on.

    With an output to hold, a frame the link cannot take without waiting for
    the host to drain earlier ones is not sent, and end() holds it: the same
    plan one frame old a late reply publishes, where waiting stalls the frame
    loop on a host that is behind."""
    frame = self._frame
    self._frame_id += 1
    frame.telemetry = want_telemetry or time.monotonic() - self._last_logged >= TELEMETRY_PERIOD
    try:
      if self._hevc:
        # the two cameras' access units, or a frame the gate kept back, which
        # is a hold and not a failure (send() returning with seq None)
        units = self._encode_frame(self._frame_id)
        if units is None:
          frame.sent = time.perf_counter()
          return
        frame.seq = self.client.infer_begin(None, self.packed, self._frame_id, reset=self._need_reset,
                                            want_state=frame.telemetry, skip_if_busy=self._can_hold,
                                            hevc=units)
      elif self._packer is None:
        frame.seq = self.client.infer_begin(self.warp.output, self.packed, self._frame_id, reset=self._need_reset,
                                            want_state=frame.telemetry, skip_if_busy=self._can_hold)
      else:
        frame.seq = self.client.infer_begin(None, self.packed, self._frame_id, reset=self._need_reset,
                                            want_state=frame.telemetry, skip_if_busy=self._can_hold,
                                            lossless=self._packer.pack(self.warp.errors))
    except Exception:
      self._log.warning("jetlink: frame %d send failed: %s", self._frame_id, getattr(self.client.t, 'last_send', {}))
      raise
    frame.sent = time.perf_counter()
    self.stages.sent(self._frame_id, frame.sent)
    if frame.seq is not None:
      self._need_reset = False

  def end(self, after_enqueue: Callable[[], None] | None = None) -> dict[str, np.ndarray]:
    """The sent frame's output, as modeld blocks on a chestnut's, but not past
    HOLD_FRAME once there is an output to publish again: a frame that long
    is a dropped camera frame. Only a stall past the client's deadline, or an
    output that is not finite, raises, into the joining state's demotion to
    the small model."""
    frame, self._frame = self._frame, None
    # publish health while the Jetson works
    if after_enqueue is not None:
      after_enqueue()
    waiting_from = time.perf_counter()
    if frame.seq is None:
      model_output = None   # not sent (see send): held
    else:
      try:
        model_output = self.client.infer_end(frame.seq, hold=self._hold_left(frame) if self._can_hold else None)
      except NotFinite:
        # answered, so the leave's summary counts it
        self.trips.record(time.perf_counter() - frame.t0, self.client.last_timings[2])
        raise
    t4 = time.perf_counter()
    held = model_output is None
    # The first frames of an HEVC stream have nothing to publish and nothing to
    # publish again: the gate is waiting for a keyframe on both cameras. That is
    # a stream coming up, not a host that is behind, so it is raised before any
    # hold is counted and never moves `behind`: the caller runs the small model
    # for the frame and keeps the link (joining catches NotReady).
    if held and self.client.last_output is None:
      self.held = False
      self.stages.replied(self._frame_id, t4)
      self.stages.finished(self._frame_id, time.perf_counter(), held=False)
      raise NotReady(f"frame {self._frame_id}: nothing to publish and nothing to hold")
    self.held = held
    self.behind = self._note_hold(held)
    self.trips.record(t4 - frame.t0, self.client.last_timings[2])
    # the reply's own arrival, and whether the hold gave up before it: the
    # watermark rule, which says a late reply is late and a missing one lost
    if frame.seq is not None:
      (self.late.gave_up if held else self.late.arrived)(self._frame_id)
    self.stages.replied(self._frame_id, t4)
    outputs = self._outputs(self.client.last_output if held else model_output)
    self.stages.finished(self._frame_id, time.perf_counter(), held=held)
    # a frame past the budget is a dropped camera frame; send against reply
    # says which end it was. Held frames are a steady few on a marginal host,
    # so after the first they go to the log at TELEMETRY_PERIOD
    log_hold = held and (self.trips.held <= 3 or t4 - self._last_hold_logged >= TELEMETRY_PERIOD)
    if self._frame_id <= 3 or t4 - frame.t0 > SLOW_FRAME or log_hold:
      note = ''
      if held:
        self._last_hold_logged = t4
        note = f', held ({self.trips.held} so far{", not sent" if frame.seq is None else ""})'
      # persisted on the comma so a drive can separate server execution from
      # receive stalls once the Jetson is offline; server total excludes USB
      gpu_us, queue_us, total_us = self.client.last_timings
      receive = getattr(self.client.t, 'last_receive', {})
      # over the cable: how frames go, how many never came back, and what the
      # kernel dropped on the way in (softnet), since the link came up
      drops = getattr(self.client.t, 'net_drops', lambda: None)()
      cable = (f"; frames {'as datagrams' if self.client.t.datagrams else 'on the stream'}, "
               f"{self.client.frames_lost} lost, net drops {drops}" if drops is not None else '')
      self._log.warning("jetlink: frame %d warp %.1f data %.1f send %.1f wait %.1f ms%s; "
                        "server gpu %.1f queue %.1f total %.1f ms; ffs maxima prepare %.1f read_wait %.1f handoff %.1f ms%s",
                        self._frame_id, (frame.t1 - frame.t0) * 1e3, (frame.t2 - frame.t1) * 1e3,
                        (frame.sent - frame.t2) * 1e3, (t4 - waiting_from) * 1e3,
                        note,
                        gpu_us / 1e3, queue_us / 1e3, total_us / 1e3, receive.get('prepare', 0.0) * 1e3,
                        receive.get('read_wait', 0.0) * 1e3, receive.get('handoff', 0.0) * 1e3, cable)
    self._report_stages(t4)
    return outputs

  def _report_stages(self, now: float) -> None:
    """The comma's six stage means to the host, once a second of frames.

    Sent off the ring's running sum, so it costs a divide and not a sort, and
    from the frame path because that is the only thread holding the link: a
    second thread would race the frame's seq and could have its own message
    taken for a replay. A second that has run no frame says nothing rather than
    six zeros, which would read as a link with no cost at all."""
    if now - self._stages_reported < TELEMETRY_PERIOD:
      return
    self._stages_reported = now
    means = self.stages.means()
    if means.get('frames'):
      self.client.report_stages(means)

  def run(self, bufs: dict, transforms: dict[str, np.ndarray],
          inputs: dict[str, np.ndarray], after_enqueue: Callable[[], None] | None = None) -> dict[str, np.ndarray]:
    # a paced frame is not prepared, sent or run on the host: the last plan
    # publishes again, the held frame's semantics without a frame the host
    # queues. Never counted as a hold -- the governor asked for it (pace.py)
    if self._pace is not None and self.client.last_output is not None \
            and self._pace.skip(time.monotonic()):
      self.held = True
      self.behind = None
      if after_enqueue is not None:
        after_enqueue()
      return self._outputs(self.client.last_output)
    self.prepare(bufs, transforms, inputs)
    self.send(after_enqueue is not None)
    return self.end(after_enqueue)

  @property
  def _hold_frame(self) -> float | None:
    return HOLD_FRAME if self._hold_frame_override is None else self._hold_frame_override

  @property
  def _settling_frames(self) -> int:
    return SETTLING_FRAMES if self._settling_frames_override is None else self._settling_frames_override

  @property
  def _holds_in_a_row_limit(self) -> int:
    return HOLDS_IN_A_ROW if self._holds_in_a_row_override is None else self._holds_in_a_row_override

  @property
  def _holds_allowed(self) -> int:
    return HOLDS_ALLOWED if self._holds_allowed_override is None else self._holds_allowed_override

  @property
  def _can_hold(self) -> bool:
    """Is there an output to publish again instead of waiting (HOLD_FRAME)?"""
    return bool(self._hold_frame) and self.client.last_output is not None

  def _hold_left(self, frame) -> float:
    """What is left of the hold for `frame`, from its warp's start."""
    return self._hold_frame - (time.perf_counter() - frame.t0)

  def _note_hold(self, held: bool) -> str | None:
    """Why the large model should hand back after this frame, if it should:
    any held frame among its first PROVING_FRAMES past SETTLING_FRAMES,
    HOLDS_IN_A_ROW held frames running, or more than HOLDS_ALLOWED in
    HOLD_WINDOW. None while it is keeping up."""
    # the governor watches the same rhythm and steps the frame rate; its own
    # paced frames never come through here (run() answers them itself)
    if self._pace is not None:
      self._pace.note(held)
    if not held:
      self._holds_in_a_row = 0
      return None
    self.trips.held += 1
    now = time.monotonic()
    self._holds.append(now)
    while now - self._holds[0] > HOLD_WINDOW:
      self._holds.popleft()
    self._holds_in_a_row += 1
    if self._frame_id <= self._settling_frames:
      return None
    if self._proving_holds_fatal and self._frame_id <= PROVING_FRAMES:
      return f'held frame {self._frame_id} of the first {PROVING_FRAMES}'
    if self._holds_in_a_row >= self._holds_in_a_row_limit:
      return f'held {self._holds_in_a_row} frames in a row'
    if len(self._holds) > self._holds_allowed:
      return f'held {len(self._holds)} frames in {HOLD_WINDOW:.0f} s'
    return None

  def _outputs(self, model_output: np.ndarray) -> dict[str, np.ndarray]:
    """The output as modeld reads it. An array parsed before (a held frame's)
    gives the same dict again: the parser's softmax works in place on it."""
    if self._parsed is not None and self._parsed[0] is model_output:
      return self._parsed[1]
    # the server checks first (Status.NOT_FINITE, which the client raises as
    # this). This is for one that did not, or bytes the link changed: a raw
    # inf is a corrupt output even where the parser would clip it finite. A
    # sum allocates nothing, and any NaN or inf makes it one; these outputs
    # are far from overflow
    if not np.isfinite(model_output.sum()):
      raise NotFinite(f"frame {self._frame_id}: the output is not finite")
    outputs_dict = self.parser.parse_outputs(self.slice_outputs(model_output, self.output_slices))
    # a finite output can still parse to inf, by a parser that does not clip
    if not np.isfinite(sum(float(value.sum()) for value in outputs_dict.values())):
      raise NotFinite(f"frame {self._frame_id}: the parsed output is not finite")
    if SEND_RAW_PRED:
      outputs_dict['raw_pred'] = model_output.copy()
    self._parsed = (model_output, outputs_dict)
    return outputs_dict

  def close(self) -> None:
    """Let go of the link; the joining state calls this on a model it retires."""
    self.client.close()


def _address(buf) -> int:
  """Where a camera buffer modeld hands over (a VisionBuf) keeps its bytes."""
  return np.frombuffer(buf.data, dtype=np.uint8).ctypes.data
