"""API handlers — misc."""

from ai.server.handlers._api_common import *  # noqa: F403

async def api_notifications(request: web.Request) -> web.Response:
  if request.method == "POST":
    mark_notifications_read()
    try:
      await broadcast_notifications()
    except Exception as e:
      cloudlog.warning(f"aid: broadcast_notifications failed: {e}")
    return _json_response({"ok": True})
  unread = request.query.get("unread", "1") != "0"
  return _json_response(list_notifications(unread_only=unread))

async def api_adaptation_bundle(request: web.Request) -> web.Response:
  project_id = request.match_info.get("project_id", "")
  from ai.tools.adaptation import export_adaptation_bundle
  result = export_adaptation_bundle(project_id)
  if not result.get("ok"):
    return _json_response(result, status=404)
  if request.query.get("download") == "1":
    filename = f"adaptation_{project_id}.json"
    return web.Response(
      body=json.dumps(result, ensure_ascii=False, indent=2),
      content_type="application/json",
      headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
  return _json_response(result)


# -----------------------------------------------------------------------------
# Streaming helpers
# -----------------------------------------------------------------------------

async def api_usage(request: web.Request) -> web.Response:
  return _json_response({
    "ok": True,
    "usage": load_usage(_PARAMS),
    "embeddingUsage": load_embedding_usage(_PARAMS),
  })
