"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of jetlink and is licensed under the MIT License.
See the LICENSE file in the root directory for more details.

The comma's half of lossless frames (jetlink.lossless): the MED errors on the
GPU, which the lossless warp build makes in its own graph (warp.with_errors);
jetlink.lossless.Packer packs them on the CPU.

Measured on the mici (2026-10-07, scripts/comma/bench_lossless.py): warp
0.96 ms p50 alone, 1.10 with the errors, 3.0 with the packing, bit for bit
with jetlink.lossless.encode.

tinygrad is the fork's: imported inside the functions that need it.
"""
from __future__ import annotations


def med(x):
  """The MED errors of a uint8 tensor (..., H, W), folded, as uint8: the
  tinygrad form of jetlink.lossless.encode."""
  from tinygrad import dtypes
  x = x.cast(dtypes.int32)
  p = x.pad(((0, 0),) * (x.ndim - 2) + ((1, 0), (1, 0)))
  a, b, c = p[..., 1:, :-1], p[..., :-1, 1:], p[..., :-1, :-1]
  mx, mn = a.maximum(b), a.minimum(b)
  r = (x - (c >= mx).where(mn, (c <= mn).where(mx, a + b - c)) + 256) % 256
  return (r < 128).where(r * 2, (256 - r) * 2 - 1).cast(dtypes.uint8)
