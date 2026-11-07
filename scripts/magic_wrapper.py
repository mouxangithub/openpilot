#!/usr/bin/env python3
"""Keep /usr/comma/magic.py running if the system magic.service has failed.

magic.py provides the /tmp/drmfd.sock Unix socket that passes a DRM master file
descriptor to the openpilot UI. On devices where the touchscreen driver did not
probe, magic.service fails during boot because raylib's COMMA platform cannot
open /dev/input/event2. This wrapper waits for the fake_touch fallback device to
appear, then execs the system magic.py so the DRM socket is created.
"""
import os
import socket
import sys
import time

MAGIC_PY = "/usr/comma/magic.py"
DRMFD_SOCK = "/tmp/drmfd.sock"
TOUCH_EVENT = "/dev/input/event2"


def wait_for_touch(timeout_s: float = 30.0) -> bool:
  deadline = time.monotonic() + timeout_s
  while time.monotonic() < deadline:
    if os.path.exists(TOUCH_EVENT):
      return True
    time.sleep(0.5)
  return os.path.exists(TOUCH_EVENT)


def drmfd_is_serving() -> bool:
  """Return True only if the socket exists and accepts connections."""
  if not os.path.exists(DRMFD_SOCK):
    return False
  try:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
      s.settimeout(1.0)
      s.connect(DRMFD_SOCK)
      return True
  except (OSError, ConnectionRefusedError):
    return False


def main() -> int:
  if drmfd_is_serving():
    # magic.py is already serving; nothing to do.
    return 0

  # Remove a stale socket file left by a dead magic.py/systemd instance so the
  # new instance can bind the path.
  try:
    os.unlink(DRMFD_SOCK)
  except FileNotFoundError:
    pass
  except OSError as e:
    print(f"magic_wrapper: failed to remove stale {DRMFD_SOCK}: {e}", file=sys.stderr)
    return 1

  if not wait_for_touch():
    print(f"magic_wrapper: {TOUCH_EVENT} did not appear", file=sys.stderr)
    return 1

  if not os.path.isfile(MAGIC_PY):
    print(f"magic_wrapper: {MAGIC_PY} not found", file=sys.stderr)
    return 1

  # Replace this process with magic.py; launch_chffrplus keep_alive will restart
  # us if it exits.
  py = sys.executable
  os.execv(py, [py, "-u", MAGIC_PY])
  return 1


if __name__ == "__main__":
  sys.exit(main())
