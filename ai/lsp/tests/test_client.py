"""Tests for ai.lsp.client diagnostic/rename methods."""

from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any

from ai.lsp.client import LspClient


class FakeStream:
  """Minimal StreamReader/Writer pair for LspClient tests."""

  def __init__(self) -> None:
    self._incoming = asyncio.Queue[bytes]()
    self._outgoing: list[bytes] = []
    self._closed = False

  async def read(self, n: int = -1) -> bytes:
    chunk = await self._incoming.get()
    if chunk == b"":
      self._closed = True
    return chunk

  def write(self, data: bytes) -> None:
    self._outgoing.append(data)

  async def drain(self) -> None:
    pass

  def close(self) -> None:
    self._closed = True

  async def wait_closed(self) -> None:
    pass

  def feed(self, message: dict[str, Any]) -> None:
    body = json.dumps(message).encode("utf-8")
    self._incoming.put_nowait(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)

  def get_last_request(self) -> dict[str, Any]:
    assert self._outgoing, "no outgoing message"
    raw = self._outgoing[-1]
    # Strip Content-Length header.
    sep = raw.find(b"\r\n\r\n")
    assert sep >= 0
    return json.loads(raw[sep + 4:].decode("utf-8"))


class TestLspClientDiagnosticsRename(unittest.TestCase):
  def _run(self, coro):
    return asyncio.run(coro())

  def _make_client(self):
    reader = FakeStream()
    writer = FakeStream()
    client = LspClient(reader, writer)
    return client, reader, writer

  def test_diagnostic_sends_request(self):
    client, reader, writer = self._make_client()

    async def scenario():
      await client.start()
      task = asyncio.create_task(client.diagnostic("file:///a.py", 5, 10))
      # Wait for request to be sent.
      await asyncio.sleep(0)
      req = writer.get_last_request()
      reader.feed({"jsonrpc": "2.0", "id": req["id"], "result": {"items": [{"message": "unused import", "severity": 2, "range": {"start": {"line": 5, "character": 10}}}]}})
      result = await task
      assert result is not None
      self.assertEqual(result["items"][0]["message"], "unused import")

    self._run(scenario)

  def test_rename_sends_request(self):
    client, reader, writer = self._make_client()

    async def scenario():
      await client.start()
      task = asyncio.create_task(client.rename("file:///a.py", 5, 10, "newName"))
      await asyncio.sleep(0)
      req = writer.get_last_request()
      self.assertEqual(req["method"], "textDocument/rename")
      self.assertEqual(req["params"]["newName"], "newName")
      reader.feed({"jsonrpc": "2.0", "id": req["id"], "result": {"changes": {"file:///a.py": [{"newText": "newName"}]}}})
      result = await task
      assert result is not None
      self.assertEqual(result["changes"]["file:///a.py"][0]["newText"], "newName")

    self._run(scenario)


if __name__ == "__main__":
  unittest.main()
