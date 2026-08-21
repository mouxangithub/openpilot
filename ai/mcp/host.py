"""Lightweight MCP client — stdio JSON-RPC tool bridge."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from openpilot.common.params import Params

from ai.common.storage import read_param, write_param

MCP_SERVERS_KEY = "ai_mcp_servers"


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
  stdout, stderr = await asyncio.wait_for(
    proc.communicate((json.dumps(req) + "\n").encode()),
    timeout=45,
  )
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
) -> dict[str, Any]:
  servers = [s for s in _load_servers(params) if s.get("enabled", True)]
  server = next((s for s in servers if s.get("id") == server_id), None)
  if not server:
    return {"ok": False, "error": f"MCP server '{server_id}' not found"}
  cmd = str(server.get("command") or "")
  if not cmd:
    return {"ok": False, "error": "server command not configured"}
  try:
    result = await _rpc_stdio(
      cmd,
      list(server.get("args") or []),
      {str(k): str(v) for k, v in (server.get("env") or {}).items()},
      "tools/call",
      {"name": tool_name, "arguments": arguments or {}},
    )
    return {"ok": True, "serverId": server_id, "tool": tool_name, "result": result}
  except Exception as e:
    return {"ok": False, "error": str(e), "serverId": server_id, "tool": tool_name}


async def discover_mcp_tools(params: Params, server_id: str) -> dict[str, Any]:
  servers = _load_servers(params)
  server = next((s for s in servers if s.get("id") == server_id), None)
  if not server:
    return {"ok": False, "error": f"MCP server '{server_id}' not found"}
  cmd = str(server.get("command") or "")
  if not cmd:
    return {"ok": False, "error": "server command not configured"}
  try:
    result = await _rpc_stdio(
      cmd,
      list(server.get("args") or []),
      {str(k): str(v) for k, v in (server.get("env") or {}).items()},
      "tools/list",
      {},
    )
    tools = result.get("tools") if isinstance(result, dict) else result
    if isinstance(tools, list):
      server["tools"] = [t.get("name") for t in tools if isinstance(t, dict) and t.get("name")]
      _save_servers(params, servers)
    return {"ok": True, "serverId": server_id, "tools": tools}
  except Exception as e:
    return {"ok": False, "error": str(e)}
