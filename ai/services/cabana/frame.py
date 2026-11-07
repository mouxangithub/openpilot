"""CAN frame helpers."""
from __future__ import annotations
import base64
from typing import Any


def can_frame_to_dict(cf, mono_time: float | None = None, encoding: str = "hex") -> dict[str, Any]:
  """Convert a cereal CAN frame to a dict; data is hex (default) or base64."""
  dat = bytes(cf.dat)
  data = base64.b64encode(dat).decode("ascii") if encoding == "base64" else dat.hex()
  return {
    "address": int(cf.address),
    "bus": int(cf.src),
    "data": data,
    "time": mono_time if mono_time is not None else 0.0,
  }


def encode_frame_data(data_hex: str, encoding: str = "hex") -> str:
  """Convert an already-extracted hex data string to the requested encoding."""
  if encoding == "base64":
    try:
      return base64.b64encode(bytes.fromhex(data_hex)).decode("ascii")
    except ValueError:
      return data_hex
  return data_hex


# Legacy alias
_can_frame_to_dict = can_frame_to_dict
