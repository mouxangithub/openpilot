"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of jetlink and is licensed under the MIT License.
See the LICENSE file in the root directory for more details.

Lossless frames for links slower than USB (Wi-Fi): what the comma sends in
place of the warped frame, and how a server gets the frame back bit for bit.

Each 128x256 plane of the warp's output, (2 cameras, 6 planes, 128, 256)
uint8, is predicted pixel by pixel from its left (a), upper (b) and upper-left
(c) neighbours with JPEG-LS's MED predictor, zero outside the plane:

    pred = min(a, b) if c >= max(a, b)
           max(a, b) if c <= min(a, b)
           a + b - c otherwise

and the error (x - pred) mod 256 is folded so small errors either way are
small bytes: 0, -1, 1, -2, 2 ... -> 0, 1, 2, 3, 4 ... A Huffman coder then
packs those bytes: 2.1x on real drive frames (route 286, 2026-10-06).

Zero padding gives the edges JPEG-LS's rules without cases: the first row
predicts from the left, the first column from above, the first pixel from 0.

The comma computes the errors on its GPU with the warp (openpilot.lossless)
and packs each plane alone (Packer), so a server unpacks planes in parallel;
on the wire that is INFER_REQ with Flag.LOSSLESS (jetlink.protocol). encode()
and decode() are the reference both ends and the tests check against, in
numpy. Decoding is sequential (each pixel needs its decoded neighbours), so a
server's decoder is native code; decode() here is for tests.
"""
from __future__ import annotations

import ctypes
import ctypes.util

import numpy as np

# the warp's output: two cameras of six 128x256 planes (4 Y phases, U, V)
SHAPE = (2, 6, 128, 256)


def predict(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
  """MED's prediction from the left, upper and upper-left neighbours."""
  mx, mn = np.maximum(a, b), np.minimum(a, b)
  return np.where(c >= mx, mn, np.where(c <= mn, mx, a + b - c))


def fold(r: np.ndarray) -> np.ndarray:
  """(x - pred) mod 256 as a byte, small either way first: 0, -1, 1, -2 ..."""
  r = r % 256
  return np.where(r < 128, r * 2, (256 - r) * 2 - 1).astype(np.uint8)


def unfold(z: np.ndarray) -> np.ndarray:
  """fold's inverse, as an error mod 256."""
  z = z.astype(np.int32)
  return np.where(z % 2 == 0, z // 2, 256 - (z + 1) // 2)


def encode(frame: np.ndarray) -> np.ndarray:
  """The folded errors of planes (..., H, W) uint8, the same shape."""
  x = frame.astype(np.int32)
  pad = [(0, 0)] * (x.ndim - 2) + [(1, 0), (1, 0)]
  p = np.pad(x, pad)
  return fold(x - predict(p[..., 1:, :-1], p[..., :-1, 1:], p[..., :-1, :-1]))


def decode(errors: np.ndarray) -> np.ndarray:
  """encode's inverse. Row by row, pixel by pixel: slow, for tests."""
  r = unfold(errors)
  h, w = errors.shape[-2:]
  out = np.zeros(errors.shape[:-2] + (h + 1, w + 1), np.int32)   # zero row and column first
  for i in range(1, h + 1):
    for j in range(1, w + 1):
      pred = predict(out[..., i, j - 1], out[..., i - 1, j], out[..., i - 1, j - 1])
      out[..., i, j] = (pred + r[..., i - 1, j - 1]) % 256
  return out[..., 1:, 1:].astype(np.uint8)


# zstd.h: ZSTD_c_compressionLevel, and ZSTD_c_literalCompressionMode
# (ZSTD_c_experimentalParam5, which the shared library accepts) set to
# ZSTD_ps_enable. Negative levels leave literals raw (1.2-1.5x on these errors)
# unless told otherwise; matching is not worth its time on them, Huffman is
# the gain: 2.12x at level -20, 2.63 ms a frame on a mici big core
_ZSTD_C_LEVEL = 100
_ZSTD_C_LITERAL_MODE = 1002
_ZSTD_PS_ENABLE = 1
LEVEL = -20


def _libzstd():
  """The system's libzstd: AGNOS and Linux by soname, a Mac's from Homebrew."""
  for name in ('libzstd.so.1', ctypes.util.find_library('zstd'),
               '/opt/homebrew/lib/libzstd.dylib', '/usr/local/lib/libzstd.dylib'):
    if name:
      try:
        return ctypes.CDLL(name)
      except OSError:
        continue
  raise OSError("no libzstd on this system")


class Packer:
  """Each plane of a frame's errors packed alone, into one reused buffer."""

  def __init__(self, warped_shape):
    n, k, h, w = warped_shape
    self.planes, self.plane_bytes = n * k, h * w
    lib = _libzstd()
    lib.ZSTD_createCCtx.restype = ctypes.c_void_p
    lib.ZSTD_CCtx_setParameter.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    lib.ZSTD_CCtx_setParameter.restype = ctypes.c_size_t
    lib.ZSTD_compress2.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    lib.ZSTD_compress2.restype = ctypes.c_size_t
    lib.ZSTD_compressBound.argtypes = [ctypes.c_size_t]
    lib.ZSTD_compressBound.restype = ctypes.c_size_t
    lib.ZSTD_isError.argtypes = [ctypes.c_size_t]
    lib.ZSTD_isError.restype = ctypes.c_uint
    self._compress = lib.ZSTD_compress2
    self._cctx = lib.ZSTD_createCCtx()
    for key, value in ((_ZSTD_C_LEVEL, LEVEL), (_ZSTD_C_LITERAL_MODE, _ZSTD_PS_ENABLE)):
      if lib.ZSTD_isError(lib.ZSTD_CCtx_setParameter(self._cctx, key, value)):
        raise RuntimeError(f"libzstd refused parameter {key}={value}")
    self._out = np.empty(self.planes * lib.ZSTD_compressBound(self.plane_bytes), np.uint8)
    self._out_at = self._out.ctypes.data
    # the size table INFER_REQ carries before the planes: a u32 per plane
    self._sizes = np.zeros(self.planes, '<u4')
    self._table = memoryview(self._sizes).cast('B')
    # the errors' address, kept while they are the same buffer: the warp's
    # are one for its life, so the frame loop reads it once
    self._src = None
    self._src_at = 0

  def pack(self, errors) -> tuple[memoryview, memoryview]:
    """The size table and the packed planes of `errors` (planes x plane_bytes,
    contiguous), as INFER_REQ with Flag.LOSSLESS carries them after the packed
    floats. Both are valid until the next pack()."""
    if errors is not self._src:
      src = np.frombuffer(errors, np.uint8)
      if src.size != self.planes * self.plane_bytes:
        raise ValueError(f"{src.size} bytes of errors, not {self.planes} planes of {self.plane_bytes}")
      self._src, self._src_at = errors, src.ctypes.data
    at, cap = 0, self._out.size
    for k in range(self.planes):
      n = self._compress(self._cctx, self._out_at + at, cap - at, self._src_at + k * self.plane_bytes, self.plane_bytes)
      if n > cap - at:   # a zstd error code is a size_t near its maximum
        raise RuntimeError("zstd could not pack a plane")
      self._sizes[k] = n
      at += n
    return self._table, memoryview(self._out)[:at]
