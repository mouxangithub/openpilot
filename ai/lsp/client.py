"""Async LSP JSON-RPC client over stdio.

Supports the small subset used by op助手: initialize, textDocument/documentSymbol,
workspace/symbol, and textDocument/definition. The client owns message framing,
request/response correlation, and graceful shutdown.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

_HEADER_SEPARATOR = b"\r\n\r\n"
_MAX_HEADER_BYTES = 1 << 16


class LspError(Exception):
  """Structured LSP failure surfaced by the client."""

  def __init__(self, message: str, code: int | str | None = None):
    super().__init__(message)
    self.code = code


class _MessageDecoder:
  """Content-Length framed JSON-RPC decoder."""

  def __init__(self, max_message_bytes: int):
    self._buffer = bytearray()
    self._max_message_bytes = max_message_bytes

  def push(self, chunk: bytes) -> list[dict[str, Any]]:
    self._buffer.extend(chunk)
    messages: list[dict[str, Any]] = []
    while True:
      step = self._next()
      if step is None:
        break
      messages.append(step)
    return messages

  def _next(self) -> dict[str, Any] | None:
    sep = self._buffer.find(_HEADER_SEPARATOR)
    if sep < 0:
      if len(self._buffer) > _MAX_HEADER_BYTES:
        raise LspError("LSP header exceeded maximum size")
      return None
    if sep > _MAX_HEADER_BYTES:
      raise LspError("LSP header exceeded maximum size")
    header = bytes(self._buffer[:sep]).decode("ascii", errors="replace")
    content_length = self._parse_content_length(header)
    if content_length > self._max_message_bytes:
      raise LspError(f"LSP message length {content_length} exceeds limit")
    body_start = sep + len(_HEADER_SEPARATOR)
    body_end = body_start + content_length
    if len(self._buffer) < body_end:
      return None
    body = bytes(self._buffer[body_start:body_end]).decode("utf-8", errors="replace")
    self._buffer = self._buffer[body_end:]
    try:
      return json.loads(body)
    except json.JSONDecodeError as e:
      raise LspError(f"LSP body was not valid JSON: {e}") from e

  @staticmethod
  def _parse_content_length(header: str) -> int:
    for line in header.split("\r\n"):
      colon = line.find(":")
      if colon < 0:
        continue
      name = line[:colon].strip().lower()
      if name != "content-length":
        continue
      try:
        value = int(line[colon + 1:].strip())
      except ValueError as e:
        raise LspError(f"invalid Content-Length header: {line}") from e
      if value < 0:
        raise LspError(f"invalid Content-Length header: {line}")
      return value
    raise LspError("LSP header missing Content-Length")


class LspClient:
  """JSON-RPC client bound to a StreamReader/StreamWriter pair."""

  def __init__(
    self,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    max_message_bytes: int = 16_000_000,
  ):
    self.reader = reader
    self.writer = writer
    self.max_message_bytes = max_message_bytes
    self._decoder = _MessageDecoder(max_message_bytes)
    self._next_id = 1
    self._pending: dict[int | str, asyncio.Future[dict[str, Any]]] = {}
    self._read_task: asyncio.Task[None] | None = None
    self._closed = False

  async def start(self) -> None:
    """Begin consuming server messages."""
    if self._read_task is not None:
      return
    self._read_task = asyncio.create_task(self._read_loop())

  async def _read_loop(self) -> None:
    try:
      while not self._closed:
        chunk = await self.reader.read(65536)
        if not chunk:
          break
        messages = self._decoder.push(chunk)
        for message in messages:
          self._dispatch(message)
    except Exception as e:
      self._fail_all(e)
    finally:
      self._closed = True
      self._fail_all(LspError("LSP connection closed"))

  def _dispatch(self, message: dict[str, Any]) -> None:
    method = message.get("method")
    msg_id = message.get("id")
    if isinstance(method, str) and msg_id is not None:
      # Server->client request; answer best-effort.
      asyncio.create_task(self._answer_server_request(msg_id, method, message.get("params")))
      return
    if msg_id is not None:
      self._handle_response(msg_id, message)

  async def _answer_server_request(self, msg_id: Any, method: str, params: Any) -> None:
    if method == "workspace/configuration":
      items = (params or {}).get("items") or []
      await self._send({"jsonrpc": "2.0", "id": msg_id, "result": [None] * len(items)})
    else:
      await self._send({
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"unsupported server request: {method}"},
      })

  def _handle_response(self, msg_id: Any, message: dict[str, Any]) -> None:
    future = self._pending.pop(msg_id, None)
    if future is None or future.done():
      return
    if "error" in message:
      error = message["error"]
      future.set_exception(LspError(str(error.get("message", "LSP error")), error.get("code")))
    else:
      future.set_result(message.get("result"))

  async def _send(self, message: dict[str, Any]) -> None:
    body = json.dumps(message, ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    self.writer.write(header + body)
    await self.writer.drain()

  async def request(self, method: str, params: Any) -> Any:
    """Send a request and await its result."""
    if self._closed:
      raise LspError("LSP client is closed")
    msg_id = self._next_id
    self._next_id += 1
    loop = asyncio.get_event_loop()
    future: asyncio.Future[dict[str, Any]] = loop.create_future()
    self._pending[msg_id] = future
    try:
      await self._send({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
    except Exception as e:
      self._pending.pop(msg_id, None)
      raise LspError(f"failed to send LSP request {method}: {e}") from e
    return await future

  async def notify(self, method: str, params: Any) -> None:
    """Send a notification."""
    if self._closed:
      raise LspError("LSP client is closed")
    await self._send({"jsonrpc": "2.0", "method": method, "params": params})

  async def initialize(
    self,
    root_uri: str,
    workspace_folders: list[dict[str, str]] | None = None,
    capabilities: dict[str, Any] | None = None,
    initialization_options: Any = None,
  ) -> dict[str, Any]:
    """Perform the LSP initialize handshake."""
    if workspace_folders is None:
      workspace_folders = [{"uri": root_uri, "name": "workspace"}]
    if capabilities is None:
      capabilities = {
        "general": {"positionEncodings": ["utf-16"]},
        "workspace": {"workspaceFolders": True, "configuration": True},
        "textDocument": {
          "synchronization": {"dynamicRegistration": False},
          "definition": {"linkSupport": True},
          "documentSymbol": {},
          "hover": {"contentFormat": ["markdown", "plaintext"]},
        },
      }
    result = await self.request("initialize", {
      "processId": None,
      "rootUri": root_uri,
      "workspaceFolders": workspace_folders,
      "capabilities": capabilities,
      "initializationOptions": initialization_options,
    })
    await self.notify("initialized", {})
    return result

  async def document_symbol(self, uri: str) -> list[dict[str, Any]]:
    """Request textDocument/documentSymbol for `uri`."""
    result = await self.request("textDocument/documentSymbol", {"textDocument": {"uri": uri}})
    if result is None:
      return []
    return result if isinstance(result, list) else [result]

  async def workspace_symbol(self, query: str = "") -> list[dict[str, Any]]:
    """Request workspace/symbol."""
    result = await self.request("workspace/symbol", {"query": query})
    if result is None:
      return []
    return result if isinstance(result, list) else []

  async def definition(self, uri: str, line: int, character: int) -> list[dict[str, Any]]:
    """Request textDocument/definition."""
    result = await self.request("textDocument/definition", {
      "textDocument": {"uri": uri},
      "position": {"line": line, "character": character},
    })
    if result is None:
      return []
    return result if isinstance(result, list) else [result]

  async def references(self, uri: str, line: int, character: int) -> list[dict[str, Any]]:
    """Request textDocument/references."""
    result = await self.request("textDocument/references", {
      "textDocument": {"uri": uri},
      "position": {"line": line, "character": character},
      "context": {"includeDeclaration": True},
    })
    if result is None:
      return []
    return result if isinstance(result, list) else [result]

  async def implementation(self, uri: str, line: int, character: int) -> list[dict[str, Any]]:
    """Request textDocument/implementation."""
    result = await self.request("textDocument/implementation", {
      "textDocument": {"uri": uri},
      "position": {"line": line, "character": character},
    })
    if result is None:
      return []
    return result if isinstance(result, list) else [result]

  async def hover(self, uri: str, line: int, character: int) -> dict[str, Any] | None:
    """Request textDocument/hover."""
    result = await self.request("textDocument/hover", {
      "textDocument": {"uri": uri},
      "position": {"line": line, "character": character},
    })
    if result is None:
      return None
    return result if isinstance(result, dict) else None

  async def diagnostic(self, uri: str, line: int | None = None, character: int | None = None) -> dict[str, Any] | None:
    """Request textDocument/diagnostic (LSP 3.17 pull diagnostics).

    Falls back to textDocument/documentSymbol if the server does not support
    pull diagnostics.
    """
    try:
      params: dict[str, Any] = {"textDocument": {"uri": uri}}
      if line is not None and character is not None:
        params["previousResultId"] = f"{uri}:{line}:{character}"
      result = await self.request("textDocument/diagnostic", params)
      if result is None:
        return None
      return result if isinstance(result, dict) else None
    except LspError as exc:
      # -32601 = MethodNotFound; fall back to documentSymbol as a best-effort.
      if exc.code == -32601:
        symbols = await self.document_symbol(uri)
        return {"kind": "documentSymbol", "items": symbols}
      raise

  async def rename(self, uri: str, line: int, character: int, new_name: str) -> dict[str, Any] | None:
    """Request textDocument/rename and return a WorkspaceEdit."""
    result = await self.request("textDocument/rename", {
      "textDocument": {"uri": uri},
      "position": {"line": line, "character": character},
      "newName": new_name,
    })
    if result is None:
      return None
    return result if isinstance(result, dict) else None

  async def shutdown_and_exit(self) -> None:
    """Send shutdown/exit and close the transport."""
    try:
      await self.request("shutdown", None)
    except LspError:
      pass
    try:
      await self.notify("exit", None)
    except LspError:
      pass
    await self.close()

  async def close(self) -> None:
    """Close the transport and stop the read loop."""
    if self._closed:
      return
    self._closed = True
    try:
      self.writer.close()
      await self.writer.wait_closed()
    except Exception:
      pass
    if self._read_task is not None:
      self._read_task.cancel()
      try:
        await self._read_task
      except asyncio.CancelledError:
        pass
      except Exception:
        pass
    self._fail_all(LspError("LSP client closed"))

  def _fail_all(self, error: Exception) -> None:
    pending = list(self._pending.items())
    self._pending.clear()
    for _, future in pending:
      if not future.done():
        future.set_exception(error)
