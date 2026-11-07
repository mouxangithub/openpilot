"""QR PNG data URLs for Web UI — uses openpilot.common.qrcode (no pyray / pip qrcode)."""

from __future__ import annotations

import base64
import importlib.util
import os
import struct
import zlib
from pathlib import Path
from typing import Any, Callable


def _load_qr_encoder() -> tuple[Any, Callable[[int], int]]:
  try:
    from openpilot.common.qrcode import _Qr, _capacity
    return _Qr, _capacity
  except Exception:
    pass

  root = os.environ.get("OPENPILOT_ROOT") or os.environ.get("OP_ROOT") or ""
  candidates = [
    Path(root) / "openpilot" / "common" / "qrcode.py",
    Path(__file__).resolve().parents[3] / "openpilot" / "common" / "qrcode.py",
  ]
  for path in candidates:
    if not path.is_file():
      continue
    spec = importlib.util.spec_from_file_location("_op_qrcode_encoder", path)
    if spec is None or spec.loader is None:
      continue
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._Qr, mod._capacity
  raise ImportError("openpilot.common.qrcode unavailable")


def _png_rgb(width: int, height: int, rgb: bytes) -> bytes:
  def chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

  raw = b"".join(b"\x00" + rgb[y * width * 3:(y + 1) * width * 3] for y in range(height))
  return (
    b"\x89PNG\r\n\x1a\n"
    + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    + chunk(b"IDAT", zlib.compress(raw, 9))
    + chunk(b"IEND", b"")
  )


def qr_data_url(text: str, *, scale: int = 8, border: int = 4) -> str:
  """Return a white-on-black PNG as a data: URL, or \"\" on failure."""
  try:
    _Qr, _capacity = _load_qr_encoder()

    raw = text.encode()
    for version in range(1, 21):
      count_bits = 8 if version <= 9 else 16
      if 4 + count_bits + len(raw) * 8 <= _capacity(version) * 8:
        break
    else:
      return ""

    modules = _Qr(version, raw).modules
    size = len(modules) + 2 * border
    pixel = size * scale
    rgb = bytearray(pixel * pixel * 3)
    for py in range(pixel):
      my = py // scale - border
      for px in range(pixel):
        mx = px // scale - border
        dark = 0 <= my < len(modules) and 0 <= mx < len(modules[0]) and modules[my][mx]
        i = (py * pixel + px) * 3
        rgb[i:i + 3] = (0, 0, 0) if dark else (255, 255, 255)
    b64 = base64.b64encode(_png_rgb(pixel, pixel, bytes(rgb))).decode("ascii")
    return f"data:image/png;base64,{b64}"
  except Exception:
    return ""
