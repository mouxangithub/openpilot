"""A heartbeat file that lets the manager notice a process that hung.

``restart_if_crash`` only catches a process that died. A process that is
still alive but stopped making progress looks identical from the outside:
it holds its resources, it answers no error, and the car keeps waiting for
a message that never comes. That is the shape of the failure we hit where
camerad restarted and modeld stayed wedged forever.

A monitored process writes the current monotonic timestamp into a small file
every time it finishes a unit of work. The manager reads that file and, when
the timestamp is too old, restarts the process.

The module deliberately imports nothing from openpilot so it can be unit
tested on a PC and so the daemon can use it without pulling in the logging
chain.
"""
import os
import platform
import struct
import time

# The heartbeat files live next to the other shared memory state. On macOS
# /dev/shm does not exist, so the temporary directory is used instead.
SHM_PATH = "/tmp" if platform.system() == "Darwin" else "/dev/shm"

WATCHDOG_FN = f"{SHM_PATH}/wd_"

# The heartbeat is written at most once a second. A process that renders at
# 60Hz does not need 60 writes a second, and the file would be pointless
# churn.
KICK_THROTTLE_S = 1.0

# An error writing the heartbeat is worth reporting, but not once a frame.
ERROR_LOG_THROTTLE_S = 5.0

_last_kick = 0.0
_last_error_log = 0.0


def _now_ns() -> int:
  """Nanoseconds on the clock the C++ side writes.

  ``nanos_since_boot()`` in common/timing.h reads CLOCK_BOOTTIME. Time
  monotonic in Python is CLOCK_MONOTONIC, which differs by the time the
  device has spent suspended. On a car that is normally zero, but a
  heartbeat written on one clock and compared against the other is wrong by
  an unknown amount, so the same clock is used on both sides.
  """
  try:
    return time.clock_gettime_ns(time.CLOCK_BOOTTIME)
  except (AttributeError, OSError, TypeError):
    # CLOCK_BOOTTIME does not exist on macOS or Windows.
    return time.monotonic_ns()


def watchdog_path(pid: int) -> str:
  """The heartbeat file of a process."""
  return f"{WATCHDOG_FN}{pid}"


def kick_watchdog() -> bool:
  """Record that this process is still making progress.

  Returns True when the heartbeat was written or was skipped because the
  last one is recent enough, and False when the write failed.
  """
  global _last_kick, _last_error_log
  now_ns = _now_ns()
  current_time = now_ns / 1e9

  if current_time - _last_kick < KICK_THROTTLE_S:
    return True

  try:
    with open(watchdog_path(os.getpid()), 'wb') as f:
      f.write(struct.pack('<Q', now_ns))
      f.flush()
    _last_kick = current_time
    return True
  except OSError:
    if current_time - _last_error_log >= ERROR_LOG_THROTTLE_S:
      _last_error_log = current_time
    return False


def read_watchdog_time(pid: int) -> float | None:
  """The boot-clock timestamp of a process's last heartbeat.

  Returns None when the file is missing or unreadable, which means the
  process has not reported in yet.
  """
  try:
    with open(watchdog_path(pid), 'rb') as f:
      raw = f.read()
    if len(raw) != struct.calcsize('Q'):
      return None
    return struct.unpack('Q', raw)[0] / 1e9
  except (OSError, struct.error):
    return None


def watchdog_timed_out(pid: int, max_dt: float | None) -> float | None:
  """How long ago the last heartbeat was, or None when the process is fine.

  Returns the elapsed time when it is larger than ``max_dt`` so the caller
  can restart the process, and None otherwise.
  """
  if max_dt is None:
    return None
  last = read_watchdog_time(pid)
  if last is None:
    return None
  dt = (_now_ns() / 1e9) - last
  return dt if dt > max_dt else None


def clear_watchdog(pid: int) -> None:
  """Remove a process's heartbeat file."""
  try:
    os.unlink(watchdog_path(pid))
  except OSError:
    pass


def pid_alive(pid: int) -> bool:
  """Whether a process with this pid exists.

  ``os.kill(pid, 0)`` is the portable probe: it answers "does this pid
  exist and may I signal it" without delivering anything. An /proc lookup
  would be simpler but does not exist on macOS or Windows, and the manager
  runs on a PC too (process replay), where it would make every process look
  dead and sweep live heartbeats away.
  """
  if pid <= 0:
    return False
  try:
    os.kill(pid, 0)
  except ProcessLookupError:
    return False
  except PermissionError:
    # Exists, just not ours.
    return True
  except OSError:
    return False
  return True


def sweep_stale_heartbeats() -> int:
  """Remove heartbeat files whose process is gone; returns how many.

  A manager restart, or any process killed while it still had a heartbeat
  file, leaves that file behind. The manager only reads files for the pids
  it watches, so a leftover is harmless to it -- but it accumulates in
  /dev/shm over restarts, and anything that scans the directory would see
  ghosts of processes that no longer exist. Swept once at manager start.
  """
  prefix = os.path.basename(WATCHDOG_FN)
  # Scan the directory the prefix lives in, not SHM_PATH: the two are the
  # same in production, and this keeps the function patchable in tests.
  directory = os.path.dirname(WATCHDOG_FN) or "."
  try:
    names = os.listdir(directory)
  except OSError:
    return 0

  removed = 0
  for name in names:
    if not name.startswith(prefix):
      continue
    pid_text = name[len(prefix):]
    if not pid_text.isdigit():
      continue
    pid = int(pid_text)
    if pid_alive(pid):
      continue
    clear_watchdog(pid)
    if not os.path.exists(watchdog_path(pid)):
      removed += 1
  return removed
