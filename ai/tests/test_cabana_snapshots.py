"""Cabana replay snapshot / seek-state helpers (no LogReader)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from ai.services.cabana.replay_util import build_replay_snapshots, latest_frames_at_rel


def _frame(t: float, bus: int, addr: int, data: str) -> dict:
  return {"time": t, "bus": bus, "address": addr, "data": data}


class CabanaSnapshotTest(unittest.TestCase):
  def test_snapshot_progress_is_route_relative(self):
    frames = [
      _frame(1000.0, 0, 0x50, "aa"),
      _frame(1000.5, 0, 0x140, "bb"),
      _frame(1001.0, 0, 0x50, "cc"),
    ]
    snaps = build_replay_snapshots(frames, interval=0.25)
    self.assertTrue(snaps)
    self.assertGreaterEqual(snaps[0][0], 0.0)
    self.assertLessEqual(snaps[-1][0], 1.0 + 1e-6)

  def test_snapshot_progress_not_confused_with_mono_time(self):
    """Regression: comparing snapshot progress to first_time+start skips all snapshots."""
    frames = [_frame(1_000_000_000.0 + i * 0.1, 0, 0x50, f"{i:02x}") for i in range(200)]
    snaps = build_replay_snapshots(frames, interval=0.25)
    self.assertTrue(snaps)
    first_time = frames[0]["time"]
    start_time = 0.0
    snap_idx = 0
    while snap_idx < len(snaps) and snaps[snap_idx][0] < start_time:
      snap_idx += 1
    self.assertLess(snap_idx, len(snaps))
    wrong_idx = 0
    while wrong_idx < len(snaps) and snaps[wrong_idx][0] < first_time + start_time:
      wrong_idx += 1
    self.assertEqual(wrong_idx, len(snaps))

    frames = [
      _frame(10.0, 0, 0x50, "01"),
      _frame(11.0, 0, 0x140, "02"),
      _frame(12.0, 0, 0x50, "03"),
      _frame(13.0, 1, 0x60, "04"),
    ]
    at_1 = latest_frames_at_rel(frames, 1.0, 10.0)
    addrs = sorted((f["bus"], f["address"], f["data"]) for f in at_1)
    self.assertEqual(addrs, [(0, 0x50, "01"), (0, 0x140, "02")])

    at_2 = latest_frames_at_rel(frames, 2.0, 10.0)
    addrs2 = sorted((f["bus"], f["address"], f["data"]) for f in at_2)
    self.assertEqual(addrs2, [(0, 0x50, "03"), (0, 0x140, "02")])

    at_end = latest_frames_at_rel(frames, 99.0, 10.0)
    self.assertEqual(len(at_end), 3)


if __name__ == "__main__":
  unittest.main()
