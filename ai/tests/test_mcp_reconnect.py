"""Tests for MCP stdio client reconnect supervision (D-P0.2)."""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import ai.tests.bootstrap_pc  # noqa: F401


class TestMCPReconnect(unittest.TestCase):
  def _run(self, coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
      return loop.run_until_complete(coro)
    finally:
      loop.close()

  def test_reconnect_delay_backoff_capped(self):
    from ai.mcp.host import MCPStdioClient
    c = MCPStdioClient("echo", [], {}, reconnect_initial_delay_ms=100, reconnect_max_delay_ms=350)
    self.assertAlmostEqual(c._reconnect_delay(1), 0.1)
    self.assertAlmostEqual(c._reconnect_delay(2), 0.2)
    self.assertAlmostEqual(c._reconnect_delay(3), 0.35)  # capped
    self.assertAlmostEqual(c._reconnect_delay(4), 0.35)

  def test_request_retries_and_succeeds(self):
    from ai.mcp.host import MCPStdioClient
    c = MCPStdioClient("echo", [], {}, reconnect_max_attempts=3)
    calls = {"n": 0}

    async def _flaky(method, params):
      calls["n"] += 1
      if calls["n"] < 3:
        raise RuntimeError("transient")
      return {"ok": True}
    with patch.object(c, "_request_once", new=_flaky), patch.object(c, "close", new=AsyncMock()) as close_mock:
      result = self._run(c.request("tools/list", {}))
    self.assertEqual(result, {"ok": True})
    self.assertEqual(calls["n"], 3)
    close_mock.assert_awaited()

  def test_request_gives_up_after_max(self):
    from ai.mcp.host import MCPStdioClient
    c = MCPStdioClient("echo", [], {}, reconnect_max_attempts=2, reconnect_initial_delay_ms=1)
    async def _always_fail(method, params):
      raise RuntimeError("boom")
    with patch.object(c, "_request_once", new=_always_fail), patch.object(c, "close", new=AsyncMock()):
      with self.assertRaises(RuntimeError) as ctx:
        self._run(c.request("tools/list", {}))
    self.assertIn("after retries", str(ctx.exception))


if __name__ == "__main__":
  unittest.main()