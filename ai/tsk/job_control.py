"""Cooperative cancel for long-running TSK panda jobs."""

from __future__ import annotations

import threading

_cancel_event = threading.Event()


def clear_cancel() -> None:
  _cancel_event.clear()


def request_cancel() -> None:
  _cancel_event.set()


def is_cancelled() -> bool:
  return _cancel_event.is_set()
