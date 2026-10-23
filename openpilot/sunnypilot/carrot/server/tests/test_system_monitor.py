"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Tests for services/system_monitor.py against a fake /proc tree.

Everything the monitor needs (proc root, clock tick, page size, storage root,
monotonic clock) is injected, so these run on any OS without touching the real
/proc and without any real sleeping: the clock is a fake we advance by hand.
"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openpilot.sunnypilot.carrot.server.services.system_monitor import SystemMonitor


class FakeClock:
  def __init__(self):
    self.now = 1000.0

  def monotonic(self):
    return self.now

  def advance(self, seconds):
    self.now += seconds


class FakeProc:
  """Minimal /proc tree: stat, meminfo, uptime and a few pid directories."""

  def __init__(self, root: Path):
    self.root = root
    root.mkdir(parents=True, exist_ok=True)
    self.set_cpu({"cpu": (1000, 800), "cpu0": (1000, 900)})
    self.set_meminfo(2048000, 1024000)
    self.set_uptime(1234.5)
    self.set_process(123, "managed", utime=10, stime=10, starttime=100, rss=2560,
                     cmdline=b"python3.12\x00-m\x00openpilot.system.managed_processes\x00")
    self.set_process(456, "kworker", state="I", utime=0, stime=0, starttime=50, rss=0)

  def _write(self, name: str, text: str):
    (self.root / name).write_text(text)

  def set_cpu(self, cores: dict[str, tuple[int, int]]):
    # total, idle  -> expanded as "user nice system idle iowait irq softirq steal"
    lines = []
    for name, (total, idle) in cores.items():
      busy = total - idle
      lines.append(f"{name} {busy - 100} 0 100 {idle - 100} 0 0 0 100")
    self._write("stat", "\n".join(lines) + "\n")

  def set_meminfo(self, total_kib: int, available_kib: int):
    self._write("meminfo", f"MemTotal:  {total_kib} kB\nMemAvailable:  {available_kib} kB\n")

  def set_uptime(self, seconds: float):
    self._write("uptime", f"{seconds} {seconds * 2}\n")

  def set_process(self, pid: int, comm: str, *, state: str = "S", utime: int = 0, stime: int = 0,
                  starttime: int = 0, rss: int = 0, cmdline: bytes = b""):
    pid_dir = self.root / str(pid)
    pid_dir.mkdir(exist_ok=True)
    # fields after "comm)": state, 10 fillers, utime, stime, 6 fillers, starttime, filler, rss
    fields = [state] + ["0"] * 10 + [str(utime), str(stime)] + ["0"] * 6 + [str(starttime), "0", str(rss)]
    (pid_dir / "stat").write_text(f"{pid} ({comm}) {' '.join(fields)}\n")
    (pid_dir / "cmdline").write_bytes(cmdline)


class TestSystemMonitor(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    self.proc = FakeProc(Path(self.tmp.name) / "proc")
    self.storage = Path(self.tmp.name) / "data"
    self.storage.mkdir()
    self.clock = FakeClock()
    patcher = mock.patch("openpilot.sunnypilot.carrot.server.services.system_monitor.time", self.clock)
    patcher.start()
    self.addCleanup(patcher.stop)

  def _monitor(self, cache_seconds: float = 0.0) -> SystemMonitor:
    return SystemMonitor(self.proc.root, hz=100, page_size=4096,
                         storage_root=str(self.storage), cache_seconds=cache_seconds)

  def test_first_sample_reports_no_cpu_percent(self):
    snapshot = self._monitor().sample()
    self.assertIsNone(snapshot["cpuPercent"])
    self.assertIsNone(snapshot["sampleSeconds"])
    for core in snapshot["cores"]:
      self.assertIsNone(core["percent"])
    self.assertEqual({"totalMiB": 2000.0, "usedMiB": 1000.0, "availableMiB": 1000.0, "percent": 50.0},
                     snapshot["memory"])
    self.assertEqual(1234.5, snapshot["uptimeSeconds"])
    self.assertEqual(2, snapshot["processCount"])

  def test_second_sample_computes_cpu_percent(self):
    monitor = self._monitor()
    monitor.sample()
    self.clock.advance(10.0)
    self.proc.set_cpu({"cpu": (1100, 840), "cpu0": (1050, 930)})
    snapshot = monitor.sample()
    # overall: idle delta 40 over 100 -> 60% busy; cpu0: 30 over 50 -> 40% busy
    self.assertEqual(60.0, snapshot["cpuPercent"])
    self.assertEqual(10.0, snapshot["sampleSeconds"])
    self.assertEqual(40.0, snapshot["cores"][0]["percent"])

  def test_process_rows(self):
    monitor = self._monitor()
    monitor.sample()
    self.clock.advance(10.0)
    self.proc.set_cpu({"cpu": (1100, 840), "cpu0": (1050, 930)})
    self.proc.set_process(123, "managed", utime=30, stime=10, starttime=100, rss=2560,
                          cmdline=b"python3.12\x00-m\x00openpilot.system.managed_processes\x00")
    snapshot = monitor.sample()
    rows = {row["pid"]: row for row in snapshot["processes"]}
    managed = rows[123]
    # cmdline wins over comm; "-m module" collapses to the module name
    self.assertEqual("openpilot.system.managed_processes", managed["name"])
    self.assertFalse(managed["kernel"])
    self.assertEqual("S", managed["state"])
    # 20 new ticks (40 vs 20) out of 100 ticks of total cpu capacity
    self.assertEqual(20.0, managed["cpu"])
    # rss 2560 pages * 4096 bytes
    self.assertEqual(10.0, managed["memoryMiB"])
    kernel = rows[456]
    self.assertTrue(kernel["kernel"])
    self.assertEqual("kworker", kernel["name"])
    self.assertEqual("I", kernel["state"])

  def test_cached_name_survives_cmdline_disappearance(self):
    monitor = self._monitor()
    monitor.sample()
    self.clock.advance(10.0)
    (self.proc.root / "123" / "cmdline").unlink()  # process read its own args away
    snapshot = monitor.sample()
    managed = next(row for row in snapshot["processes"] if row["pid"] == 123)
    self.assertEqual("openpilot.system.managed_processes", managed["name"])

  def test_cache_window_returns_same_snapshot(self):
    monitor = self._monitor(cache_seconds=5.0)
    first = monitor.sample()
    self.clock.advance(1.0)
    self.assertIs(first, monitor.sample())  # inside the window: same object, no resample
    self.clock.advance(10.0)
    self.assertIsNot(first, monitor.sample())

  def test_missing_memtotal_raises(self):
    (self.proc.root / "meminfo").write_text("SwapTotal: 0 kB\n")
    with self.assertRaises(OSError):
      self._monitor().sample()

  def test_pid_reuse_is_not_confused(self):
    monitor = self._monitor()
    monitor.sample()
    self.clock.advance(10.0)
    self.proc.set_cpu({"cpu": (1100, 840), "cpu0": (1050, 930)})
    # pid 123 "restarts": new starttime, zeroed ticks. Old ticks must not leak into it.
    self.proc.set_process(123, "managed", utime=0, stime=0, starttime=999, rss=2560,
                          cmdline=b"python3.12\x00-m\x00openpilot.system.managed_processes\x00")
    snapshot = monitor.sample()
    managed = next(row for row in snapshot["processes"] if row["pid"] == 123)
    self.assertIsNone(managed["cpu"])


if __name__ == "__main__":
  unittest.main()
