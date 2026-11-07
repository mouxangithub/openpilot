"""Cabana frame query / export endpoint tests + segment addressing + cache LRU."""

from __future__ import annotations

import ai.tests.bootstrap_pc  # noqa: F401  # PC mocks before ai imports
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from ai.services.cabana.replay import (
  _load_route_cache,
  _prune_cabana_cache,
  _route_cache_file,
  _route_dir,
  _save_route_cache,
)

ROUTE_NAME = "2026-07-08--14-30-00--fr--0"
BASE_ABS = 1000.0


def _make_frames() -> list[dict]:
  """100 frames of 0x50 every 0.1s (first byte = i) + 20 frames of 0x140."""
  frames: list[dict] = []
  for i in range(100):
    frames.append({
      "time": BASE_ABS + i * 0.1,
      "bus": 0,
      "address": 0x50,
      "data": f"{i:02x}" + "00" * 7,
    })
  for i in range(20):
    frames.append({
      "time": BASE_ABS + i * 0.5,
      "bus": 0,
      "address": 0x140,
      "data": "ff" * 8,
    })
  frames.sort(key=lambda f: f["time"])
  return frames


def _fake_sig(name: str, address: int, *, start_bit: int, size: int, factor: float = 1.0,
              unit: str = "") -> dict:
  return {
    "address": address,
    "message": f"MSG_{address:X}",
    "signal": name,
    "start_bit": start_bit,
    "size": size,
    "little_endian": True,
    "signed": False,
    "factor": factor,
    "offset": 0.0,
    "unit": unit,
    "signal_type": 0,
  }


class FramesEndpointTest(AioHTTPTestCase):
  def setUp(self):
    super().setUp()
    self._tmpdir = tempfile.TemporaryDirectory()
    self.routes_dir = Path(self._tmpdir.name) / "routes"
    self.route_dir = self.routes_dir / ROUTE_NAME
    self.route_dir.mkdir(parents=True)
    self.cache_dir = Path(self._tmpdir.name) / "cache"
    self.cache_dir.mkdir()
    self.frames = _make_frames()
    with patch("ai.services.cabana.replay._cabana_cache_dir", return_value=self.cache_dir):
      _save_route_cache(self.route_dir, self.frames, decimated=False, full=False)
    self._patchers = [
      patch("ai.services.cabana.replay._get_routes_dir", return_value=self.routes_dir),
      patch("ai.services.cabana.replay._cabana_cache_dir", return_value=self.cache_dir),
    ]
    for p in self._patchers:
      p.start()

  def tearDown(self):
    for p in self._patchers:
      p.stop()
    self._tmpdir.cleanup()
    super().tearDown()

  async def get_application(self):
    import ai.services.cabana.app as cabana

    app = web.Application()
    cabana.register_routes(app, Path(__file__).parent)
    return app

  @unittest_run_loop
  async def test_frames_range_filter_sorted(self):
    resp = await self.client.get(f"/api/cabana/route/{ROUTE_NAME}/frames?address=0x50&t0=1.0&t1=3.0")
    self.assertEqual(resp.status, 200)
    data = await resp.json()
    self.assertTrue(data["ok"])
    self.assertEqual(data["address"], 0x50)
    frames = data["frames"]
    # rel times 1.0..3.0 inclusive at 0.1 steps -> 21 frames
    self.assertEqual(len(frames), 21)
    rels = [f["time"] for f in frames]
    self.assertEqual(rels, sorted(rels))
    self.assertGreaterEqual(rels[0], 1.0)
    self.assertLessEqual(rels[-1], 3.0)
    self.assertEqual(frames[0]["data"], "0a" + "00" * 7)

  @unittest_run_loop
  async def test_frames_requires_address(self):
    resp = await self.client.get(f"/api/cabana/route/{ROUTE_NAME}/frames")
    self.assertEqual(resp.status, 400)

  @unittest_run_loop
  async def test_frames_unknown_route_404(self):
    resp = await self.client.get("/api/cabana/route/no-such-route/frames?address=1")
    self.assertEqual(resp.status, 404)

  @unittest_run_loop
  async def test_frames_downsample_buckets_without_dbc(self):
    resp = await self.client.get(
      f"/api/cabana/route/{ROUTE_NAME}/frames?address=0x50&t0=1.0&t1=3.0&downsample=5"
    )
    data = await resp.json()
    self.assertTrue(data["ok"])
    buckets = data["buckets"]
    self.assertEqual(len(buckets), 5)
    # first-byte raw min/max per bucket: values 10..30 across 5 buckets
    self.assertEqual(sum(b["count"] for b in buckets), 21)
    self.assertEqual(buckets[0]["min"], 10)
    self.assertEqual(buckets[-1]["max"], 30)

  @unittest_run_loop
  async def test_frames_downsample_buckets_with_dbc(self):
    fake_table = {0x50: [_fake_sig("speed", 0x50, start_bit=0, size=8)]}
    with patch("ai.services.cabana.handlers._get_decoder", return_value=fake_table):
      resp = await self.client.get(
        f"/api/cabana/route/{ROUTE_NAME}/frames?address=0x50&t0=1.0&t1=3.0&downsample=2&dbc=fake"
      )
    data = await resp.json()
    self.assertTrue(data["ok"])
    buckets = data["buckets"]
    self.assertEqual(len(buckets), 2)
    sigs = buckets[0]["signals"]["speed"]
    # bucket 0 covers rel [1.0, 2.0) -> first bytes 10..19
    self.assertAlmostEqual(sigs["min"], 10.0)
    self.assertAlmostEqual(sigs["max"], 19.0)
    sigs1 = buckets[1]["signals"]["speed"]
    # bucket 1 covers rel [2.0, 3.0] -> first bytes 20..30
    self.assertAlmostEqual(sigs1["min"], 20.0)
    self.assertAlmostEqual(sigs1["max"], 30.0)

  @unittest_run_loop
  async def test_frames_decode_attaches_values(self):
    fake_table = {0x50: [_fake_sig("speed", 0x50, start_bit=0, size=8, factor=0.5)]}
    with patch("ai.services.cabana.handlers._get_decoder", return_value=fake_table):
      resp = await self.client.get(
        f"/api/cabana/route/{ROUTE_NAME}/frames?address=0x50&t0=0&t1=0.1&dbc=fake"
      )
    data = await resp.json()
    self.assertTrue(data["ok"])
    frames = data["frames"]
    self.assertEqual(len(frames), 2)
    self.assertAlmostEqual(frames[0]["values"]["speed"], 0.0)
    self.assertAlmostEqual(frames[1]["values"]["speed"], 0.5)

  @unittest_run_loop
  async def test_export_csv_default_columns(self):
    resp = await self.client.get(f"/api/cabana/route/{ROUTE_NAME}/export?address=0x50")
    self.assertEqual(resp.status, 200)
    self.assertEqual(resp.content_type, "text/csv")
    self.assertIn("attachment", resp.headers.get("Content-Disposition", ""))
    self.assertIn(".csv", resp.headers.get("Content-Disposition", ""))
    body = await resp.text()
    lines = body.strip().splitlines()
    self.assertEqual(lines[0], "time,bus,address,data_hex")
    # 100 frames of 0x50 -> 101 lines
    self.assertEqual(len(lines), 101)
    self.assertEqual(lines[1].split(",")[3], "0000000000000000")

  @unittest_run_loop
  async def test_export_csv_decoded_signals(self):
    fake_table = {0x50: [_fake_sig("speed", 0x50, start_bit=0, size=8, factor=0.5, unit="km/h")]}
    with patch("ai.services.cabana.handlers._get_decoder", return_value=fake_table):
      resp = await self.client.get(
        f"/api/cabana/route/{ROUTE_NAME}/export?address=0x50&decode=1&dbc=fake"
      )
    body = await resp.text()
    lines = body.strip().splitlines()
    self.assertEqual(lines[0], "time,bus,address,data_hex,speed(km/h)")
    # frame 2: raw 2 * 0.5 = 1.0
    self.assertEqual(lines[3].split(",")[4], "1.000")


class RouteSegmentAddressTest(unittest.TestCase):
  """A: `name/<digits>` segment addressing; traversal attempts rejected."""

  def setUp(self):
    self._tmp = tempfile.TemporaryDirectory()
    self.routes_dir = Path(self._tmp.name) / "routes"
    self.route_dir = self.routes_dir / "route--abc"
    (self.route_dir / "1").mkdir(parents=True)
    (self.route_dir / "1" / "rlog").write_bytes(b"x")
    (self.route_dir / "boot").mkdir()
    self._patch = patch("ai.services.cabana.replay._get_routes_dir", return_value=self.routes_dir)
    self._patch.start()

  def tearDown(self):
    self._patch.stop()
    self._tmp.cleanup()

  def test_plain_route_resolved(self):
    self.assertEqual(_route_dir("route--abc"), self.route_dir)

  def test_segment_route_resolved(self):
    self.assertEqual(_route_dir("route--abc/1"), self.route_dir / "1")

  def test_missing_segment_rejected(self):
    self.assertIsNone(_route_dir("route--abc/9"))

  def test_non_numeric_segment_rejected(self):
    self.assertIsNone(_route_dir("route--abc/boot"))
    self.assertIsNone(_route_dir("route--abc/abc"))

  def test_traversal_rejected(self):
    self.assertIsNone(_route_dir("route--abc/../route--abc/1"))
    self.assertIsNone(_route_dir("../routes/route--abc"))
    self.assertIsNone(_route_dir("route--abc/1/2"))

  def test_backslash_rejected(self):
    self.assertIsNone(_route_dir("route--abc\\1"))


class SegmentCacheRoundtripTest(unittest.TestCase):
  """Segment caches must not collide across routes with the same segment name."""

  def setUp(self):
    self._tmp = tempfile.TemporaryDirectory()
    self.cache_dir = Path(self._tmp.name) / "cache"
    self.cache_dir.mkdir()
    self.routes_dir = Path(self._tmp.name) / "routes"
    for name in ("routeA", "routeB"):
      (self.routes_dir / name / "1").mkdir(parents=True)

  def tearDown(self):
    self._tmp.cleanup()

  def test_segment_cache_disjoint(self):
    with patch("ai.services.cabana.replay._cabana_cache_dir", return_value=self.cache_dir):
      seg_a = self.routes_dir / "routeA" / "1"
      seg_b = self.routes_dir / "routeB" / "1"
      frames_a = [{"time": 1.0, "bus": 0, "address": 0x11, "data": "aa"}]
      frames_b = [{"time": 2.0, "bus": 0, "address": 0x22, "data": "bb"}]
      _save_route_cache(seg_a, frames_a, decimated=False, full=False)
      _save_route_cache(seg_b, frames_b, decimated=False, full=False)
      self.assertNotEqual(_route_cache_file(seg_a), _route_cache_file(seg_b))
      self.assertEqual(_load_route_cache(seg_a, want_full=False)[0]["address"], 0x11)
      self.assertEqual(_load_route_cache(seg_b, want_full=False)[0]["address"], 0x22)


class CacheLruTest(unittest.TestCase):
  """G: pruning keeps only the newest `keep` *.json.gz files."""

  def setUp(self):
    self._tmp = tempfile.TemporaryDirectory()
    self.cache_dir = Path(self._tmp.name) / "cache"
    self.cache_dir.mkdir()

  def tearDown(self):
    self._tmp.cleanup()

  def _create_file(self, name: str, mtime_offset: float) -> Path:
    path = self.cache_dir / name
    path.write_bytes(b"x")
    os.utime(path, (mtime_offset, mtime_offset))
    return path

  def test_keeps_newest_files(self):
    for i in range(7):
      self._create_file(f"{i:016x}_0_v3.json.gz", mtime_offset=1000.0 + i)
    # non-cache files must never be touched
    stray = self.cache_dir / "notes.txt"
    stray.write_bytes(b"x")
    removed = _prune_cabana_cache(keep=5, cache_dir=self.cache_dir)
    self.assertEqual(len(removed), 2)
    self.assertEqual(removed[0].name, "0000000000000000_0_v3.json.gz")
    remaining = sorted(p.name for p in self.cache_dir.glob("*.json.gz"))
    self.assertEqual(len(remaining), 5)
    self.assertEqual(remaining[0], "0000000000000002_0_v3.json.gz")
    self.assertTrue(stray.exists())

  def test_under_limit_noop(self):
    for i in range(3):
      self._create_file(f"{i:016x}_0_v3.json.gz", mtime_offset=1000.0 + i)
    removed = _prune_cabana_cache(keep=5, cache_dir=self.cache_dir)
    self.assertEqual(removed, [])


if __name__ == "__main__":
  unittest.main()
