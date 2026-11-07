#!/usr/bin/env python3
"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of zoompilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

Does the Venus encoder actually work on this device?

Not a unittest, and not in CI: the test needs /dev/video33 and /dev/ion, which
exist on a comma and nowhere else. Run it on the device:

  PYTHONPATH=/data/openpilot python3 \\
    openpilot/sunnypilot/jetlink_adapter/tests/hevc_venus_check.py

It encodes real NV12 frames at the geometry jetlink uses and checks the things
a receiver depends on: Annex-B framing, the parameter sets riding on every
keyframe, the IDR the carrier's keyframe gate asks for, a P frame smaller than
the IDR before it, the GOP actually recycling, the rate control actually
responding, and -- because jetlink runs one encoder per camera -- two sessions
open at once.

There is no libavcodec on the device, so the obvious proof (decode the stream
back and compare pixels) was tried through the other half of the vidc pair
(/dev/video32) and does not work here: that node starts a session and then
never emits a frame, for *any* stream. The device's own recorded
fcamera.hevc -- HEVC that every phone and the replay tool decode -- behaves
exactly like ours at that interface, so the failure is the vdec and not the
bitstream. `--decode` re-runs that comparison for anyone who wants to see it.
"""
import ctypes
import importlib.util
import os
import select
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.path.join(HERE, '..', 'hevc_venus.py')

# jetlink's frame geometry: model planes are 128 rows by 256 columns, and the
# six of them pack into one 512x256 NV12
WIDTH = 512
HEIGHT = 256
FRAMES = 6

# the decoder half of the same vidc pair; index0 where the encoder is index1
DECODER = '/dev/v4l/by-path/platform-aa00000.qcom_vidc-video-index0'
DECODER_FALLBACK = '/dev/video32'
DECODE_TIMEOUT = 3.0

# HEVC NAL unit types, from ITU-T H.265 table 7-1
NAL_VPS = 32
NAL_SPS = 33
NAL_PPS = 34
NAL_IDR_W_RADL = 19
NAL_IDR_N_LP = 20
NAL_CRA = 21

failures = []


def load():
  spec = importlib.util.spec_from_file_location('hevc_venus', MODULE)
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


def check(condition, message):
  """Record instead of raise: one run should report everything that is wrong,
  not stop at the first thing."""
  if condition:
    print(f"  ok    {message}")
  else:
    print(f"  FAIL  {message}")
    failures.append(message)
  return condition


def nals(data):
  """Every NAL unit in an Annex-B stream, as (type, payload) pairs.

  The start code is three or four bytes; both appear in vidc's output, so the
  scan skips zero bytes rather than assuming a length."""
  found = []
  i = 0
  size = len(data)
  while i + 3 <= size:
    if data[i] == 0 and data[i + 1] == 0 and data[i + 2] == 1:
      start = i + 3
      j = start
      while j + 3 <= size and not (data[j] == 0 and data[j + 1] == 0 and data[j + 2] in (0, 1)):
        j += 1
      end = j
      while end > start and data[end - 1] == 0:
        end -= 1
      if end > start:
        found.append(((data[start] >> 1) & 0x3F, data[start + 2:end]))
      i = j
    else:
      i += 1
  return found


def types_of(data):
  return [t for t, _ in nals(data)]


def pattern(width, height, shift):
  """A moving square on a flat background, with a chroma ramp.

  Grey is not enough: an encoder can match a flat frame while dropping the
  chroma plane entirely, so the ramp makes a broken NV12 layout visible. The
  square moves with `shift`, which is what stops a stale reference frame from
  looking like a good encode."""
  y = bytearray(width * height)
  for row in range(height):
    base = row * width
    for col in range(width):
      inside = (row // 32 + shift) % 4 == col // 64 % 4
      y[base + col] = 200 if inside else 40
  uv = bytearray(width * height // 2)
  for row in range(height // 2):
    base = row * width
    for col in range(0, width, 2):
      uv[base + col] = (col * 255) // width
      uv[base + col + 1] = (row * 255) // (height // 2)
  return bytes(y) + bytes(uv)


def mean_abs_diff(a, b, length):
  """Average |a-b| over the first `length` bytes: a 512x256 frame is 131k
  bytes and this device's Python is a Cortex-A, so it walks slices rather than
  indexing one byte at a time."""
  total = 0
  step = 4096
  for start in range(0, length, step):
    va = a[start:start + step]
    vb = b[start:start + step]
    total += sum(abs(x - y) for x, y in zip(va, vb, strict=True))
  return total / length


class Decoder:
  """The other half of the vidc pair: an Annex-B HEVC access unit in, one NV12
  frame out.

  Kept because it is the only decoder on the device, and because watching it
  fail identically on a production stream is what ruled it out as a check.
  Only the capture fourcc NV12_UBWC gets past STREAMON; NV12 is answered with
  "Unsupported bitstream" in the kernel log, which is the driver reporting a
  format it cannot use as a stream it cannot read.
  """

  def __init__(self, hevc, width, height, buffers=4):
    self.hevc = hevc
    self.width = width
    self.height = height
    self.path = DECODER if os.path.exists(DECODER) else DECODER_FALLBACK
    self._free = []
    self._started = False
    self.fd = os.open(self.path, os.O_RDWR | os.O_NONBLOCK)

    cap = hevc._Capability()
    hevc._ioctl(self.fd, hevc._ior('V', 0, ctypes.sizeof(cap)), cap)
    if cap.driver != b'msm_vidc_driver':
      raise hevc.EncoderError(f"{self.path}: not the vidc driver ({cap.driver!r})")

    # the bitstream format first: it is what tells a decoder which codec this
    # session is, and the raw side is negotiated against it
    in_fmt = hevc._Format(type=hevc.BUF_TYPE_OUTPUT, pix_mp=hevc._PixFormatMplane(
      width=width, height=height, pixelformat=hevc.FOURCC_HEVC, field=hevc.FIELD_ANY))
    hevc._ioctl(self.fd, hevc._iowr('V', 5, ctypes.sizeof(in_fmt)), in_fmt)
    self._in_size = in_fmt.pix_mp.plane_fmt[0].sizeimage

    out_fmt = hevc._Format(type=hevc.BUF_TYPE_CAPTURE, pix_mp=hevc._PixFormatMplane(
      width=width, height=height, pixelformat=hevc.FOURCC_NV12_UBWC, field=hevc.FIELD_ANY))
    hevc._ioctl(self.fd, hevc._iowr('V', 5, ctypes.sizeof(out_fmt)), out_fmt)
    self._out_size = out_fmt.pix_mp.plane_fmt[0].sizeimage

    for buf_type in (hevc.BUF_TYPE_CAPTURE, hevc.BUF_TYPE_OUTPUT):
      hevc._ioctl(self.fd, hevc._iowr('V', 8, ctypes.sizeof(hevc._RequestBuffers)),
                  hevc._RequestBuffers(count=buffers, type=buf_type, memory=hevc.MEMORY_USERPTR))
    self._in = [hevc._DmaBuf(self._in_size) for _ in range(buffers)]
    self._out = [hevc._DmaBuf(self._out_size) for _ in range(buffers)]
    self._free = list(range(buffers))

  def _qbuf(self, buf_type, index, bytesused):
    hevc = self.hevc
    buf = self._in[index] if buf_type == hevc.BUF_TYPE_OUTPUT else self._out[index]
    length = self._in_size if buf_type == hevc.BUF_TYPE_OUTPUT else self._out_size
    reserved = (hevc._u32 * 11)()
    reserved[0] = buf.fd
    plane = hevc._Plane(bytesused=bytesused, length=length, reserved=reserved)
    plane.m.userptr = buf.addr
    hevc._ioctl(self.fd, hevc._iowr('V', 15, ctypes.sizeof(hevc._Buffer)),
                hevc._Buffer(index=index, type=buf_type, memory=hevc.MEMORY_USERPTR,
                             m=hevc._M(planes=ctypes.addressof(plane)), length=1))

  def _dqbuf(self, buf_type):
    hevc = self.hevc
    plane = hevc._Plane()
    buf = hevc._Buffer(type=buf_type, memory=hevc.MEMORY_USERPTR,
                       m=hevc._M(planes=ctypes.addressof(plane)), length=1)
    try:
      hevc._ioctl(self.fd, hevc._iowr('V', 17, ctypes.sizeof(hevc._Buffer)), buf)
    except hevc.EncoderError as err:
      if err.errno in (11, 16):        # EAGAIN, EBUSY
        return None
      raise
    return buf.index, plane.bytesused, buf.flags

  def decode(self, unit):
    """One access unit in, one frame out, or None if nothing arrived.

    The stream-on order is the one the driver accepts: the bitstream reference
    first, then STREAMON on the bitstream queue, then the raw queue. Any other
    order answers EINVAL, which is the entire reason this class is a diagnostic
    and not a helper."""
    deadline = time.monotonic() + DECODE_TIMEOUT
    index = self._take_input()
    self._in[index].write(unit)
    self._qbuf(self.hevc.BUF_TYPE_OUTPUT, index, len(unit))
    if not self._started:
      hevc = self.hevc
      hevc._ioctl(self.fd, hevc._iow('V', 18, ctypes.sizeof(ctypes.c_int)), ctypes.c_int(hevc.BUF_TYPE_OUTPUT))
      for i in range(len(self._out)):
        self._qbuf(hevc.BUF_TYPE_CAPTURE, i, self._out_size)
      hevc._ioctl(self.fd, hevc._iow('V', 18, ctypes.sizeof(ctypes.c_int)), ctypes.c_int(hevc.BUF_TYPE_CAPTURE))
      self._started = True
    while time.monotonic() < deadline:
      readable, _, _ = select.select([self.fd], [], [], 0.1)
      if not readable:
        continue
      got = self._dqbuf(self.hevc.BUF_TYPE_CAPTURE)
      if got is None:
        continue
      out_index, bytesused, flags = got
      data = self._out[out_index].read(bytesused)
      self._qbuf(self.hevc.BUF_TYPE_CAPTURE, out_index, self._out_size)
      if bytesused:
        return data
    return None

  def _take_input(self):
    deadline = time.monotonic() + DECODE_TIMEOUT
    while not self._free:
      if time.monotonic() > deadline:
        raise self.hevc.EncoderError('the decoder took no input')
      _, writable, _ = select.select([], [self.fd], [], 0.05)
      if writable:
        got = self._dqbuf(self.hevc.BUF_TYPE_OUTPUT)
        if got is not None:
          self._free.append(got[0])
    return self._free.pop()

  def close(self):
    hevc = self.hevc
    for buf_type in (hevc.BUF_TYPE_OUTPUT, hevc.BUF_TYPE_CAPTURE):
      try:
        hevc._ioctl(self.fd, hevc._iow('V', 19, ctypes.sizeof(ctypes.c_int)), ctypes.c_int(buf_type))
      except hevc.EncoderError:
        pass
      try:
        hevc._ioctl(self.fd, hevc._iowr('V', 8, ctypes.sizeof(hevc._RequestBuffers)),
                    hevc._RequestBuffers(count=0, type=buf_type, memory=hevc.MEMORY_USERPTR))
      except hevc.EncoderError:
        pass
    os.close(self.fd)


def one_unit(encoder, frame, *, force_keyframe: bool = False, tries: int = 6):
  """One non-empty access unit, re-sending the frame while the encoder reports
  that it has nothing yet.

  `encode()` is allowed to come back empty -- the hardware buffers a few frames
  when a stream opens, and hard content can take longer -- so a check that
  treated the first empty answer as a failure would be testing the encoder's
  latency rather than its output."""
  for attempt in range(tries):
    data, key = encoder.encode(frame, force_keyframe=force_keyframe and attempt == 0)
    if data:
      return data, key
  return b'', False


def encode_frames(hevc, count, **kwargs):
  """`count` frames from a fresh encoder, plus the encoder itself so the caller
  can look at the session. Always closed by the caller."""
  encoder = hevc.VenusEncoder(width=WIDTH, height=HEIGHT, **kwargs)
  units = [one_unit(encoder, pattern(WIDTH, HEIGHT, i)) for i in range(count)]
  return encoder, units


def part_gop(hevc):
  """The IDR period is a control the radio link depends on: a receiver that
  joins mid-stream waits for the next keyframe, so the GOP bounds the wait."""
  print("\n7. the GOP recycles on schedule")
  gop = 20
  encoder, units = encode_frames(hevc, gop + 4, gop=gop)
  try:
    keys = [i for i, (_, key) in enumerate(units) if key]
    check(keys[0] == 0, f"frame 0 is a keyframe, keys at {keys}")
    check(len(keys) == 2 and abs(keys[1] - gop) <= 1,
          f"the next keyframe lands on the GOP boundary (index {keys[1] if len(keys) > 1 else 'none'}, asked for {gop})")
  finally:
    encoder.close()


def part_rate(hevc):
  """The bitrate control is what keeps the link inside its budget, so it has to
  change the output and not just be accepted silently.

  The two ends of the range are used because the middle saturates: a frame this
  simple hits the encoder's floor well before 1 Mbps, and above that the number
  of bytes stops tracking the setting. Pure noise is not usable here either --
  incompressible input makes the encoder take seconds per frame, so a short run
  measures the timeout instead of the rate control."""
  print("\n8. the bitrate control moves the output")
  frames = [pattern(WIDTH, HEIGHT, i) for i in range(6)]
  sizes = {}
  for bitrate in (200_000, 2_000_000):
    encoder = hevc.VenusEncoder(width=WIDTH, height=HEIGHT, bitrate=bitrate, fps=20)
    try:
      sizes[bitrate] = sum(len(one_unit(encoder, frame)[0]) for frame in frames)
    finally:
      encoder.close()
  print(f"  200 kbps -> {sizes[200_000]} bytes, 2 Mbps -> {sizes[2_000_000]} bytes over {len(frames)} frames")
  check(sizes[2_000_000] > sizes[200_000] * 1.5,
        "the higher bitrate produces visibly more bytes for the same frames")


def part_two_cameras(hevc):
  """jetlink runs one encoder per camera, so two sessions have to coexist on a
  chip that has one encoder block. If this fails, the second camera has no
  hardware and the whole design changes."""
  print("\n9. two cameras at once")
  first = second = None
  try:
    first = hevc.VenusEncoder(width=WIDTH, height=HEIGHT)
    second = hevc.VenusEncoder(width=WIDTH, height=HEIGHT)
    check(True, "both sessions opened")
    for i in range(4):
      a, a_key = one_unit(first, pattern(WIDTH, HEIGHT, i))
      b, b_key = one_unit(second, pattern(WIDTH, HEIGHT, i + 2))
      check(a_key == b_key, f"frame {i}: both encoders agree about the keyframe ({a_key}, {b_key})")
      check(len(a) and len(b), f"frame {i}: both produced a unit ({len(a)} and {len(b)} bytes)")
    check(first.frames == 4 and second.frames == 4, "and each counted its own frames")
  except hevc.EncoderError as err:
    check(False, f"two concurrent sessions: {err}")
  finally:
    for encoder in (first, second):
      if encoder is not None:
        encoder.close()


def part_decode(hevc, units):
  """Opt-in: hand the stream to the vdec and report what comes back. On this
  kernel the answer is nothing, and a production stream gets the same answer,
  which is why the default run does not treat it as a failure."""
  print("\n10. decode round trip (opt-in)")
  decoder = None
  try:
    decoder = Decoder(hevc, WIDTH, HEIGHT)
    check(True, f"{decoder.path}: formats in {decoder._in_size} out {decoder._out_size}")
    frame_bytes = WIDTH * HEIGHT * 3 // 2
    for i, (unit, _) in enumerate(units):
      decoded = decoder.decode(unit)
      if decoded is None:
        check(False, f"frame {i}: the vdec produced nothing in {DECODE_TIMEOUT}s")
        break
      if not check(len(decoded) >= frame_bytes, f"frame {i}: {len(decoded)} bytes decoded"):
        continue
      error = mean_abs_diff(decoded, pattern(WIDTH, HEIGHT, i), WIDTH * HEIGHT)
      check(error < 12, f"frame {i}: luma differs from the source by {error:.2f} on average")
  except hevc.EncoderError as err:
    check(False, f"decode round trip: {err}")
  finally:
    if decoder is not None:
      decoder.close()


def main():
  decode = '--decode' in sys.argv[1:]
  print(f"module: {os.path.normpath(MODULE)}")
  hevc = load()

  print("\n1. does this machine have the block?")
  if not check(hevc.available(), f"available() with {hevc.node()}"):
    print("\nno encoder on this machine: nothing else can run")
    return 1
  check(os.path.exists(hevc.ION_NODE), f"{hevc.ION_NODE} present")

  print("\n2. the struct sizes this module believes")
  try:
    hevc._check_sizes()
    check(True, f"{len(hevc.EXPECTED_SIZES)} structures match the kernel's header")
  except hevc.EncoderError as err:
    check(False, str(err))
    return 1

  print(f"\n3. encode {FRAMES} frames at {WIDTH}x{HEIGHT}")
  sources = [pattern(WIDTH, HEIGHT, i) for i in range(FRAMES)]
  encoder = hevc.VenusEncoder(width=WIDTH, height=HEIGHT, bitrate=2_000_000, gop=20, fps=20)
  check(encoder._in_size >= WIDTH * HEIGHT * 3 // 2, f"input plane {encoder._in_size} bytes")
  check(encoder._out_size > 0, f"output plane {encoder._out_size} bytes")
  check(encoder._force_ctrl == hevc.CTRL_REQUEST_IFRAME, f"IDR control 0x{encoder._force_ctrl:08x}")

  units = []
  try:
    for i in range(FRAMES):
      data, key = one_unit(encoder, sources[i])
      units.append((data, key))
      print(f"  frame {i}: {len(data):6d} bytes  key={key!s:5s}  nals={types_of(data)}")

    print("\n4. what a receiver needs from each unit")
    first, first_key = units[0]
    check(first_key, "the first frame is a keyframe")
    check(first.startswith((b'\x00\x00\x00\x01', b'\x00\x00\x01')),
          "Annex-B start code at offset 0")
    first_types = types_of(first)
    check(NAL_VPS in first_types, "VPS (type 32) on the keyframe")
    check(NAL_SPS in first_types, "SPS (type 33) on the keyframe")
    check(NAL_PPS in first_types, "PPS (type 34) on the keyframe")
    check(any(t in (NAL_IDR_W_RADL, NAL_IDR_N_LP, NAL_CRA) for t in first_types),
          "an IRAP slice on the keyframe")
    rest = units[1:]
    check(all(not key for _, key in rest), "frames after the first are not keyframes")
    for i, (data, _) in enumerate(rest, start=1):
      types = types_of(data)
      check(all(1 <= t <= 31 for t in types), f"frame {i} is VCL only {types}")
    check(len(units[1][0]) < len(first), f"the P frame {len(units[1][0])} is smaller than the IDR {len(first)}")

    print("\n5. an IDR on demand")
    ahead, ahead_key = one_unit(encoder, sources[0], force_keyframe=True)
    check(ahead_key, "force_keyframe makes the next frame a keyframe")
    check(any(t in (NAL_IDR_W_RADL, NAL_IDR_N_LP) for t in types_of(ahead)),
          f"and it is an IDR {types_of(ahead)}")

    print("\n6. reset() starts a stream a new receiver can decode")
    encoder.reset()
    after, after_key = one_unit(encoder, sources[0])
    check(after_key, "the frame after reset is a keyframe")
    check(NAL_SPS in types_of(after) and NAL_PPS in types_of(after),
          "and carries the parameter sets again")
    encoder.reset()
    again, _ = one_unit(encoder, sources[0])
    check(again == first, f"first frame identical on a fresh encoder ({len(again)} vs {len(first)} bytes)")
  finally:
    encoder.close()

  part_gop(hevc)
  part_rate(hevc)
  part_two_cameras(hevc)
  if decode:
    part_decode(hevc, units)

  print()
  if failures:
    print(f"{len(failures)} check(s) failed:")
    for message in failures:
      print(f"  - {message}")
    return 1
  print("all checks passed: the Venus encoder produces the stream jetlink needs")
  return 0


if __name__ == '__main__':
  sys.exit(main())
