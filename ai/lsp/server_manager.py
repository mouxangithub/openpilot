"""Start, pool, and stop language-server subprocesses.

A thin manager around `LspClient` that knows how to spawn stdio servers and
clean them up on shutdown.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from ai.lsp.client import LspClient, LspError


class LspServerManager:
  """Owns one `LspClient` per workspace root."""

  def __init__(
    self,
    configs: dict[str, dict[str, Any]] | None = None,
  ):
    """`configs` maps a language id to a dict with `command` and optional `args`."""
    self.configs = configs or {}
    self._clients: dict[str, LspClient] = {}
    self._processes: dict[str, asyncio.subprocess.Process] = {}

  def list_servers(self) -> list[dict[str, Any]]:
    return [
      {"workspace": ws, "pid": proc.pid, "running": proc.returncode is None}
      for ws, proc in self._processes.items()
    ]

  async def start_server(
    self,
    workspace_root: str,
    command: str,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    startup_timeout: float = 30.0,
  ) -> LspClient:
    """Spawn a server for `workspace_root` and return its client."""
    if workspace_root in self._clients:
      return self._clients[workspace_root]

    args = list(args or [])
    merged_env = {**os.environ, **(env or {})}
    try:
      proc = await asyncio.create_subprocess_exec(
        command,
        *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=workspace_root,
        env=merged_env,
      )
    except Exception as e:
      raise LspError(f"failed to spawn LSP server {command}: {e}") from e

    client = LspClient(proc.stdout, proc.stdin)
    await client.start()
    root_uri = Path(workspace_root).resolve().as_uri()
    try:
      await asyncio.wait_for(
        client.initialize(root_uri),
        timeout=startup_timeout,
      )
    except Exception as e:
      await client.close()
      proc.terminate()
      try:
        await asyncio.wait_for(proc.wait(), timeout=5)
      except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
      raise LspError(f"LSP initialize failed for {workspace_root}: {e}") from e

    self._processes[workspace_root] = proc
    self._clients[workspace_root] = client
    return client

  async def start_server_for_language(
    self,
    workspace_root: str,
    language: str,
  ) -> LspClient:
    """Start a server using the configured command for `language`."""
    cfg = self.configs.get(language)
    if not cfg:
      raise LspError(f"no LSP server configured for language: {language}")
    command = cfg["command"]
    args = cfg.get("args", [])
    env = cfg.get("env")
    return await self.start_server(workspace_root, command, args=args, env=env)

  def get_client(self, workspace_root: str) -> LspClient | None:
    return self._clients.get(workspace_root)

  async def stop_server(self, workspace_root: str) -> None:
    """Gracefully shut down one server."""
    client = self._clients.pop(workspace_root, None)
    proc = self._processes.pop(workspace_root, None)
    if client is not None:
      try:
        await client.shutdown_and_exit()
      except Exception:
        await client.close()
    if proc is not None:
      if proc.returncode is None:
        proc.terminate()
        try:
          await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
          proc.kill()
          await proc.wait()

  async def stop_all(self) -> None:
    """Stop every managed server."""
    for workspace in list(self._clients):
      await self.stop_server(workspace)
