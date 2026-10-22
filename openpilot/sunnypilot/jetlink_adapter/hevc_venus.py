"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of zoompilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

The comma's hardware HEVC encoder: jetlink's codecs.HEVCEncoder over the
Venus block, through V4L2's stateful memory-to-memory API.

The device is the one place this can exist: jetlink (the submodule) never
imports openpilot, and openpilot's own encoder (system/loggerd/encoder/
v4l_encoder.cc) is C++ behind VisionBuf with no Python binding. So this talks
to the driver directly, and the only thing it needs from the rest of the
checkout is a device node.

Why ctypes and not a compiled shim: the adapter's SConscript is deliberately a
no-op, and a `.so` would add a build step to a fork that has none, for a dozen
ioctls. The structs below are the kernel's, so their sizes are asserted before
the first ioctl: a mismatch is a loud failure rather than a stack smash in the
driver.

What the node accepts, measured on a comma 3 (kernel 4.9.103, msm_vidc_venc):

  * MMAP and DMABUF are refused with EINVAL, so `REQBUFS` is USERPTR only.
  * USERPTR with ordinary heap memory is *accepted* and then never processed:
    the frame is queued, the driver returns no event, and the encode hangs.
    The memory has to be a dma-buf, with its fd in the plane's reserved[0] --
    which is what loggerd's encoder does with a VisionBuf, and what this does
    with an ION allocation. Nothing in the ioctls says so; the buffer just
    never comes back.
  * ION's system heap is `1 << ION_SYSTEM_HEAP_ID`, and this device's id is 25,
    not the generic enum's 0. Allocating through the wrong mask is ENODEV.
  * the driver wants 8 bytes more than the buffer it was asked for, so every
    allocation is length + 8, as VisionBuf::allocate does.

Two cameras are two instances. One session encoding two independent views
reconfigures the hardware every frame, which is why jetlink's contract has one
encoder per stream.
"""
from __future__ import annotations

import ctypes
import errno
import fcntl
import mmap
import os
import select
import time

# the encoder half of the vidc pair: index1 is the encoder, index0 the decoder
NODE = '/dev/v4l/by-path/platform-aa00000.qcom_vidc-video-index1'
NODE_FALLBACK = '/dev/video33'
ION_NODE = '/dev/ion'

VIDEO_MAX_PLANES = 8
BUFFERS = 4                    # per queue: one in the driver, three to spare
TIMEOUT = 2.0                  # seconds to wait for one access unit

_u32 = ctypes.c_uint32
_s32 = ctypes.c_int32
_ulong = ctypes.c_ulong


def _ioc(direction: int, kind: str, nr: int, size: int) -> int:
  return (direction << 30) | (size << 16) | (ord(kind) << 8) | nr


def _ior(kind: str, nr: int, size: int) -> int:
  return _ioc(2, kind, nr, size)


def _iow(kind: str, nr: int, size: int) -> int:
  return _ioc(1, kind, nr, size)


def _iowr(kind: str, nr: int, size: int) -> int:
  return _ioc(3, kind, nr, size)


# -- the kernel's structures, from linux/videodev2.h ------------------------------

class _Timeval(ctypes.Structure):
  """struct timeval. The 6.x header says timespec; on LP64 both are two 8-byte
  longs, which is why openpilot's C++ builds against this header on this kernel."""
  _fields_ = [('tv_sec', ctypes.c_long), ('tv_usec', ctypes.c_long)]


class _Timecode(ctypes.Structure):
  _fields_ = [('type', _u32), ('flags', _u32), ('frames', ctypes.c_uint8), ('seconds', ctypes.c_uint8),
              ('minutes', ctypes.c_uint8), ('hours', ctypes.c_uint8), ('userbits', ctypes.c_uint8 * 4)]


class _PlanePixFormat(ctypes.Structure):
  _fields_ = [('sizeimage', _u32), ('bytesperline', _u32), ('reserved', ctypes.c_uint16 * 6)]


class _PixFormatMplane(ctypes.Structure):
  _fields_ = [('width', _u32), ('height', _u32), ('pixelformat', _u32), ('field', _u32), ('colorspace', _u32),
              ('plane_fmt', _PlanePixFormat * VIDEO_MAX_PLANES), ('num_planes', ctypes.c_uint8),
              ('flags', ctypes.c_uint8), ('ycbcr_enc', ctypes.c_uint8), ('quantization', ctypes.c_uint8),
              ('xfer_func', ctypes.c_uint8), ('reserved', ctypes.c_uint8 * 7)]


class _Format(ctypes.Structure):
  """struct v4l2_format: the type, then a union whose largest member decides the
  size the ioctl is checked against (208 here). Only pix_mp is ever used."""
  _fields_ = [('type', _u32), ('_pad', _u32), ('pix_mp', _PixFormatMplane), ('_tail', ctypes.c_uint8 * 8)]


class _M(ctypes.Union):
  _fields_ = [('offset', _u32), ('userptr', _ulong), ('planes', ctypes.c_void_p), ('fd', _s32)]


class _Plane(ctypes.Structure):
  _fields_ = [('bytesused', _u32), ('length', _u32), ('m', _M), ('data_offset', _u32), ('reserved', _u32 * 11)]


class _Buffer(ctypes.Structure):
  _fields_ = [('index', _u32), ('type', _u32), ('bytesused', _u32), ('flags', _u32), ('field', _u32),
              ('timestamp', _Timeval), ('timecode', _Timecode), ('sequence', _u32), ('memory', _u32),
              ('m', _M), ('length', _u32), ('reserved2', _u32), ('request_fd', _s32)]


class _RequestBuffers(ctypes.Structure):
  _fields_ = [('count', _u32), ('type', _u32), ('memory', _u32), ('reserved', _u32 * 2)]


class _Control(ctypes.Structure):
  _fields_ = [('id', _u32), ('value', _s32)]


class _Capability(ctypes.Structure):
  _fields_ = [('driver', ctypes.c_char * 16), ('card', ctypes.c_char * 32), ('bus_info', ctypes.c_char * 32),
              ('version', _u32), ('capabilities', _u32), ('device_caps', _u32), ('reserved', _u32 * 3)]


class _CaptureParm(ctypes.Structure):
  _fields_ = [('capability', _u32), ('capturemode', _u32), ('timeperframe_num', _u32), ('timeperframe_den', _u32),
              ('extendedmode', _u32), ('readbuffers', _u32), ('reserved', _u32 * 4)]


class _StreamParm(ctypes.Structure):
  """struct v4l2_streamparm: the type, then a 200-byte union."""
  _fields_ = [('type', _u32), ('parm', ctypes.c_uint8 * 200)]


class _IonAllocation(ctypes.Structure):
  _fields_ = [('len', ctypes.c_size_t), ('align', ctypes.c_size_t), ('heap_id_mask', _u32), ('flags', _u32),
              ('handle', _s32)]


class _IonFd(ctypes.Structure):
  _fields_ = [('handle', _s32), ('fd', _s32)]


# the sizes measured from the device's own header: any divergence means this
# module's idea of a struct is not the kernel's, and the ioctls would corrupt
EXPECTED_SIZES = {
  'v4l2_format': (_Format, 208), 'v4l2_pix_format_mplane': (_PixFormatMplane, 192),
  'v4l2_plane_pix_format': (_PlanePixFormat, 20), 'v4l2_buffer': (_Buffer, 88), 'v4l2_plane': (_Plane, 64),
  'v4l2_requestbuffers': (_RequestBuffers, 20), 'v4l2_control': (_Control, 8), 'v4l2_capability': (_Capability, 104),
  'v4l2_streamparm': (_StreamParm, 204), 'v4l2_captureparm': (_CaptureParm, 40),
  'ion_allocation_data': (_IonAllocation, 32), 'ion_fd_data': (_IonFd, 8),
}

# the fourcc codes, written out so a wrong endianness is visible at a glance
FOURCC_HEVC = 0x43564548               # 'HEVC'
FOURCC_NV12 = 0x3231564E               # 'NV12'
FOURCC_NV12_UBWC = 0x38323151          # 'Q128', the tile format the decoder insists on
BUF_TYPE_CAPTURE = 9                   # V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE
BUF_TYPE_OUTPUT = 10                   # V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE
MEMORY_USERPTR = 2
FIELD_ANY = 1
COLORSPACE_470_SYSTEM_BG = 8

FLAG_KEYFRAME = 0x00000008
FLAG_CODECCONFIG = 0x00020000
FLAG_EOS = 0x02000000

CTRL_BITRATE = 0x009909CF
CTRL_HEADER_MODE = 0x009909D8
CTRL_IDR_PERIOD = 0x00992005
CTRL_NUM_P_FRAMES = 0x00992006
CTRL_NUM_B_FRAMES = 0x00992007
CTRL_RATE_CONTROL = 0x00992009
CTRL_VUI_TIMING_INFO = 0x00992013
CTRL_HEVC_PROFILE = 0x00992028
CTRL_HEVC_TIER_LEVEL = 0x00992029
CTRL_PRIORITY = 0x00992034
CTRL_FORCE_KEY_FRAME = 0x00980918      # the standard one; vidc answers EINVAL
CTRL_REQUEST_IFRAME = 0x00992008       # vidc's own: an IDR on the next frame
HEADER_MODE_SEPARATE = 0
RATE_CONTROL_VBR_CFR = 2
HEVC_PROFILE_MAIN = 0
HEVC_LEVEL_HIGH_TIER_5 = 0xF

ION_SYSTEM_HEAP_ID = 25                # this device's, from linux/msm_ion.h
ION_ALLOC_PAD = 8                      # the driver wants 8 bytes more than asked

HEVC_DEFAULT_BITRATE = 2_000_000
HEVC_GOP = 20
HEVC_FPS = 20


class EncoderError(RuntimeError):
  """The node would not do what the frame path asked: no encoder, a reconfig
  that failed, or a frame that never came back.

  `errno` is the ioctl's, when there was one: an empty queue answers EAGAIN,
  which is a state and not a failure, so the callers that expect it have to be
  able to tell the two apart without reading the message."""

  def __init__(self, message: str, errno_: int | None = None):
    super().__init__(message)
    self.errno = errno_


def node() -> str | None:
  """The encoder node, or None on a machine with no Venus block (a PC, a
  Jetson, a Mac): the caller then keeps the carrier it had."""
  for path in (NODE, NODE_FALLBACK):
    if os.path.exists(path):
      return path
  return None


def available() -> bool:
  """Is there an encoder to build? Opening both nodes is the only honest test."""
  path = node()
  if path is None or not os.path.exists(ION_NODE):
    return False
  try:
    fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
  except OSError:
    return False
  os.close(fd)
  return True


def make_encoder(size, geometry=None, *, bitrate: int = HEVC_DEFAULT_BITRATE,
                 gop: int = HEVC_GOP, fps: int = HEVC_FPS) -> VenusEncoder:
  """One camera's encoder, as jetlink's `ModelFace.hevc_encoder` asks for it.

  `size` is the NV12 frame's (rows, cols) and `geometry` its flat byte count,
  which is redundant here but is the second half of the contract. The size is
  what matters: a frame's length cannot be split back into a width and a
  height, so a builder handed only the length cannot open anything.
  """
  height, width = int(size[0]), int(size[1])
  return VenusEncoder(width=width, height=height, bitrate=bitrate, gop=gop, fps=fps)


def _check_sizes() -> None:
  for name, (struct, expected) in EXPECTED_SIZES.items():
    got = ctypes.sizeof(struct)
    if got != expected:
      raise EncoderError(f"{name} is {got} bytes here, {expected} in the kernel's header: refusing to ioctl")


def _ioctl(fd: int, request: int, struct) -> None:
  """One ioctl, with the struct carried across as bytes: fcntl wants a buffer,
  ctypes structs are not one, and the buffer is mutated in place while an int
  comes back."""
  raw = bytearray(bytes(struct))
  try:
    fcntl.ioctl(fd, request, raw, True)
  except OSError as err:
    raise EncoderError(f"ioctl 0x{request:08x} failed: {err.strerror}", err.errno) from err
  ctypes.memmove(ctypes.addressof(struct), bytes(raw), ctypes.sizeof(struct))


class _DmaBuf:
  """One ION allocation, and the fd vidc wants in the plane's reserved[0].

  Two views of the same memory: `addr` is the virtual address the plane's
  userptr takes, `fd` the dma-buf the driver actually maps. Both are needed --
  the queue is USERPTR, and without the fd nothing is ever encoded.
  """

  def __init__(self, length: int):
    self.allocated = length + ION_ALLOC_PAD
    ion = os.open(ION_NODE, os.O_RDWR)
    try:
      alloc = _IonAllocation(len=self.allocated, align=4096, heap_id_mask=1 << ION_SYSTEM_HEAP_ID, flags=0)
      _ioctl(ion, _iowr('I', 0, ctypes.sizeof(_IonAllocation)), alloc)     # ION_IOC_ALLOC
      shared = _IonFd(handle=alloc.handle)
      _ioctl(ion, _iowr('I', 4, ctypes.sizeof(_IonFd)), shared)            # ION_IOC_SHARE
    finally:
      os.close(ion)
    self.fd = shared.fd
    self._map = mmap.mmap(self.fd, self.allocated)
    self._view = ctypes.c_char.from_buffer(self._map)
    self.addr = ctypes.addressof(self._view)

  def write(self, payload: bytes) -> None:
    self._map[:len(payload)] = payload

  def read(self, size: int) -> bytes:
    return bytes(self._map[:size])


class VenusEncoder:
  """One camera's HEVC stream, as jetlink's HEVCEncoder expects it.

  `encode` is synchronous -- one NV12 in, one Annex-B access unit out --
  because the frame path asks for both cameras' units on the same thread and
  has nothing else to do with the time. The encoder is stateful across frames
  (references, GOP phase), so an instance belongs to one stream, and `reset`
  is how a new connection starts one a receiver can decode from nothing.
  """

  def __init__(self, *, width: int = 0, height: int = 0, bitrate: int = HEVC_DEFAULT_BITRATE,
               gop: int = HEVC_GOP, fps: int = HEVC_FPS, path: str | None = None):
    _check_sizes()
    self._path = path or node()
    if self._path is None:
      raise EncoderError('no encoder node: this machine has no Venus block')
    self.width = int(width)
    self.height = int(height)
    self.bitrate = int(bitrate)
    self.gop = int(gop)
    self.fps = int(fps)
    self.frames = 0
    self._fd = -1
    self._force_ctrl = 0
    self._header = b''
    self._in: list[_DmaBuf] = []
    self._out: list[_DmaBuf] = []
    self._free: list[int] = []
    self._in_size = 0
    self._out_size = 0
    if self.width and self.height:
      self._open()

  # -- the contract ------------------------------------------------------------

  def configure(self, *, width: int, height: int, bitrate: int = HEVC_DEFAULT_BITRATE, gop: int = HEVC_GOP) -> None:
    """Set the geometry, the rate control and the GOP. Called before the first
    frame; a repeat of the same values does nothing."""
    if (width, height, bitrate, gop) == (self.width, self.height, self.bitrate, self.gop) and self._fd >= 0:
      return
    self.close()
    self.width, self.height, self.bitrate, self.gop = int(width), int(height), int(bitrate), int(gop)
    self._open()

  def encode(self, frame, *, force_keyframe: bool = False) -> tuple[bytes, bool]:
    """One frame's access unit, and whether the encoder made it a keyframe.

    `frame` is one camera's NV12, flat or (rows, cols) uint8: 3/2 bytes per
    pixel. The returned unit is Annex-B and carries the parameter sets when it
    is a keyframe, so a receiver with nothing in hand can decode it.

    The bytes can be empty, and that is not an error: the hardware holds several
    frames before its first output, so the opening frames of a stream come back
    with nothing. The caller treats an empty answer as a frame not yet encoded,
    which is what `codecs.HEVCEncoder` documents and what the frame path does
    with it. Waiting here for the output would deadlock instead -- the encoder
    needs the following frames queued before it will produce this one.
    """
    if self._fd < 0:
      if not (self.width and self.height):
        raise EncoderError('configure() before encode(): the geometry is not known')
      self._open()
    payload = frame if isinstance(frame, (bytes, bytearray)) else memoryview(frame).tobytes()
    if len(payload) != self.width * self.height * 3 // 2:
      raise EncoderError(f"{len(payload)} bytes of NV12, expected {self.width * self.height * 3 // 2}")
    index = self._take_input()
    self._in[index].write(payload)
    if force_keyframe and self._force_ctrl:
      self._try_ctrl(self._force_ctrl, 1)
    self._qbuf(BUF_TYPE_OUTPUT, index, len(payload))
    self.frames += 1
    return self._collect()

  def reset(self) -> None:
    """Drop the stream state without reconfiguring: the next frame is an IDR a
    receiver that has forgotten everything can decode from."""
    if self._fd >= 0:
      self.close()
      self._open()

  def close(self) -> None:
    """Release the encoder. Idempotent."""
    if self._fd < 0:
      return
    for buf_type in (BUF_TYPE_CAPTURE, BUF_TYPE_OUTPUT):
      try:
        self._streamoff(buf_type)
      except EncoderError:
        pass
      try:
        self._reqbufs(buf_type, 0)
      except EncoderError:
        pass
    try:
      os.close(self._fd)
    finally:
      self._fd = -1
      self._in, self._out, self._free = [], [], []

  # -- setup -------------------------------------------------------------------

  def _open(self) -> None:
    self._header = b''
    self._fd = os.open(self._path, os.O_RDWR | os.O_NONBLOCK)
    cap = _Capability()
    _ioctl(self._fd, _ior('V', 0, ctypes.sizeof(_Capability)), cap)            # VIDIOC_QUERYCAP
    if cap.driver != b'msm_vidc_driver':
      self.close()
      raise EncoderError(f"{self._path}: not the vidc driver ({cap.driver!r})")

    # capture first: the bitstream, at the output geometry
    out_fmt = _Format(type=BUF_TYPE_CAPTURE, pix_mp=_PixFormatMplane(
      width=self.width, height=self.height, pixelformat=FOURCC_HEVC, field=FIELD_ANY))
    _ioctl(self._fd, _iowr('V', 5, ctypes.sizeof(_Format)), out_fmt)           # VIDIOC_S_FMT
    # the driver advertises one byte per pixel here and will not negotiate
    # more (S_FMT clamps it back), which a low-QP frame of hard content can
    # exceed; such a frame comes back as an unfilled buffer. Handing it twice
    # the room costs a megabyte and removes one way to lose a frame silently.
    self._out_size = max(out_fmt.pix_mp.plane_fmt[0].sizeimage, self.width * self.height * 2)

    # then the raw side: NV12 in, at the same geometry. The warp already made
    # exactly the frame that is sent, so no scaling is asked for
    in_fmt = _Format(type=BUF_TYPE_OUTPUT, pix_mp=_PixFormatMplane(
      width=self.width, height=self.height, pixelformat=FOURCC_NV12, field=FIELD_ANY,
      colorspace=COLORSPACE_470_SYSTEM_BG))
    _ioctl(self._fd, _iowr('V', 5, ctypes.sizeof(_Format)), in_fmt)            # VIDIOC_S_FMT
    self._in_size = max(in_fmt.pix_mp.plane_fmt[0].sizeimage, self.width * self.height * 3 // 2)

    # rate control's CFR denominator: it must match what the caller sends, or
    # the bitrate is spread over a different number of frames than there are
    pacer = _CaptureParm(timeperframe_num=1, timeperframe_den=max(1, self.fps))
    parm = _StreamParm(type=BUF_TYPE_OUTPUT)
    ctypes.memmove(ctypes.byref(parm, 4), ctypes.byref(pacer), ctypes.sizeof(pacer))
    _ioctl(self._fd, _iowr('V', 22, ctypes.sizeof(_StreamParm)), parm)         # VIDIOC_S_PARM

    # separate headers, cached and prepended to every keyframe: that is what
    # makes an IDR self-contained, which the frame carrier requires
    self._ctrl(CTRL_BITRATE, self.bitrate)
    self._ctrl(CTRL_HEADER_MODE, HEADER_MODE_SEPARATE)
    self._ctrl(CTRL_NUM_P_FRAMES, max(0, self.gop - 1))
    self._ctrl(CTRL_NUM_B_FRAMES, 0)
    self._ctrl(CTRL_IDR_PERIOD, max(1, self.gop))
    self._ctrl(CTRL_RATE_CONTROL, RATE_CONTROL_VBR_CFR)
    self._ctrl(CTRL_VUI_TIMING_INFO, 1)
    self._ctrl(CTRL_HEVC_PROFILE, HEVC_PROFILE_MAIN)
    self._ctrl(CTRL_HEVC_TIER_LEVEL, HEVC_LEVEL_HIGH_TIER_5)
    self._ctrl(CTRL_PRIORITY, 0)
    # an IDR on demand is what the carrier's keyframe gate needs, and there are
    # two candidates: vidc's own and the standard one, which this driver refuses
    # with EINVAL. Whichever answers is kept; with neither, the GOP's periodic
    # IDR is all there is and the caller trusts the returned flag, as it must
    self._force_ctrl = next((c for c in (CTRL_REQUEST_IFRAME, CTRL_FORCE_KEY_FRAME) if self._try_ctrl(c, 1)), 0)

    self._reqbufs(BUF_TYPE_CAPTURE, BUFFERS)
    self._reqbufs(BUF_TYPE_OUTPUT, BUFFERS)
    self._in = [_DmaBuf(self._in_size) for _ in range(BUFFERS)]
    self._out = [_DmaBuf(self._out_size) for _ in range(BUFFERS)]
    self._free = list(range(BUFFERS))
    # stream on before any buffer is queued: vidc refuses a queue that already
    # holds buffers, which is why this follows loggerd's encoder and not the
    # textbook order
    self._streamon(BUF_TYPE_CAPTURE)
    self._streamon(BUF_TYPE_OUTPUT)
    for i in range(BUFFERS):
      self._qbuf(BUF_TYPE_CAPTURE, i, self._out_size)

  # -- ioctls ------------------------------------------------------------------

  def _ctrl(self, ctrl_id: int, value: int) -> None:
    _ioctl(self._fd, _iowr('V', 28, ctypes.sizeof(_Control)), _Control(id=ctrl_id, value=value))

  def _try_ctrl(self, ctrl_id: int, value: int) -> bool:
    """Set a control that may not exist on this driver: False instead of raise,
    for the ones the frame path can do without."""
    try:
      self._ctrl(ctrl_id, value)
    except EncoderError:
      return False
    return True

  def _reqbufs(self, buf_type: int, count: int) -> None:
    _ioctl(self._fd, _iowr('V', 8, ctypes.sizeof(_RequestBuffers)),
           _RequestBuffers(count=count, type=buf_type, memory=MEMORY_USERPTR))

  def _streamon(self, buf_type: int) -> None:
    _ioctl(self._fd, _iow('V', 18, ctypes.sizeof(ctypes.c_int)), ctypes.c_int(buf_type))

  def _streamoff(self, buf_type: int) -> None:
    _ioctl(self._fd, _iow('V', 19, ctypes.sizeof(ctypes.c_int)), ctypes.c_int(buf_type))

  def _qbuf(self, buf_type: int, index: int, bytesused: int) -> None:
    buf = self._in[index] if buf_type == BUF_TYPE_OUTPUT else self._out[index]
    length = self._in_size if buf_type == BUF_TYPE_OUTPUT else self._out_size
    # the dma-buf fd in reserved[0] is the one thing the driver does not
    # document: without it the queued frame is never processed
    reserved = (_u32 * 11)()
    reserved[0] = buf.fd
    plane = _Plane(bytesused=bytesused, length=length, reserved=reserved)
    plane.m.userptr = buf.addr
    _ioctl(self._fd, _iowr('V', 15, ctypes.sizeof(_Buffer)),
           _Buffer(index=index, type=buf_type, memory=MEMORY_USERPTR,
                   m=_M(planes=ctypes.addressof(plane)), length=1))

  def _dqbuf(self, buf_type: int) -> tuple[int, int, int] | None:
    """The next buffer the driver has finished with, or None when this queue
    is empty. EAGAIN here is the normal answer -- it is what the drain loop
    stops on, and what a poll that lied about being readable gives back."""
    plane = _Plane()
    buf = _Buffer(type=buf_type, memory=MEMORY_USERPTR, m=_M(planes=ctypes.addressof(plane)), length=1)
    try:
      _ioctl(self._fd, _iowr('V', 17, ctypes.sizeof(_Buffer)), buf)
    except EncoderError as err:
      if err.errno in (errno.EAGAIN, errno.EBUSY):
        return None
      raise
    return buf.index, plane.bytesused, buf.flags

  # -- one frame ---------------------------------------------------------------

  def _take_input(self) -> int:
    """An output buffer the driver has given back. Normally one is free; if
    none is, the drain has not run yet, so wait for it."""
    deadline = time.monotonic() + TIMEOUT
    while not self._free:
      if time.monotonic() > deadline:
        raise EncoderError('no free input buffer')
      self._drain_output(0.05)
    return self._free.pop()

  def _drain_output(self, timeout: float) -> None:
    """Take back the output buffers the driver has finished with: POLLOUT on
    this fd is exactly that."""
    _, writable, _ = select.select([], [self._fd], [], timeout)
    if not writable:
      return
    while True:
      got = self._dqbuf(BUF_TYPE_OUTPUT)
      if got is None:
        return
      self._free.append(got[0])

  def _collect(self) -> tuple[bytes, bool]:
    """The access unit this frame produced, headers included when it is a key
    one. Empty when the encoder has not finished it yet.

    An empty answer is the contract's own: `codecs.HEVCEncoder` says the first
    frames may return nothing while the encoder buffers, and the frame path
    counts one as a frame not sent rather than a failure. It cannot be a wait,
    either -- the hardware buffers several frames before its first output, so
    waiting here would deadlock against the feed that fills that buffer.

    A codec-config buffer is the parameter sets: cached, and skipped.
    """
    deadline = time.monotonic() + TIMEOUT
    while True:
      remaining = deadline - time.monotonic()
      if remaining <= 0:
        return b'', False
      readable, writable, _ = select.select([self._fd], [self._fd], [], remaining)
      if writable:
        self._drain_output(0)
      if not readable:
        continue
      got = self._dqbuf(BUF_TYPE_CAPTURE)
      if got is None:
        continue
      index, bytesused, flags = got
      data = self._out[index].read(bytesused)
      self._qbuf(BUF_TYPE_CAPTURE, index, self._out_size)
      if flags & FLAG_EOS:
        raise EncoderError('the encoder reported end of stream')
      if flags & FLAG_CODECCONFIG:
        self._header = data
        continue
      if not bytesused:
        # the driver handing a capture slot back unfilled while it works
        continue
      key = bool(flags & FLAG_KEYFRAME)
      if key and self._header and not data.startswith(self._header):
        data = self._header + data
      return data, key
