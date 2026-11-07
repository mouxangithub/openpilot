#!/usr/bin/env python3
"""ACP stdio server — JSON-RPC over stdin/stdout for IDE / external clients.

Protocol: newline-delimited JSON-RPC 2.0 frames. stdout carries ONLY protocol
frames; all logs go to stderr so they never pollute the wire. Reuses
``run_chat_loop`` + ``make_handlers`` from the shared chat runner.

Methods:
  initialize, tools/list, session/create, session/resume, prompt,
  session/cancel, shutdown

Run:  python -m ai.cli.acp_server  (or --smoke for a keyless self-test)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any


def _log(*parts: Any) -> None:
  print(*parts, file=sys.stderr, flush=True)


def _frame(obj: dict[str, Any]) -> str:
  return json.dumps(obj, ensure_ascii=False, default=str) + "\n"


def _error(req_id: Any, code: int, message: str) -> dict[str, Any]:
  return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _result(req_id: Any, result: Any) -> dict[str, Any]:
  return {"jsonrpc": "2.0", "id": req_id, "result": result}


class AcpStdioServer:
  """Line-based JSON-RPC stdio dispatcher that drives one agent session."""

  def __init__(self, params: Any, get_state_reader: Any, get_tool_handlers: Any) -> None:
    self.params = params
    self.get_state_reader = get_state_reader
    self.get_tool_handlers = get_tool_handlers
    self.session_id: str = ""
    self._cancel = asyncio.Event()
    self._running = False

  def _emit(self, event: dict[str, Any]) -> Any:
    async def _wrapped() -> None:
      sys.stdout.write(_frame({"jsonrpc": "2.0", "method": "session/event", "params": event}))
      sys.stdout.flush()
    return _wrapped()

  async def handle(self, msg: dict[str, Any]) -> list[dict[str, Any]]:
    rid = msg.get("id")
    method = str(msg.get("method", ""))
    params = msg.get("params") or {}
    if method == "initialize":
      return [_result(rid, {
        "protocolVersion": 1,
        "capabilities": ["prompt", "tools", "session/resume", "session/cancel"],
        "serverInfo": {"name": "ai-acp", "version": "1.0"},
      })]
    if method == "tools/list":
      from ai.tools.agent_tools import build_tool_schemas
      return [_result(rid, {"tools": build_tool_schemas()})]
    if method == "session/create":
      sid = str(params.get("sessionId") or f"acp-{id(self):x}").strip()
      self.session_id = sid
      return [_result(rid, {"sessionId": sid, "resumed": False})]
    if method == "session/resume":
      sid = str(params.get("sessionId") or "").strip()
      if not sid:
        return [_error(rid, -32602, "sessionId required")]
      self.session_id = sid
      return [_result(rid, {"sessionId": sid, "resumed": True})]
    if method == "session/cancel":
      self._cancel.set()
      return [_result(rid, {"cancelled": True})]
    if method == "prompt":
      if not self.session_id:
        return [_error(rid, -32001, "no session; call session/create first")]
      content = params.get("content", "")
      result = await self._run_prompt(str(content))
      return [_result(rid, result)]
    if method == "shutdown":
      return [_result(rid, {"ok": True})]
    return [_error(rid, -32601, f"method not found: {method}")]

  async def _run_prompt(self, content: str) -> dict[str, Any]:
    if self._running:
      return {"ok": False, "error": "a prompt is already running"}
    self._running = True
    self._cancel.clear()
    body: dict[str, Any] = {
      "sessionId": self.session_id,
      "messages": [{"role": "user", "content": content}],
      "_skip_handoff": True,
    }
    is_cancelled = lambda: self._cancel.is_set()  # noqa: E731
    try:
      from ai.core.chat.runner import run_chat_loop
      result = await run_chat_loop(
        body,
        self.params,
        self._emit,
        get_state_reader=self.get_state_reader,
        get_tool_handlers=self.get_tool_handlers,
        tools=None,
        is_cancelled=is_cancelled,
      )
      return result
    except Exception as e:
      _log("acp: prompt failed:", e)
      return {"ok": False, "error": str(e)}
    finally:
      self._running = False

  async def run(self) -> None:
    """Read newline-JSON frames from stdin until shutdown/EOF."""
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    while True:
      line = await reader.readline()
      if not line:
        break
      text = line.decode("utf-8", errors="replace").strip()
      if not text:
        continue
      try:
        msg = json.loads(text)
      except json.JSONDecodeError as e:
        _log("acp: bad frame:", e)
        sys.stdout.write(_frame(_error(None, -32700, f"parse error: {e}")))
        sys.stdout.flush()
        continue
      if not isinstance(msg, dict):
        continue
      responses = await self.handle(msg)
      for resp in responses:
        sys.stdout.write(_frame(resp))
        sys.stdout.flush()


async def _smoke(params: Any, get_state_reader: Any, get_tool_handlers: Any) -> int:
  """Keyless self-test: initialize + tools/list + session/create + shutdown."""
  srv = AcpStdioServer(params, get_state_reader, get_tool_handlers)
  out: list[dict[str, Any]] = []
  out += await srv.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
  out += await srv.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
  out += await srv.handle({"jsonrpc": "2.0", "id": 3, "method": "session/create", "params": {}})
  out += await srv.handle({"jsonrpc": "2.0", "id": 4, "method": "shutdown", "params": {}})
  ok = all("error" not in r for r in out) and any(r.get("result", {}).get("tools") for r in out)
  return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(prog="acp", description="AI ACP stdio server")
  parser.add_argument("--smoke", action="store_true", help="run keyless self-test and exit")
  parser.add_argument("--pc", action="store_true", help="install openpilot PC mocks (dev boxes without AGNOS)")
  args = parser.parse_args(argv)

  try:
    if args.pc:
      from ai.dev.run_pc import _install_openpilot_mocks
      _install_openpilot_mocks()
    from openpilot.common.params import Params
    params = Params()
    from ai.server.deps import get_state_reader, get_tool_handlers
    from ai.core.tools.sandbox_hooks import shell_runner  # noqa: F401  # warm sandbox early
  except Exception as e:
    _log("acp: init failed:", e)
    return 1

  if args.smoke:
    return asyncio.run(_smoke(params, get_state_reader, get_tool_handlers))

  srv = AcpStdioServer(params, get_state_reader, get_tool_handlers)
  try:
    asyncio.run(srv.run())
  except KeyboardInterrupt:
    pass
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
