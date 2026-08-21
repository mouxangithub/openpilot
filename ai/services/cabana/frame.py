"""CAN frame helpers."""
from __future__ import annotations
from typing import Any


def can_frame_to_dict(cf, mono_time: float | None = None) -> dict[str, Any]:
  return {
    "address": int(cf.address),
    "bus": int(cf.src),
    "data": cf.dat.hex(),
    "time": mono_time if mono_time is not None else 0.0,
  }


# Legacy alias
_can_frame_to_dict = can_frame_to_dict
