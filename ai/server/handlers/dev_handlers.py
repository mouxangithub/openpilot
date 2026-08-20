"""API handlers — dev."""

from ai.server.handlers._api_common import *  # noqa: F403

async def api_dev_assets(request: web.Request) -> web.Response:
  from ai.tools.dev_assets import list_dev_assets, resolve_dev_asset
  if request.method == "GET" and request.match_info.get("kind"):
    kind = request.match_info.get("kind", "")
    name = request.match_info.get("name", "")
    path = resolve_dev_asset(kind, name)
    if path is None:
      return web.Response(status=404, text="Not found")
    if name.lower().endswith(".opbak"):
      content_type = "application/gzip"
    else:
      import mimetypes
      content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    return web.FileResponse(
      path,
      headers={
        "Content-Disposition": f'attachment; filename="{name}"',
        "Content-Type": content_type,
      },
    )
  limit = int(request.query.get("limit", "40"))
  return _json_response(list_dev_assets(limit=limit))

async def api_dev_cache(request: web.Request) -> web.Response:
  from ai.tools.dev_cache_tools import clear_dev_cache, get_cache_status

  if request.method == "GET":
    days_raw = request.query.get("days")
    mode_raw = request.query.get("mode")
    if days_raw is not None and mode_raw is not None:
      return _json_response(get_cache_status(
        days=int(days_raw),
        mode=str(mode_raw),
      ))
    return _json_response(get_cache_status())
  try:
    body = await request.json()
  except json.JSONDecodeError:
    body = {}
  groups = body.get("groups")
  if groups is not None and not isinstance(groups, list):
    groups = None
  result = clear_dev_cache(
    days=int(body.get("days", 3)),
    mode=str(body.get("mode", "within")),
    groups=groups,
  )
  status = 409 if not result.get("ok") else 200
  return _json_response(result, status=status)

async def api_shell(request: web.Request) -> web.Response:
  try:
    state = _get_state_reader().update(timeout=0)
    allowed, reason = is_action_allowed("shell", state, admin=is_admin_mode(_PARAMS))
    if not allowed:
      return _json_response({"ok": False, "error": reason}, status=403)

    try:
      body = await request.json()
    except json.JSONDecodeError:
      return _json_response({"ok": False, "error": "Invalid JSON body."}, status=400)

    command_name = body.get("command", "")
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, run_command, command_name)
    return _json_response(result)
  except Exception as e:
    cloudlog.error(f"aid: api_shell error: {e}")
    return _json_response({"ok": False, "error": f"Internal error: {e}"}, status=500)

async def api_state(request: web.Request) -> web.Response:
  try:
    reader = _get_state_reader()
    reader.update(timeout=0)
    return _json_response({"ok": True, "data": reader.latest()})
  except Exception as e:
    cloudlog.error(f"aid: api_state error: {e}")
    return _json_response({"ok": False, "error": f"Internal error: {e}"}, status=500)


async def api_files_search(request: web.Request) -> web.Response:
  from ai.tools.file_search import search_repo_files

  query = str(request.query.get("q") or request.query.get("query") or "")
  scope = str(request.query.get("scope") or "").strip().lower() or None
  try:
    limit = int(request.query.get("limit", "25"))
  except (TypeError, ValueError):
    limit = 25
  loop = asyncio.get_running_loop()
  result = await loop.run_in_executor(
    None,
    lambda: search_repo_files(query, limit=limit, scope=scope),
  )
  return _json_response(result)


async def api_files_content(request: web.Request) -> web.Response:
  from ai.tools.file_search import read_repo_file_snippet

  path = str(request.query.get("path") or "")
  try:
    max_chars = int(request.query.get("max_chars", "48000"))
  except (TypeError, ValueError):
    max_chars = 48000
  if not path.strip():
    return _json_response({"ok": False, "error": "path is required"}, status=400)
  return _json_response(read_repo_file_snippet(path, max_chars=max_chars))


async def api_context_url(request: web.Request) -> web.Response:
  from ai.tools.context_resolve import fetch_url_context

  url = str(request.query.get("url") or request.query.get("q") or "")
  try:
    max_chars = int(request.query.get("max_chars", "48000"))
  except (TypeError, ValueError):
    max_chars = 48000
  if not url.strip():
    return _json_response({"ok": False, "error": "url is required"}, status=400)
  return _json_response(fetch_url_context(url, max_chars=max_chars))


async def api_context_branch(request: web.Request) -> web.Response:
  from ai.tools.context_resolve import fetch_branch_context

  branch = str(request.query.get("branch") or "")
  try:
    max_chars = int(request.query.get("max_chars", "48000"))
  except (TypeError, ValueError):
    max_chars = 48000
  return _json_response(fetch_branch_context(branch=branch, max_chars=max_chars))


async def api_context_session(request: web.Request) -> web.Response:
  from ai.tools.context_resolve import fetch_session_context

  session_id = str(request.query.get("session_id") or request.query.get("sessionId") or "")
  try:
    max_chars = int(request.query.get("max_chars", "48000"))
  except (TypeError, ValueError):
    max_chars = 48000
  if not session_id.strip():
    return _json_response({"ok": False, "error": "session_id is required"}, status=400)
  return _json_response(fetch_session_context(session_id, max_chars=max_chars))
