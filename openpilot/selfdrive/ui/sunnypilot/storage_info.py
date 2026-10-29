"""
Copyright (c) 2026-, mouxan.

Storage usage helpers for the on-device Storage panel.

Pure functions over paths so the math is testable on a PC without the
hardware stack: each category is a label, the directory it occupies and the
human-readable size on disk. Deletion lives in the panel because it also
clears the params a downloader keys off (see settings/storage.py).
"""
from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass


MB = 1024 ** 2
GB = 1024 ** 3


@dataclass(frozen=True)
class DiskUsage:
  total: int
  used: int
  free: int

  @property
  def used_fraction(self) -> float:
    return (self.used / self.total) if self.total else 0.0


def disk_usage(path: str) -> DiskUsage | None:
  """Total/used/free bytes of the filesystem backing `path`, or None when it
  cannot be stat-ed (a PC without the device mount)."""
  try:
    st = os.statvfs(path)
  except (OSError, AttributeError):
    return None
  total = st.f_blocks * st.f_frsize
  free = st.f_bavail * st.f_frsize
  return DiskUsage(total=total, used=total - st.f_bfree * st.f_frsize, free=free)


def directory_size(path: str) -> int:
  """Recursive bytes under a directory; 0 when it is absent. Symlinks are not
  followed, so a linked path never counts its target twice."""
  total = 0
  if not os.path.isdir(path):
    return 0
  stack = [path]
  while stack:
    current = stack.pop()
    try:
      with os.scandir(current) as entries:
        for entry in entries:
          if entry.is_symlink():
            continue
          if entry.is_file(follow_symlinks=False):
            with contextlib.suppress(OSError):
              total += entry.stat(follow_symlinks=False).st_size
          elif entry.is_dir(follow_symlinks=False):
            stack.append(entry.path)
    except OSError:
      pass
  return total


def format_size(num_bytes: int) -> str:
  """'12.34 MB' / '1.20 GB', matching the rest of the settings UI."""
  if num_bytes >= GB:
    return f"{num_bytes / GB:.2f} GB"
  return f"{num_bytes / MB:.2f} MB"
