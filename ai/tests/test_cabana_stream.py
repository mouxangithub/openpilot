"""Stream abstraction / decimation / cache-key tests."""

from __future__ import annotations

import ai.tests.bootstrap_pc  # noqa: F401  # PC mocks before ai imports
import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from ai.services.cabana.decoder import get_decoder  # noqa: F401  (decoder smoke import)
from ai.services.cabana.live import LiveCanBroadcaster
from ai.services.cabana.replay import (
  CACHE_VERSION,
  MAX_REPLAY_FRAMES,
  _decimate,
  _load_route_cache,
  _route_cache_file,
  _save_route_cache,
)
from ai.services.cabana.replay_stream import ReplayStream
from ai.services.cabana.stream_base import conforms


def _frame(t: float, bus: int = 0, addr: int = 0x50, data: str = "aa") -> dict:
  return {"time": t, "bus": bus, "address": addr, "data": data}


class StreamProtocolTest(unittest.TestCase):
  def test_live_broadcaster_conforms(self):
    b = LiveCanBroadcaster()
    self.assertTrue(conforms(b))
    self.assertEqual(b.mode, "live")
    for name in ("start", "stop", "messages", "last_msgs", "subscribe", "unsubscribe", "seek", "speed"):
      self.assertTrue(callable(getattr(b, name)), name)

  def test_replay_stream_conforms(self):
    s = ReplayStream("no-such-route")
    self.assertTrue(conforms(s))
    self.assertEqual(s.mode, "replay")
    self.assertIsNone(s.route_path)
    self.assertEqual(s.qlogs, [])
    self.assertEqual(s.rlogs, [])

  def test_replay_stream_seek_speed_state(self):
    s = ReplayStream("no-such-route")
    s.speed(50.0)
    s.seek(3.5)
    self.assertEqual(s._speed, 10.0)  # clamped to 10
    self.assertEqual(s.take_seek(), 3.5)
    self.assertIsNone(s.take_seek())  # consumed

  def test_replay_stream_tick_dedup(self):
    # Legacy prev_sig semantics preserved: sig = (frame_time, data), so a repeat
    # frame with a new timestamp is re-emitted; the WS layer compacts per address.
    s = ReplayStream("no-such-route")
    s.all_frames = [
      _frame(10.0, data="aa"),
      _frame(10.1, data="aa"),
      _frame(10.2, data="bb"),
    ]
    s.first_time = 10.0
    delta, progress = s.tick(10.15)
    self.assertAlmostEqual(progress, 0.15)
    self.assertEqual([f["data"] for f in delta], ["aa", "aa"])
    delta2, _ = s.tick(10.30)
    self.assertEqual([f["data"] for f in delta2], ["bb"])
    # prev_sig tracks the latest frame per (bus, address)
    self.assertEqual(s.prev_sig[(0, 0x50)], (10.2, "bb"))

  def test_replay_stream_messages_filter(self):
    s = ReplayStream("no-such-route")
    s.all_frames = [_frame(10.0, addr=0x50), _frame(10.5, addr=0x140), _frame(11.0, addr=0x50)]
    got = s.messages(0x50, 10.0, 11.0)
    self.assertEqual(len(got), 2)
    self.assertEqual([f["time"] for f in got], [10.0, 11.0])

  def test_replay_stream_last_msgs(self):
    s = ReplayStream("no-such-route")
    s.all_frames = [_frame(10.0, bus=0, addr=0x50), _frame(10.5, bus=1, addr=0x50)]
    last = s.last_msgs()
    self.assertEqual(set(last.keys()), {(0, 0x50), (1, 0x50)})


class DecimateTest(unittest.TestCase):
  def test_under_limit_unchanged(self):
    frames = [_frame(float(i)) for i in range(100)]
    out, decimated = _decimate(frames, max_n=MAX_REPLAY_FRAMES)
    self.assertFalse(decimated)
    self.assertEqual(len(out), 100)

  def test_over_limit_stride(self):
    n = MAX_REPLAY_FRAMES * 2 + 10
    frames = [_frame(float(i)) for i in range(n)]
    out, decimated = _decimate(frames)
    self.assertTrue(decimated)
    stride = max(1, n // MAX_REPLAY_FRAMES)
    self.assertEqual(len(out), len(range(0, n, stride)))
    self.assertEqual(out[0]["time"], 0.0)

  def test_exact_limit_unchanged(self):
    frames = [_frame(float(i)) for i in range(MAX_REPLAY_FRAMES)]
    out, decimated = _decimate(frames)
    self.assertFalse(decimated)
    self.assertEqual(len(out), MAX_REPLAY_FRAMES)


class _FakeLiveWs:
  """Minimal WS stand-in recording broadcast payloads."""

  def __init__(self):
    self.sent: list[dict] = []

  async def send_str(self, s: str) -> None:
    self.sent.append(json.loads(s))


class _DeadLiveWs:
  """WS stand-in whose send always fails."""

  async def send_str(self, s: str) -> None:
    raise RuntimeError("connection gone")


class LiveFilterDeliveryTest(unittest.IsolatedAsyncioTestCase):
  """Regression: filter-suppressed changes must stay pending, not marked sent."""

  async def test_filter_suppressed_change_delivered_after_clear(self):
    b = LiveCanBroadcaster()
    ws = _FakeLiveWs()
    b._clients.add(ws)
    b.set_filter(ws, {0x140})
    b._latest = {
      (0, 0x50): _frame(1.0, addr=0x50, data="aa"),
      (0, 0x140): _frame(1.0, addr=0x140, data="bb"),
    }
    await b._broadcast()
    seen = {f["address"] for p in ws.sent for f in p["frames"]}
    self.assertNotIn(0x50, seen)
    self.assertIn(0x140, seen)

    # 0x50 changes while the filter is active: still suppressed and still pending.
    b._latest[(0, 0x50)] = _frame(2.0, addr=0x50, data="cc")
    await b._broadcast()
    seen = {f["address"] for p in ws.sent for f in p["frames"]}
    self.assertNotIn(0x50, seen)
    self.assertEqual(b._last_sent.get((0, 0x50)), None)

    # Clearing the filter must deliver the previously suppressed change.
    b.set_filter(ws, None)
    await b._broadcast()
    delivered = [(f["address"], f["data"]) for p in ws.sent for f in p["frames"]]
    self.assertIn((0x50, "cc"), delivered)
    self.assertEqual(b._last_sent[(0, 0x50)], (2.0, "cc"))

  async def test_send_failure_not_marked_sent(self):
    b = LiveCanBroadcaster()
    dead = _DeadLiveWs()
    b._clients.add(dead)
    b._latest = {(0, 0x50): _frame(1.0, addr=0x50, data="aa")}
    await b._broadcast()
    self.assertEqual(b._last_sent, {})
    self.assertEqual(b._clients, set())

    # A working client joining later still receives the pending frame.
    ws = _FakeLiveWs()
    b._clients.add(ws)
    await b._broadcast()
    self.assertEqual(b._last_sent[(0, 0x50)], (1.0, "aa"))
    self.assertTrue(any(f["address"] == 0x50 for p in ws.sent for f in p["frames"]))


class RouteCacheKeyTest(unittest.TestCase):
  def setUp(self):
    self._tmp = tempfile.TemporaryDirectory()
    self.route_dir = Path(self._tmp.name) / "2026-07-08--14-30-00--abc--0"
    self.route_dir.mkdir(parents=True)

  def tearDown(self):
    self._tmp.cleanup()

  def _patched_cache_dir(self, tmp: Path):
    tmp.mkdir(parents=True, exist_ok=True)
    return patch("ai.services.cabana.replay._cabana_cache_dir", return_value=tmp)

  def test_cache_key_uses_resolved_path(self):
    with self._patched_cache_dir(Path(self._tmp.name)):
      f1 = _route_cache_file(self.route_dir)
      self.assertTrue(f1.name.endswith(f"_v{CACHE_VERSION}.json.gz"))
      digest = f1.name.split("_")[0]
      self.assertEqual(len(digest), 16)
      import hashlib
      expected = hashlib.sha1(str(self.route_dir.resolve()).encode("utf-8")).hexdigest()[:16]
      self.assertEqual(digest, expected)

  def test_save_load_roundtrip(self):
    cache_dir = Path(self._tmp.name) / "cache"
    frames = [_frame(float(i)) for i in range(10)]
    with self._patched_cache_dir(cache_dir):
      _save_route_cache(self.route_dir, frames, decimated=False, full=False)
      loaded = _load_route_cache(self.route_dir, want_full=False)
    self.assertIsNotNone(loaded)
    self.assertEqual(len(loaded), 10)

  def test_load_rejects_wrong_route_name(self):
    cache_dir = Path(self._tmp.name) / "cache2"
    frames = [_frame(float(i)) for i in range(5)]
    with self._patched_cache_dir(cache_dir):
      _save_route_cache(self.route_dir, frames, decimated=False, full=False)
      path = _route_cache_file(self.route_dir)
      raw = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
      raw["route"] = "some-other-route"
      path.write_bytes(gzip.compress(json.dumps(raw).encode("utf-8")))
      self.assertIsNone(_load_route_cache(self.route_dir, want_full=False))

  def test_load_rejects_old_version(self):
    cache_dir = Path(self._tmp.name) / "cache3"
    frames = [_frame(float(i)) for i in range(5)]
    with self._patched_cache_dir(cache_dir):
      _save_route_cache(self.route_dir, frames, decimated=False, full=False)
      path = _route_cache_file(self.route_dir)
      raw = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
      raw["version"] = CACHE_VERSION - 1
      path.write_bytes(gzip.compress(json.dumps(raw).encode("utf-8")))
      self.assertIsNone(_load_route_cache(self.route_dir, want_full=False))


if __name__ == "__main__":
  unittest.main()
