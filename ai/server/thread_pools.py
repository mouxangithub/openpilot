"""Dedicated thread pools — avoid blocking HTTP on heavy background jobs."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

_IO_POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="aid-io")


def io_executor() -> ThreadPoolExecutor:
  return _IO_POOL
