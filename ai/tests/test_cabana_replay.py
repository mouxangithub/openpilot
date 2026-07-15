"""Cabana offline replay WebSocket tests (mocked LogReader)."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))


class _FakeCanFrame:
  def __init__(self, address: int, src: int, dat: bytes):
    self.address = address
    self.src = src
    self.dat = dat


class _FakeCanMsg:
  def __init__(self, mono_ns: int, frames: list[_FakeCanFrame]):
    self._which = "can"
    self.logMonoTime = mono_ns
    self.can = frames

  def which(self) -> str:
    return self._which


class _FakeLogReader:
  """Minimal LogReader stand-in for cabana replay tests."""

  def __init__(self, path: str):
    self.path = path
    self._msgs = []
    seg = Path(path).name
    base = int(seg.replace("rlog", "") or "0") * 10.0
    for i in range(1200):
      mono = int((base + i * 0.05) * 1e9)
      addr = 0x50 if i % 3 else 0x140
      self._msgs.append(_FakeCanMsg(mono, [_FakeCanFrame(addr, 0, bytes([i % 256, 0, 0, 0, 0, 0, 0, 0]))]))

  def __iter__(self):
    return iter(self._msgs)


class CabanaReplayWsTest(AioHTTPTestCase):
  def setUp(self):
    super().setUp()
    self._tmpdir = tempfile.TemporaryDirectory()
    self.route_dir = Path(self._tmpdir.name) / "route--abc--2"
    self.route_dir.mkdir(parents=True)
    for seg in ("0", "1"):
      seg_dir = self.route_dir / seg
      seg_dir.mkdir(parents=True, exist_ok=True)
      (seg_dir / "rlog").write_bytes(b"fake")

  def tearDown(self):
    self._tmpdir.cleanup()
    super().tearDown()

  async def get_application(self):
    import ai.cabana as cabana

    app = web.Application()
    cabana.register_routes(app, Path(__file__).parent)
    return app

  @unittest_run_loop
  async def test_offline_ws_streams_metadata_and_can(self):
    import ai.cabana as cabana

    route_name = self.route_dir.name

    def fake_routes_dir():
      return self.route_dir.parent

    with patch.object(cabana, "LogReader", _FakeLogReader), patch.object(cabana, "_get_routes_dir", fake_routes_dir):
      client = await self.client.ws_connect(f"/api/cabana/offline/ws?route={route_name}&speed=10")
      seen: dict[str, list] = {"loading": [], "can": 0, "metadata": None, "done": False}

      async def recv_until(predicate, timeout=8.0):
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
          msg = await asyncio.wait_for(client.receive(), timeout=timeout)
          if msg.type.name != "TEXT":
            continue
          data = json.loads(msg.data)
          t = data.get("type")
          if t == "loading":
            seen["loading"].append(data.get("phase"))
          elif t == "metadata":
            seen["metadata"] = data
          elif t == "can":
            seen["can"] += len(data.get("frames", []))
          elif t == "done":
            seen["done"] = True
          if predicate(data):
            return data
        raise AssertionError(f"timeout waiting; seen={seen}")

      await client.send_str(json.dumps({"action": "play"}))
      meta = await recv_until(lambda d: d.get("type") == "metadata")
      self.assertGreater(meta.get("duration", 0), 0)
      self.assertIn(meta.get("source"), ("rlog", "qlog"))

      await recv_until(lambda d: d.get("type") == "can" and len(d.get("frames", [])) > 0, timeout=12.0)
      self.assertGreater(seen["can"], 0)

      await client.close()


if __name__ == "__main__":
  unittest.main()
