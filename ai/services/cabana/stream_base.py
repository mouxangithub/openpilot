"""Unified stream abstraction (mirrors desktop tools/cabana AbstractStream)."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, TypedDict


class CanFrame(TypedDict):
  address: int
  bus: int
  data: str  # hex string
  time: float


FrameCallback = Callable[[list[CanFrame]], None]


class StreamSource(Protocol):
  """Protocol shared by live and replay CAN sources.

  ``mode`` is "live" | "replay". ``messages(address, t0, t1)`` mirrors the
  desktop eventsInRange semantics: frames matching ``address`` with
  ``t0 <= time <= t1``, sorted by time.
  """

  mode: str

  def start(self) -> None: ...

  def stop(self) -> None: ...

  def messages(self, address: int, t0: float, t1: float) -> list[CanFrame]: ...

  def last_msgs(self) -> dict[tuple[int, int], CanFrame]: ...

  def subscribe(self, cb: FrameCallback) -> None: ...

  def unsubscribe(self, cb: FrameCallback) -> None: ...

  def seek(self, t: float) -> None: ...

  def speed(self, v: float) -> None: ...


def conforms(source: Any) -> bool:
  """Runtime check that an object satisfies the StreamSource protocol shape."""
  for name in ("mode", "start", "stop", "messages", "last_msgs", "subscribe", "unsubscribe", "seek", "speed"):
    if not hasattr(source, name):
      return False
  return True
