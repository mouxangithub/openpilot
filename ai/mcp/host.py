"""Lightweight MCP client — stdio JSON-RPC tool bridge."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from openpilot.common.params import Params

from ai.common.storage import read_param, write_param

MCP_SERVERS_KEY = "ai_mcp_servers"
_session_locks: dict[tuple[str, str], asyncio.Lock] = {}
_session_configs: dict[tuple[str, str], tuple[str, tuple[str, ...], tuple[tuple[str, str], ...]]] = {}
_clients: dict[tuple[str, str], "MCPStdioClient"] = {}


class MCPStdioClient:
  def __init__(
    self,
    command: str,
    args: list[str],
    env: dict[str, str],
    *,
    reconnect_max_attempts: int = 3,
    reconnect_initial_delay_ms: float = 250,
    reconnect_max_delay_ms: float = 2000,
  ) -> None:
    self.command, self.args, self.env = command, args, env
    self.proc: Any = None
    self.lock = asyncio.Lock()
    self.request_id = 0
    self.initialized = False
    # D-P0.2: supervised reconnect policy.
    self.reconnect_max_attempts = max(1, int(reconnect_max_attempts))
    self.reconnect_initial_delay_ms = float(reconnect_initial_delay_ms)
    self.reconnect_max_delay_ms = float(reconnect_max_delay_ms)

  def _reconnect_delay(self, attempt: int) -> float:
    """Exponential backoff with cap (ms)."""
    import math
    base = self.reconnect_initial_delay_ms * (2 ** (attempt - 1))
    return min(base, self.reconnect_max_delay_ms) / 1000.0

  async def start(self) -> None:
    if self.proc is None or self.proc.returncode is not None:
      self.proc = await asyncio.create_subprocess_exec(self.command, *self.args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env={**__import__("os").environ, **self.env})
      self.request_id += 1
      req = {"jsonrpc": "2.0", "id": self.request_id, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "ai-harness", "version": "1.0"}}}
      self.proc.stdin.write((json.dumps(req) + "\n").encode())
      await self.proc.stdin.drain()
      line = await asyncio.wait_for(self.proc.stdout.readline(), timeout=45)
      data = json.loads(line.decode(errors="replace"))
      if data.get("id") != self.request_id or data.get("error") or not isinstance(data.get("result"), dict):
        raise RuntimeError("MCP initialize failed")
      self.proc.stdin.write((json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}) + "\n").encode())
      await self.proc.stdin.drain()
      self.initialized = True

  async def request(self, method: str, params: dict[str, Any]) -> Any:
    """Issue an MCP request with supervised reconnect + backoff (D-P0.2)."""
    last_err: Exception | None = None
    for attempt in range(1, self.reconnect_max_attempts + 1):
      try:
        return await self._request_once(method, params)
      except Exception as exc:  # noqa: BLE001
        last_err = exc
        if attempt >= self.reconnect_max_attempts:
          break
        await self.close()
        await asyncio.sleep(self._reconnect_delay(attempt))
    # Preserve the underlying failure as the cause so callers can still see
    # (e.g.) the original TimeoutError while the reconnect contract stays stable.
    raise RuntimeError(f"MCP request '{method}' failed after retries: {last_err}") from last_err

  async def _request_once(self, method: str, params: dict[str, Any]) -> Any:
    async with self.lock:
      try:
        await self.start()
      except Exception:
        await self.close()
        raise
      self.request_id += 1
      req = {"jsonrpc": "2.0", "id": self.request_id, "method": method, "params": params}
      try:
        self.proc.stdin.write((json.dumps(req) + "\n").encode())
        await self.proc.stdin.drain()
        line = await asyncio.wait_for(self.proc.stdout.readline(), timeout=45)
        if not line:
          raise RuntimeError("MCP connection closed")
        data = json.loads(line.decode(errors="replace"))
        if data.get("error"):
          raise RuntimeError(str(data["error"]))
        return data.get("result")
      except Exception:
        await self.close()
        raise

  async def close(self) -> None:
    proc, self.proc = self.proc, None
    if proc is not None and proc.returncode is None:
      proc.kill()
      await proc.wait()


def _schedule_client_close(client: MCPStdioClient) -> None:
  try:
    loop = asyncio.get_running_loop()
  except RuntimeError:
    client.proc = None
    return
  loop.create_task(client.close())


def _client_for(server_id: str, session_id: str, command: str, args: list[str], env: dict[str, str]) -> MCPStdioClient:
  key = (server_id, session_id)
  config = (command, tuple(args), tuple(sorted(env.items())))
  if _session_configs.get(key) != config:
    old = _clients.pop(key, None)
    if old is not None:
      _schedule_client_close(old)
    _session_configs[key] = config
  client = _clients.get(key)
  if client is None:
    client = MCPStdioClient(command, args, env)
    _clients[key] = client
  return client


def _session_lock(server_id: str, session_id: str, config: tuple[str, tuple[str, ...], tuple[tuple[str, str], ...]]) -> asyncio.Lock:
  key = (server_id, session_id)
  if _session_configs.get(key) != config:
    _session_locks.pop(key, None)
    _session_configs[key] = config
  return _session_locks.setdefault(key, asyncio.Lock())


async def close_mcp_sessions_for_session(session_id: str) -> None:
  for key in [k for k in list(_clients) if k[1] == session_id]:
    client = _clients.pop(key, None)
    if client is not None:
      await client.close()
    _session_locks.pop(key, None)
    _session_configs.pop(key, None)


def close_mcp_session(server_id: str, session_id: str) -> None:
  key = (server_id, session_id)
  client = _clients.pop(key, None)
  if client is not None:
    _schedule_client_close(client)
  _session_locks.pop(key, None)
  _session_configs.pop(key, None)


def _load_servers(params: Params) -> list[dict[str, Any]]:
  try:
    raw = read_param(params, MCP_SERVERS_KEY)
    if not raw:
      return []
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="replace")
    data = json.loads(raw)
    return data if isinstance(data, list) else []
  except Exception:
    return []


def _save_servers(params: Params, servers: list[dict[str, Any]]) -> None:
  write_param(params, MCP_SERVERS_KEY, json.dumps(servers[:16], ensure_ascii=False))


def list_mcp_servers(params: Params | None = None) -> dict[str, Any]:
  params = params or Params()
  servers = []
  for s in _load_servers(params):
    servers.append({
      "id": s.get("id"),
      "name": s.get("name"),
      "command": s.get("command"),
      "enabled": s.get("enabled", True),
      "toolCount": len(s.get("tools") or []),
    })
  return {"ok": True, "servers": servers}


def upsert_mcp_server(params: Params, spec: dict[str, Any]) -> dict[str, Any]:
  servers = _load_servers(params)
  sid = str(spec.get("id") or spec.get("name") or "").strip()
  if not sid:
    return {"ok": False, "error": "id required"}
  entry = {
    "id": sid,
    "name": str(spec.get("name") or sid),
    "command": str(spec.get("command") or ""),
    "args": list(spec.get("args") or []),
    "env": dict(spec.get("env") or {}),
    "enabled": spec.get("enabled", True),
    "tools": list(spec.get("tools") or []),
  }
  replaced = False
  for i, s in enumerate(servers):
    if s.get("id") == sid:
      servers[i] = {**s, **entry}
      replaced = True
      break
  if not replaced:
    servers.append(entry)
  _save_servers(params, servers)
  return {"ok": True, "server": entry, "replaced": replaced}


async def _rpc_stdio(command: str, args: list[str], env: dict[str, str], method: str, params: dict[str, Any]) -> Any:
  proc = await asyncio.create_subprocess_exec(
    command,
    *args,
    stdin=asyncio.subprocess.PIPE,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    env={**dict(__import__("os").environ), **env},
  )
  req = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
  try:
    stdout, stderr = await asyncio.wait_for(
      proc.communicate((json.dumps(req) + "\n").encode()),
      timeout=45,
    )
  except asyncio.TimeoutError as exc:
    if proc.returncode is None:
      proc.kill()
      await proc.wait()
    raise RuntimeError("MCP request timed out after 45s") from exc
  finally:
    if proc.returncode is None:
      proc.kill()
      await proc.wait()
  if proc.returncode not in (0, None):
    err = (stderr or b"").decode(errors="replace")[:500]
    raise RuntimeError(err or f"MCP process exit {proc.returncode}")
  line = stdout.decode(errors="replace").strip().splitlines()
  if not line:
    raise RuntimeError("empty MCP response")
  data = json.loads(line[-1])
  if data.get("error"):
    raise RuntimeError(str(data["error"]))
  return data.get("result")


async def call_mcp_tool(
  params: Params,
  *,
  server_id: str,
  tool_name: str,
  arguments: dict[str, Any] | None = None,
  session_id: str = "",
  sessionId: str | None = None,
) -> dict[str, Any]:
  servers = [s for s in _load_servers(params) if s.get("enabled", True)]
  server = next((s for s in servers if s.get("id") == server_id), None)
  if not server:
    return {"ok": False, "error": f"MCP server '{server_id}' not found"}
  cmd = str(server.get("command") or "")
  if not cmd:
    return {"ok": False, "error": "server command not configured"}
  if not tool_name or "__" in tool_name or any(ch.isspace() for ch in tool_name):
    return {"ok": False, "error": "invalid MCP tool name", "serverId": server_id}
  session_id = str(sessionId or session_id or "")
  config = (cmd, tuple(map(str, server.get("args") or [])), tuple(sorted((str(k), str(v)) for k, v in (server.get("env") or {}).items())))
  try:
    client = _client_for(server_id, session_id, list(map(str, [cmd]))[0], list(map(str, server.get("args") or [])), {str(k): str(v) for k, v in (server.get("env") or {}).items()})
    async with _session_lock(server_id, session_id, config):
      result = await client.request("tools/call", {"name": tool_name, "arguments": arguments or {}})
    return {"ok": True, "serverId": server_id, "tool": tool_name, "result": result}
  except Exception as e:
    return {"ok": False, "error": str(e), "serverId": server_id, "tool": tool_name}


async def discover_mcp_tools(params: Params, server_id: str, session_id: str = "", sessionId: str | None = None) -> dict[str, Any]:
  return await _mcp_discovery_request(params, server_id, "tools/list", "tools", session_id=session_id, sessionId=sessionId)


async def discover_mcp_resources(params: Params, server_id: str, session_id: str = "", sessionId: str | None = None, cursor: str = "") -> dict[str, Any]:
  return await _mcp_discovery_request(params, server_id, "resources/list", "resources", session_id=session_id, sessionId=sessionId, cursor=cursor)


async def discover_mcp_resource_templates(params: Params, server_id: str, session_id: str = "", sessionId: str | None = None) -> dict[str, Any]:
  """List MCP resource templates (D-P1.2): ``resources/templates/list``."""
  return await _mcp_discovery_request(params, server_id, "resources/templates/list", "resourceTemplates", session_id=session_id, sessionId=sessionId)


async def discover_mcp_prompts(params: Params, server_id: str, session_id: str = "", sessionId: str | None = None) -> dict[str, Any]:
  return await _mcp_discovery_request(params, server_id, "prompts/list", "prompts", session_id=session_id, sessionId=sessionId)


def get_mcp_tool_meta(params: Params, server_id: str, tool_name: str) -> dict[str, Any] | None:
  """Return cached metadata for an MCP tool discovered via ``tools/list``."""
  servers = _load_servers(params)
  server = next((s for s in servers if s.get("id") == server_id), None)
  if not server:
    return None
  meta = (server.get("tool_meta") or {}).get(tool_name)
  if not isinstance(meta, dict):
    return None
  schema = meta.get("inputSchema") or meta.get("input_schema") or {}
  return {
    "name": tool_name,
    "label": str(meta.get("title") or meta.get("description") or tool_name)[:60],
    "description": str(meta.get("description") or ""),
    "input_schema": schema,
  }


def _get_client(params: Params, server_id: str, session_id: str) -> MCPStdioClient | None:
  """Resolve or create a cached MCP stdio client for a server/session pair."""
  servers = _load_servers(params)
  server = next((s for s in servers if s.get("id") == server_id), None)
  if not server:
    return None
  cmd = str(server.get("command") or "")
  if not cmd:
    return None
  args = list(map(str, server.get("args") or []))
  env = {str(k): str(v) for k, v in (server.get("env") or {}).items()}
  return _client_for(server_id, session_id, cmd, args, env)


async def read_mcp_resource(
  params: Params,
  server_id: str,
  uri: str,
  session_id: str = "",
  sessionId: str | None = None,
) -> dict[str, Any]:
  """Read an MCP resource by URI."""
  sid = str(sessionId or session_id or "")
  try:
    client = _get_client(params, server_id, sid)
    if client is None:
      return {"ok": False, "error": f"MCP server '{server_id}' not found", "server_id": server_id, "uri": uri}
    async with client.lock:
      result = await client.request("resources/read", {"uri": uri})
    return {"ok": True, "server_id": server_id, "uri": uri, "contents": result}
  except Exception as e:
    return {"ok": False, "error": str(e), "server_id": server_id, "uri": uri}


async def get_mcp_prompt(
  params: Params,
  server_id: str,
  name: str,
  arguments: dict[str, Any] | None = None,
  session_id: str = "",
  sessionId: str | None = None,
) -> dict[str, Any]:
  """Get an MCP prompt by name with optional arguments."""
  sid = str(sessionId or session_id or "")
  try:
    client = _get_client(params, server_id, sid)
    if client is None:
      return {"ok": False, "error": f"MCP server '{server_id}' not found", "server_id": server_id, "name": name}
    async with client.lock:
      result = await client.request("prompts/get", {"name": name, "arguments": arguments or {}})
    return {"ok": True, "server_id": server_id, "name": name, "messages": result}
  except Exception as e:
    return {"ok": False, "error": str(e), "server_id": server_id, "name": name}


async def _mcp_discovery_request(
  params: Params,
  server_id: str,
  method: str,
  result_key: str,
  session_id: str = "",
  sessionId: str | None = None,
  cursor: str = "",
) -> dict[str, Any]:
  servers = _load_servers(params)
  server = next((s for s in servers if s.get("id") == server_id), None)
  if not server:
    return {"ok": False, "error": f"MCP server '{server_id}' not found"}
  cmd = str(server.get("command") or "")
  if not cmd:
    return {"ok": False, "error": "server command not configured"}
  try:
    sid = str(sessionId or session_id or "")
    env = {str(k): str(v) for k, v in (server.get("env") or {}).items()}
    args = list(map(str, server.get("args") or []))
    config = (cmd, tuple(args), tuple(sorted(env.items())))
    # D-P1.2: cursor pagination passthrough.
    req_params: dict[str, Any] = {}
    if cursor:
      req_params["cursor"] = cursor
    if sid:
      client = _client_for(server_id, sid, cmd, args, env)
      async with _session_lock(server_id, sid, config):
        result = await client.request(method, req_params)
    else:
      result = await _rpc_stdio(cmd, args, env, method, req_params)
    items = result.get(result_key) if isinstance(result, dict) else result
    next_cursor = result.get("nextCursor") if isinstance(result, dict) else None
    if method == "tools/list" and isinstance(items, list):
      server["tools"] = [t.get("name") for t in items if isinstance(t, dict) and t.get("name")]
      server["tool_meta"] = {str(t.get("name")): t for t in items if isinstance(t, dict) and t.get("name")}
      _save_servers(params, servers)
    return {"ok": True, "serverId": server_id, "type": result_key, "items": items, "nextCursor": next_cursor}
  except Exception as e:
    return {"ok": False, "error": str(e), "serverId": server_id}
