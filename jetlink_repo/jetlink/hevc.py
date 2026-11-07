"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of jetlink and is licensed under the MIT License.
See the LICENSE file in the root directory for more details.

Frames as HEVC: the carrier for a link too slow for 393 KB a frame.

A big model's frame is (2, 6, H, W) uint8 off openpilot's warp: two cameras,
six planes each. The six planes are not an arbitrary layout, they are a 4:2:0
image taken apart, and putting it back is exact:

    Y[2i + dy, 2j + dx] = plane[dx + 2 dy, i, j]      (dy, dx in {0, 1})
    U, V                = plane[4], plane[5]          (each H x W)

so the image is 2W x 2H (512x256 for the big model's 128x256 planes) with
half-resolution chroma: plain NV12, the one format every hardware encoder
takes. to_nv12 and from_nv12 are inverses, and the tests hold them to it.

That is what makes this carrier possible at all: the comma's Venus encoder
wants NV12, the warp gives six planes, and a reassembly in numpy is the whole
bridge. It is ~0.2 ms a camera on a big core, next to an encoder that runs on
the GPU's own hardware block and costs the CPU nothing.

Pairing is already solved here, unlike the reference fork: jetlink's warp takes
both camera buffers in one graph call, so the two cameras of a frame are
inherently the same capture. There is nothing to match after the fact and no
half-frame to drop.

What is not free is the stream. HEVC is lossy and inter-frame, so a receiver
that misses one frame cannot decode the next: stream.StreamGate decides when an
IDR is owed, and MetaCache below is the rule that keeps a frame's own context
from being lost when an encoder output arrives late.

Pure logic and numpy, with the encoder behind a seam (codecs.HEVCEncoder): the
Venus encoder is a device, so the tests drive everything with a fake one.
"""
from __future__ import annotations

import subprocess

import numpy as np

# the model's frame: two cameras of six H x W planes
PLANES = 6
Y_PHASES = 4
# the ffmpeg command the reference backend runs: raw NV12 in, HEVC Annex-B out
FFMPEG_BIN = 'ffmpeg'


def to_nv12(planes: np.ndarray, out: np.ndarray | None = None) -> np.ndarray:
  """One camera's six planes (6, H, W) uint8 as NV12, flat and contiguous.

  NV12 is a full-resolution luma plane followed by half-resolution chroma
  interleaved U,V. The warp's four Y phases are exactly the four parity classes
  of a luma plane twice as wide and twice as tall, and its planes 4 and 5 are
  the U and V samples:

      Y[2i + dy, 2j + dx] = plane[dx + 2 dy][i, j]
      U[i, j], V[i, j]    = plane[4][i, j], plane[5][i, j]

  so the destination is a (2H) x (2W) luma of 4HW bytes then a (H, W, 2)
  interleaved chroma of 2HW: 6HW in all, which is the six planes' own size and
  the reason nothing is lost. The result is flat (`6HW` uint8) because that is
  the buffer an encoder takes; `nv12_shape` says what to reshape it to.
  """
  six = np.ascontiguousarray(planes, np.uint8) if out is None else planes
  if six.shape[0] != PLANES:
    raise ValueError(f"{six.shape[0]} planes, expected {PLANES}")
  h, w = six.shape[-2:]
  if out is not None and out.size != PLANES * h * w:
    raise ValueError(f"a {out.size} byte buffer, expected {PLANES * h * w}")
  buf = np.empty(PLANES * h * w, np.uint8) if out is None else out.reshape(-1)
  luma = buf[:4 * h * w].reshape(2 * h, 2 * w)
  for p in range(Y_PHASES):
    dx, dy = p & 1, (p >> 1) & 1
    luma[dy::2, dx::2] = six[p]
  chroma = buf[4 * h * w:].reshape(h, w, 2)
  chroma[..., 0] = six[4]
  chroma[..., 1] = six[5]
  return buf


def from_nv12(nv12: np.ndarray, plane_shape: tuple[int, int] | None = None,
              plane6: np.ndarray | None = None) -> np.ndarray:
  """to_nv12's inverse: a flat NV12 buffer back to the six planes, (6, H, W).

  The chroma, laid out (H, W, 2), splits into planes 4 and 5. The plane geometry
  comes from `plane_shape` (or from `plane6`, the destination to write into, for
  a caller reusing a buffer): a buffer's size alone cannot say how H and W split,
  and a wrong guess decodes to a plausible but wrong frame rather than failing.
  """
  buf = np.asarray(nv12, np.uint8).reshape(-1)
  shape = (plane6.shape[-2], plane6.shape[-1]) if plane6 is not None else plane_shape
  if shape is None:
    raise ValueError("from_nv12 needs the plane shape (H, W), or a plane6 buffer to write into")
  h, w = shape
  if buf.size != PLANES * h * w:
    raise ValueError(f"{buf.size} bytes, expected {PLANES * h * w} for {h} x {w} planes")
  out = np.empty((PLANES, h, w), np.uint8) if plane6 is None else plane6
  luma = buf[:4 * h * w].reshape(2 * h, 2 * w)
  for p in range(Y_PHASES):
    dx, dy = p & 1, (p >> 1) & 1
    out[p] = luma[dy::2, dx::2]
  chroma = buf[4 * h * w:].reshape(h, w, 2)
  out[4] = chroma[..., 0]
  out[5] = chroma[..., 1]
  return out


def nv12_shape(plane_shape: tuple[int, int]) -> tuple[int, int, int]:
  """The NV12 buffer's shape for a plane geometry: flat, as to_nv12 returns it."""
  h, w = plane_shape
  return (PLANES * h * w,)


def nv12_geometry(plane_shape: tuple[int, int]) -> tuple[int, int]:
  """The NV12 frame's own (rows, cols) for a plane geometry.

  Twice the plane in each direction, because the warp's four Y phases are the
  four parity classes of a luma plane twice as wide and twice as tall.

  `nv12_shape` gives the flat length, which is what a buffer check needs, but a
  length cannot be split back into a height and a width -- 6HW bytes is the same
  number for a 512x256 frame and a 256x512 one. So an encoder is configured from
  this, and a caller that had only the flat size could never open one.
  """
  h, w = plane_shape
  return (2 * h, 2 * w)


class Missing:
  """Why a frame's own context was not there for an encoder output.

  The two are kept apart because they mean different things: a stale one is a
  frame from a stream that has been replaced, which is nobody's fault and
  nothing to report; a gap is a frame the receiver will not get, which breaks
  the prediction chain and owes an IDR.
  """
  STALE = 'stale'
  GAP = 'gap'


class MetaCache:
  """A frame's own context, by frame id, for the encoder that answers later.

  An asynchronous encoder hands its output back after the frame has moved on,
  so whatever the caller needs to finish that frame (its id on the wire, its
  epoch) has to be looked up by id. This is that lookup, and the rule that
  makes it safe:

    A miss never clears the cache.

  The reference fork's first version popped the whole queue on a miss, which
  ate the new stream's opening frame and left the receiver undecodable; the bug
  is in its README as the reason the rule exists. A miss is classified instead
  (Missing), and only a gap is reported to whoever owes the recovery.

  Bounded, and keyed so a reused id is never mistaken for the frame it
  replaced: an entry is only valid while the id in the slot is the id asked
  for.
  """

  def __init__(self, ring: int = 64):
    self.ring = max(1, int(ring))
    self._slots: list[tuple[int, object] | None] = [None] * self.ring
    self._latest: int | None = None
    self.hits = 0
    self.stale = 0
    self.gaps = 0

  def put(self, frame_id: int, meta: object) -> None:
    """Remember a frame's context as it goes to the encoder."""
    self._slots[frame_id % self.ring] = (frame_id, meta)
    self._latest = frame_id

  def take(self, frame_id: int) -> tuple[object | None, str | None]:
    """The context for `frame_id`, and None, or (None, reason) for a miss.

    A miss is Missing.STALE when the frame is one this cache has moved past: a
    slot holding a newer id, or an id at or behind the newest frame put and no
    longer there (already taken, or evicted by the ring). It is Missing.GAP when
    the frame is ahead of anything ever put, which means this connection never
    had it. The two are kept apart because a gap breaks the prediction chain and
    owes an IDR, where a stale output is nobody's to recover.

    Never removes anything unless it is this frame's own entry: an output that
    cannot be matched must not cost a later frame its context.
    """
    entry = self._slots[frame_id % self.ring]
    if entry is not None and entry[0] == frame_id:
      self._slots[frame_id % self.ring] = None
      self.hits += 1
      return entry[1], None
    if self._latest is None or frame_id > self._latest:
      # nothing this connection ever sent: no context existed to lose
      self.gaps += 1
      return None, Missing.GAP
    self.stale += 1
    return None, Missing.STALE

  def clear(self) -> None:
    """Forget every frame: a new connection, whose frame ids start again and
    whose contexts belong to a stream the receiver has dropped."""
    self._slots = [None] * self.ring
    self._latest = None

  def summary(self) -> dict:
    return {'hits': self.hits, 'stale': self.stale, 'gaps': self.gaps}


class FfmpegEncoder:
  """A HEVC encoder as a subprocess: raw NV12 in, one Annex-B access unit out.

  The reference backend, and the one a Jetson or a Mac can actually run: ffmpeg
  with libx265 or a hardware encoder of its own. It is deliberately not the
  device's production path, which is the comma's Venus block through loggerd's
  V4L encoder and has no Python binding; a fork supplies that as another
  HEVCEncoder and nothing else here changes.

  `encode()` returns the bytes ffmpeg has ready, which may be none for the
  first frames while it buffers: the caller frames by access unit and treats an
  empty answer as a frame not yet encoded, not as a failure.
  """

  def __init__(self, *, size: tuple[int, int], bitrate: int = 2_000_000,
               gop: int = 20, exe: str = FFMPEG_BIN):
    self.width, self.height = size[1], size[0]     # a (rows, cols) shape
    self.bitrate = bitrate
    self.gop = gop
    self.exe = exe
    self._proc: subprocess.Popen | None = None
    self._pending_idr = False
    self.frames = 0

  def _argv(self) -> list[str]:
    # ultrafast is not available to x265; the device uses its own encoder and
    # this path exists to prove the pipeline, not to win a benchmark
    return [self.exe, '-hide_banner', '-loglevel', 'error',
            '-f', 'rawvideo', '-pix_fmt', 'nv12',
            '-s', f'{self.width}x{self.height}', '-r', '20', '-i', 'pipe:0',
            '-c:v', 'libx265', '-preset', 'ultrafast', '-tune', 'zerolatency',
            '-x265-params', f'keyint={self.gop}:min-keyint={self.gop}:bframes=0:scenecut=0',
            '-b:v', str(self.bitrate), '-f', 'hevc', 'pipe:1']

  def configure(self, *, width: int, height: int, bitrate: int = 2_000_000, gop: int = 20) -> None:
    if (height, width) == (self.height, self.width) and bitrate == self.bitrate and gop == self.gop:
      return
    self.close()
    self.width, self.height, self.bitrate, self.gop = width, height, bitrate, gop

  def _open(self) -> None:
    self._proc = subprocess.Popen(self._argv(), stdin=subprocess.PIPE, stdout=subprocess.PIPE)

  def encode(self, frame, *, force_keyframe: bool = False) -> tuple[bytes, bool]:
    """One access unit. `frame` is one camera's NV12 (2H, 2W) uint8.

    A keyframe request is honoured by ffmpeg's own GOP handling (the keyint
    above), so `force_keyframe` is recorded for the caller's bookkeeping and
    the returned flag is what the stream actually did, read off the Annex-B
    NAL types: the caller must trust the flag, not the request.
    """
    if self._proc is None:
      self._open()
    data = np.ascontiguousarray(frame, np.uint8).tobytes()
    want = len(data)
    if want != self.width * self.height * 3 // 2:
      raise ValueError(f"{want} bytes of NV12, expected {self.width * self.height * 3 // 2}")
    self._proc.stdin.write(data)
    self._proc.stdin.flush()
    self.frames += 1
    self._pending_idr = self._pending_idr or force_keyframe
    out = self._read_ready()
    return out, keyframe_in(out)

  def _read_ready(self) -> bytes:
    """Whatever the encoder has produced, without blocking for more: an
    encoder that buffers returns nothing on the frames it holds."""
    import os
    import select
    proc = self._proc
    assert proc is not None and proc.stdout is not None
    ready, _, _ = select.select([proc.stdout], [], [], 0.0)
    if not ready:
      return b''
    chunk = os.read(proc.stdout.fileno(), 1 << 20)
    return chunk or b''

  def reset(self) -> None:
    """Drop the stream state: restarting the process is the blunt way, and the
    right one for a carrier whose whole state is the encoder's references."""
    self.close()
    self._pending_idr = True

  def close(self) -> None:
    if self._proc is None:
      return
    try:
      self._proc.stdin.close()
      self._proc.wait(timeout=5)
    except Exception:
      pass
    finally:
      self._proc = None


# HEVC NAL unit types, in the header byte's top bits: 16..21 are the IRAP
# (intra random access) types a receiver may start decoding on
def keyframe_in(annexb: bytes) -> bool:
  """Does this Annex-B buffer contain an IRAP picture, i.e. a keyframe a
  receiver can start from? Scans the NAL headers of a 3- or 4-byte start code
  stream; the type is `(byte >> 1) & 0x3F` per H.265's nal_unit_header.

  A start code with no header byte after it (a truncated buffer) is not a
  picture: the scan reads the type only where the byte exists.
  """
  data = bytes(annexb)
  n = len(data)
  i = 0
  while i < n:
    if data[i:i + 3] == b'\x00\x00\x01':
      at = i + 3
      step = 3
    elif data[i:i + 4] == b'\x00\x00\x00\x01':
      at = i + 4
      step = 4
    else:
      i += 1
      continue
    if at >= n:
      return False        # a start code with nothing after it
    if 16 <= (data[at] >> 1) & 0x3F <= 21:
      return True
    i += step
  return False


def available(exe: str | None = None) -> bool:
  """Is the reference encoder's tool there? A caller checks before offering
  HEVC at all, so a link never negotiates a carrier it cannot build. No name,
  or one that is not there, is False."""
  import shutil
  return bool(exe) and shutil.which(exe) is not None
