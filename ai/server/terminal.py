"""Interactive web terminal — PTY bridge (Hermes-inspired, AGNOS/Linux)."""

from __future__ import annotations

import asyncio
import os
import platform
import shutil
import sys
from typing import Any

from aiohttp import web

from openpilot.common.swaglog import cloudlog

from ai.system.paths import openpilot_root


def _terminal_env() -> dict[str, str]:
  env = os.environ.copy()
  root = openpilot_root()
  env["TERM"] = "xterm-256color"
  env["PWD"] = str(root)
  env["OPENPILOT_ROOT"] = str(root)
  env["PYTHONPATH"] = str(root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
  op_dir = str(root)
  ai_scripts = root / "ai" / "scripts"
  path_parts = [op_dir]
  if ai_scripts.is_dir():
    path_parts.append(str(ai_scripts))
  if env.get("PATH"):
    path_parts.append(env["PATH"])
  env["PATH"] = os.pathsep.join(path_parts)
  env["OP_AGENT_URL"] = env.get("OP_AGENT_URL") or env.get("OP_URL") or "http://127.0.0.1:5090"
  return env


_WELCOME = (
  "\x1b[33mOP 终端\x1b[0m — Shell + \x1b[36mop\x1b[0m CLI（与 Hermes 相同心智模型）\r\n"
  "  \x1b[90mop status | op tune | op doctor | op adapt | op chat \"问题\"\x1b[0m\r\n"
  "  \x1b[90m自然语言 / ? / /ai → 等价 op chat；! 前缀强制 Shell\x1b[0m\r\n"
)


_RESIZE_PREFIX = "\x1b[RESIZE:"
_sessions: dict[str, dict[str, Any]] = {}


def _shell_command() -> list[str]:
  if platform.system() == "Windows":
    return ["powershell.exe", "-NoLogo"]
  bash = shutil.which("bash") or "/bin/bash"
  return [bash, "--login"]


async def _pty_available() -> bool:
  return platform.system() != "Windows" and os.name == "posix"


async def terminal_ws(request: web.Request) -> web.WebSocketResponse:
  params = request.app.get("params")
  if not await _pty_available():
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    await ws.send_str(
      "PTY terminal requires Linux/macOS (AGNOS). "
      "On Windows dev, use WSL or the AI shell tools.\r\n"
    )
    await ws.close()
    return ws

  import pty
  import termios
  import fcntl
  import struct

  ws = web.WebSocketResponse(heartbeat=30.0)
  await ws.prepare(request)
  cloudlog.info("aid: terminal ws connected")
  await ws.send_str(_WELCOME)

  master_fd, slave_fd = pty.openpty()
  env = _terminal_env()
  proc = await asyncio.create_subprocess_exec(
    *_shell_command(),
    stdin=slave_fd,
    stdout=slave_fd,
    stderr=slave_fd,
    cwd=str(openpilot_root()),
    env=env,
    preexec_fn=os.setsid,
  )
  os.close(slave_fd)

  loop = asyncio.get_event_loop()

  def _set_winsize(cols: int, rows: int) -> None:
    try:
      winsize = struct.pack("HHHH", rows, cols, 0, 0)
      fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
    except Exception:
      pass

  async def _read_pty() -> None:
    try:
      while True:
        data = await loop.run_in_executor(None, os.read, master_fd, 4096)
        if not data:
          break
        await ws.send_bytes(data)
    except Exception:
      pass

  reader_task = asyncio.create_task(_read_pty())

  try:
    async for msg in ws:
      if msg.type == web.WSMsgType.BINARY:
        os.write(master_fd, msg.data)
      elif msg.type == web.WSMsgType.TEXT:
        text = msg.data or ""
        if text.startswith(_RESIZE_PREFIX) and text.endswith("]"):
          try:
            inner = text[len(_RESIZE_PREFIX):-1]
            cols_s, rows_s = inner.split(";", 1)
            _set_winsize(int(cols_s), int(rows_s))
          except Exception:
            pass
          continue
        os.write(master_fd, text.encode("utf-8", errors="replace"))
      elif msg.type in (web.WSMsgType.CLOSE, web.WSMsgType.CLOSED, web.WSMsgType.ERROR):
        break
  finally:
    reader_task.cancel()
    try:
      os.close(master_fd)
    except Exception:
      pass
    if proc.returncode is None:
      proc.terminate()
      try:
        await asyncio.wait_for(proc.wait(), timeout=2)
      except asyncio.TimeoutError:
        proc.kill()
    cloudlog.info("aid: terminal ws disconnected")
  return ws


def register_terminal_routes(app: web.Application) -> None:
  from ai.server.handlers.terminal_op import api_terminal_op, api_terminal_op_confirm

  app.router.add_get("/api/ai/terminal/ws", terminal_ws)
  app.router.add_post("/api/ai/terminal/op", api_terminal_op)
  app.router.add_post("/api/ai/terminal/op/confirm", api_terminal_op_confirm)
