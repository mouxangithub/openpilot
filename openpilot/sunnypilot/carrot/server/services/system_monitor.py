"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Read-only, request-driven Linux process snapshots for the web client.

Answers one question during remote support: WHICH process is eating the CPU
right now. Everything comes from /proc; nothing is written, nothing is sent
anywhere. CPU percentages are deltas between consecutive samples, so the
first call reports ``None`` for CPU and the second one (>= cache window
apart) is meaningful.

Portability notes, on purpose:
- ``pwd`` and ``os.sysconf`` do not exist on Windows, so both are guarded and
  the clock tick / page size can be injected for tests.
- The /proc root and the storage root are injectable, which keeps the parsing
  logic testable on any OS against a fake tree.
- No ``time.time()`` (banned repo-wide); wall clock is reported via datetime.
"""

import os
import threading
import time
from datetime import datetime, UTC
from pathlib import Path
from shutil import disk_usage

_EMPTY_SNAPSHOT_KEYS = ("cpuPercent", "cores", "memory", "storage", "uptimeSeconds", "processes")


def _default_hz() -> int:
  try:
    return int(os.sysconf("SC_CLK_TCK"))
  except (AttributeError, OSError, ValueError):
    return 100


def _default_page_size() -> int:
  try:
    return int(os.sysconf("SC_PAGE_SIZE"))
  except (AttributeError, OSError, ValueError):
    return 4096


def _user_name(uid: int) -> str:
  try:
    import pwd  # pylint: disable=import-outside-toplevel  # not available on Windows
    return pwd.getpwuid(uid).pw_name
  except ImportError:
    return str(uid)
  except KeyError:
    return str(uid)


class SystemMonitor:
  def __init__(self, root="/proc", *, hz=None, page_size=None, storage_root=None,
               cache_seconds: float = 1.5):
    self.root = Path(root)
    self.hz = int(hz) if hz is not None else _default_hz()
    self.page = int(page_size) if page_size is not None else _default_page_size()
    self.storage_root = storage_root
    self.cache_seconds = cache_seconds
    self.lock = threading.Lock()
    self.previous: dict[tuple[int, int], int] = {}
    self.names: dict[tuple[int, int], dict] = {}
    self.cpu_previous: dict[str, tuple[int, int]] = {}
    self.previous_time: float | None = None
    self.cached: dict | None = None

  # ------------------------------ sampling -----------------------------------

  def _read_cpu_lines(self) -> dict[str, tuple[int, int]]:
    out = {}
    for line in (self.root / "stat").read_text().splitlines():
      values = line.split()
      if not values or not values[0].startswith("cpu"):
        continue
      numbers = [int(value) for value in values[1:9]]
      out[values[0]] = (sum(numbers), numbers[3] + numbers[4])
    return out

  def _read_memory(self) -> dict[str, int]:
    return {
      line.split(":", 1)[0]: int(line.split()[1])
      for line in (self.root / "meminfo").read_text().splitlines() if ":" in line
    }

  def _storage(self) -> dict[str, float]:
    root = self.storage_root
    if root is None:
      root = "/data" if Path("/data").is_dir() else "/"
    usage = disk_usage(root)
    return {"usedGiB": round(usage.used / 1073741824, 1), "totalGiB": round(usage.total / 1073741824, 1)}

  def _process_row(self, path: Path) -> tuple[dict, tuple[tuple[int, int], int] | None] | None:
    try:
      raw = (path / "stat").read_text()
      end = raw.rindex(")")
      fields = raw[end + 2:].split()
      pid = int(path.name)
      identity = (pid, int(fields[19]))  # pid + starttime: stable across pid reuse
      ticks = int(fields[11]) + int(fields[12])
      info = self.names.get(identity)
      if info is None:
        args = [part for part in (path / "cmdline").read_bytes().decode(errors="replace").split("\0") if part]
        comm = raw[raw.index("(") + 1:end]
        name = comm
        if args:
          name = args[0]
          # "python -m openpilot.x.y" reads far better than "python3.12"
          base = Path(name).name
          if "python" in base and len(args) > 1:
            name = args[2] if args[1] == "-m" and len(args) > 2 else (args[1] if not args[1].startswith("-") else base)
        info = {"name": name.removeprefix("/data/openpilot/"), "user": _user_name(path.stat().st_uid),
                "kernel": not args}
        self.names[identity] = info
      row = {"pid": pid, **info, "state": fields[0],
             "memoryMiB": round(max(0, int(fields[21])) * self.page / 1048576, 1)}
      return row, (identity, ticks)
    except (OSError, ValueError, IndexError):
      return None

  def sample(self) -> dict:
    with self.lock:
      now = datetime.now(UTC).isoformat(timespec="seconds")
      mono = time.monotonic()
      if self.cached is not None and self.previous_time is not None and mono - self.previous_time < self.cache_seconds:
        return self.cached
      elapsed = mono - self.previous_time if self.previous_time is not None else None

      cpu_now = self._read_cpu_lines()
      overall = None
      cpu_capacity = None
      cores = []
      for key, pair in cpu_now.items():
        old = self.cpu_previous.get(key)
        percent = None
        if old and pair[0] > old[0]:
          idle_delta = pair[1] - old[1]
          total_delta = pair[0] - old[0]
          percent = round(max(0.0, min(100.0, 100.0 * (1.0 - idle_delta / total_delta))), 1)
        if key == "cpu":
          overall = percent
          if percent is not None:
            cpu_capacity = pair[0] - old[0]
        else:
          cores.append({"name": key, "percent": percent})

      rows = []
      ticks = {}
      for path in self.root.iterdir():
        if not path.name.isdigit():
          continue
        parsed = self._process_row(path)
        if parsed is None:
          continue
        row, (identity, current) = parsed
        ticks[identity] = current
        cpu = None
        if cpu_capacity and identity in self.previous and current >= self.previous[identity]:
          cpu = round(min(100.0, (current - self.previous[identity]) / cpu_capacity * 100), 1)
        rows.append({"cpu": cpu, **row})

      memory = self._read_memory()
      total_kib = memory.get("MemTotal")
      if not total_kib or total_kib <= 0:
        raise OSError("MemTotal is unavailable")
      total = total_kib / 1024
      available = memory.get("MemAvailable", memory.get("MemFree", 0)) / 1024

      self.cached = {
        "sampledAt": now,
        "sampleSeconds": round(elapsed, 2) if elapsed is not None else None,
        "cpuPercent": overall,
        "cores": cores,
        "memory": {"totalMiB": round(total, 1), "usedMiB": round(total - available, 1),
                   "availableMiB": round(available, 1),
                   "percent": round(100.0 * (total - available) / total, 1)},
        "storage": self._storage(),
        "uptimeSeconds": float((self.root / "uptime").read_text().split()[0]),
        "processCount": len(rows),
        "processes": rows,
      }
      self.previous, self.names, self.cpu_previous, self.previous_time = ticks, self.names, cpu_now, mono
      return self.cached


_singleton: SystemMonitor | None = None
_singleton_lock = threading.Lock()


def get_system_monitor() -> SystemMonitor:
  global _singleton
  with _singleton_lock:
    if _singleton is None:
      _singleton = SystemMonitor()
    return _singleton
