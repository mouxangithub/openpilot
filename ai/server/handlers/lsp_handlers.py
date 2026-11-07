"""API handlers — LSP integration."""

from __future__ import annotations

from typing import Any

from ai.server.handlers._api_common import *  # noqa: F403
from ai.lsp.search import search_symbols


async def api_lsp_servers(request: web.Request) -> web.Response:
  """GET: list active servers. POST: start a server."""
  manager: Any = request.app["lsp_manager"]

  if request.method == "GET":
    return _json_response({"ok": True, "servers": manager.list_servers()})

  try:
    body = await request.json()
  except json.JSONDecodeError:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)

  workspace_root = str(body.get("workspaceRoot") or body.get("workspace") or "").strip()
  if not workspace_root:
    return _json_response({"ok": False, "error": "workspaceRoot is required"}, status=400)
  language = str(body.get("language") or "").strip()
  command = str(body.get("command") or "").strip()
  args = body.get("args") or []

  try:
    if command:
      client = await manager.start_server(workspace_root, command, args=args)
    else:
      if not language:
        return _json_response({"ok": False, "error": "language or command is required"}, status=400)
      client = await manager.start_server_for_language(workspace_root, language)
  except Exception as e:
    cloudlog.error(f"aid: lsp start failed: {e}")
    return _json_response({"ok": False, "error": str(e)}, status=500)

  return _json_response({
    "ok": True,
    "workspace": workspace_root,
    "initialized": True,
  })


async def api_lsp_servers_stop(request: web.Request) -> web.Response:
  """Stop a managed LSP server."""
  workspace = request.query.get("workspace", "")
  if not workspace:
    return _json_response({"ok": False, "error": "workspace is required"}, status=400)
  manager: Any = request.app["lsp_manager"]
  try:
    await manager.stop_server(workspace)
  except Exception as e:
    return _json_response({"ok": False, "error": str(e)}, status=500)
  return _json_response({"ok": True, "workspace": workspace})


async def api_lsp_search(request: web.Request) -> web.Response:
  """Search symbols via workspace/symbol and the local index."""
  query = request.query.get("q", "")
  workspace = request.query.get("workspace", "")
  if not query or not workspace:
    return _json_response({"ok": False, "error": "q and workspace are required"}, status=400)

  manager: Any = request.app["lsp_manager"]
  index: Any = request.app["lsp_index"]
  client = manager.get_client(workspace)
  if client is None:
    return _json_response({"ok": False, "error": "no LSP server for workspace"}, status=400)

  try:
    raw = await client.workspace_symbol(query)
    index.add_workspace_symbols(raw)
    results = search_symbols(index, query, limit=50)
  except Exception as e:
    cloudlog.error(f"aid: lsp search failed: {e}")
    return _json_response({"ok": False, "error": str(e)}, status=500)

  return _json_response({
    "ok": True,
    "query": query,
    "symbols": [s.to_dict() for s in results],
  })


async def api_lsp_index(request: web.Request) -> web.Response:
  """Index textDocument/documentSymbol results for a URI."""
  try:
    body = await request.json()
  except json.JSONDecodeError:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)

  uri = str(body.get("uri") or "").strip()
  workspace = str(body.get("workspace") or body.get("workspaceRoot") or "").strip()
  if not uri or not workspace:
    return _json_response({"ok": False, "error": "uri and workspace are required"}, status=400)

  manager: Any = request.app["lsp_manager"]
  index: Any = request.app["lsp_index"]
  client = manager.get_client(workspace)
  if client is None:
    return _json_response({"ok": False, "error": "no LSP server for workspace"}, status=400)

  try:
    raw = await client.document_symbol(uri)
    count = index.add_document_symbols(uri, raw)
  except Exception as e:
    cloudlog.error(f"aid: lsp index failed: {e}")
    return _json_response({"ok": False, "error": str(e)}, status=500)

  return _json_response({"ok": True, "indexed": count})
