"""API handlers — memory."""

from ai.server.handlers._api_common import *  # noqa: F403

async def api_memory(request: web.Request) -> web.Response:
  if request.method == "GET":
    return _json_response(get_memory(_PARAMS))
  try:
    body = await request.json()
  except json.JSONDecodeError:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  if body.get("delete_note_id"):
    return _json_response(delete_note(_PARAMS, str(body["delete_note_id"])))
  if body.get("note"):
    return _json_response(append_note(_PARAMS, body["note"], body.get("tags")))
  if body.get("vehicle_profile"):
    return _json_response(update_vehicle_profile(_PARAMS, body["vehicle_profile"]))
  return _json_response({"ok": False, "error": "Nothing to update"}, status=400)

async def api_skills(request: web.Request) -> web.Response:
  """List or persist enabled agent skills."""
  if request.method == "GET":
    enabled = load_enabled_skill_ids(_PARAMS)
    return _json_response({
      "ok": True,
      "skills": list_skills(),
      "enabled": sorted(enabled) if enabled else None,
    })
  try:
    body = await request.json()
  except json.JSONDecodeError:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  ids = body.get("enabled") or []
  if not isinstance(ids, list):
    return _json_response({"ok": False, "error": "enabled must be a list"}, status=400)
  save_enabled_skill_ids(_PARAMS, [str(x) for x in ids if x])
  return _json_response({"ok": True, "enabled": ids})
