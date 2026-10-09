"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""The rest of the parameter surface: change history, drift fingerprint, backup and QR.

CarrotPilot's app shows a "what changed?" screen, and it moves a whole settings set between
devices by scanning a QR code. Both need the endpoints here. The history is what makes a
drifted value explainable, and the fingerprint is what lets the app say "3 settings differ
from your last known good state" without diffing every key on the phone.
"""

import asyncio
import json
import os

from aiohttp import web

from ..config import PARAMS_BACKUP_PATH
from ..services.param_changes import (
  count_changes_since,
  observe_param_values,
  param_fingerprint,
  read_fingerprint_baseline,
  read_param_changes,
  verify_param_changes,
  write_fingerprint_baseline,
)
from ..services.params_backup import (
  build_params_qr_payload,
  get_all_param_values_for_backup,
  get_qr_dependency_status,
  parse_params_qr_payload,
  preview_param_restore_values,
  restore_param_values_from_backup,
  restore_param_values_validated,
  write_params_backup_file,
)
from ..services.settings import carrot_defaults
from .params import PARAMS_KEY

MAX_CHANGES = 500


def _fingerprint_now(params) -> dict:
  defaults = carrot_defaults()
  from ..services.params import get_param_values

  values = get_param_values(params, sorted(defaults), defaults)
  # Drift is only meaningful for keys the catalog owns, so hardware readouts and synthetic
  # values (which change on every read) cannot report themselves as "changed".
  observe_param_values(values, allowed=set(defaults))
  return param_fingerprint(values)


async def api_param_changes(request: web.Request) -> web.Response:
  try:
    limit = int(request.query.get("limit", "50"))
  except ValueError:
    limit = 50
  limit = max(0, min(limit, MAX_CHANGES))
  name = str(request.query.get("name", "")).strip()
  source = str(request.query.get("source", "")).strip()
  changes = await asyncio.to_thread(read_param_changes, limit, name, source)
  return web.json_response({"ok": True, "changes": changes})


async def api_param_changes_verify(request: web.Request) -> web.Response:
  """Re-walk the hash chain. Hashing is pointless if nothing ever checks it."""
  return web.json_response(await asyncio.to_thread(verify_param_changes))


async def api_param_fingerprint(request: web.Request) -> web.Response:
  """One short digest of every setting plus how it compares to the saved reference."""
  params = request.app[PARAMS_KEY]

  def build() -> dict:
    result = _fingerprint_now(params)
    baseline = read_fingerprint_baseline()
    if baseline is None:
      # First look: adopt the current state as the reference so later visits can say
      # "changed since / unchanged" without the user setting it up.
      baseline = write_fingerprint_baseline(result["fingerprint"])
    result["baseline"] = baseline
    result["changed"] = result["fingerprint"] != baseline.get("fingerprint")
    result["changed_count"] = count_changes_since(int(baseline.get("ts") or 0), allowed=set(carrot_defaults())) if result["changed"] else 0
    return {"ok": True, **result}

  try:
    return web.json_response(await asyncio.to_thread(build))
  except Exception as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def api_param_fingerprint_baseline(request: web.Request) -> web.Response:
  """Set the current settings as the reference to compare against from now on."""
  params = request.app[PARAMS_KEY]

  def build() -> dict:
    return {"ok": True, "baseline": write_fingerprint_baseline(_fingerprint_now(params)["fingerprint"])}

  try:
    return web.json_response(await asyncio.to_thread(build))
  except Exception as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def api_params_backup_download(request: web.Request) -> web.Response:
  """A plain JSON dump of every setting - the human-readable counterpart to the QR."""
  params = request.app[PARAMS_KEY]
  try:
    await asyncio.to_thread(write_params_backup_file, params, PARAMS_BACKUP_PATH)
  except Exception as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=500)
  if not await asyncio.to_thread(os.path.exists, PARAMS_BACKUP_PATH):
    return web.json_response({"ok": False, "error": "backup file is not available"}, status=404)
  return web.FileResponse(PARAMS_BACKUP_PATH, headers={"Content-Disposition": "attachment; filename=params_backup.json"})


async def api_params_restore(request: web.Request) -> web.Response:
  """Restore from an uploaded `params_backup.json` (multipart, field `file`)."""
  params = request.app[PARAMS_KEY]
  try:
    reader = await request.multipart()
    part = await reader.next()
    if part is None or part.name != "file":
      return web.json_response({"ok": False, "error": "missing file field"}, status=400)
    raw = await part.read(decode=False)
    payload = json.loads(raw.decode("utf-8", errors="replace"))
    if not isinstance(payload, dict):
      return web.json_response({"ok": False, "error": "bad json format (must be object)"}, status=400)
    result = await asyncio.to_thread(restore_param_values_from_backup, params, payload)
  except ValueError as exc:
    return web.json_response({"ok": False, "error": f"bad json: {exc}"}, status=400)
  except Exception as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=500)
  return web.json_response({"ok": True, "result": result})


async def api_params_qr_backup(request: web.Request) -> web.Response:
  params = request.app[PARAMS_KEY]
  try:
    payload = await asyncio.to_thread(build_params_qr_payload, params)
  except Exception as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=500)
  return web.json_response({"ok": True, **payload}, headers={"Cache-Control": "no-store"})


async def api_params_qr_dependency(request: web.Request) -> web.Response:
  return web.json_response(get_qr_dependency_status())


async def api_params_qr_dependency_ensure(request: web.Request) -> web.Response:
  """Report whether the optional encoder is present.

  CarrotPilot pip-installs brotli here. This fork will not start a package install from an
  HTTP request on a car computer, so the answer is just the status: without brotli the QR
  is emitted as CQR4, which CarrotPilot's decoder already reads.
  """
  status = get_qr_dependency_status()
  return web.json_response({**status, "configured": False, "message": "no install performed; CQR4 is used"})


async def _restore_body(request: web.Request) -> tuple[dict, list | None] | web.Response:
  try:
    body = await request.json()
  except Exception:
    return web.json_response({"ok": False, "error": "invalid json"}, status=400)
  if not isinstance(body, dict):
    return web.json_response({"ok": False, "error": "body must be a JSON object"}, status=400)
  keys = body.get("keys")
  return body, keys if isinstance(keys, list) else None


async def api_params_restore_preview(request: web.Request) -> web.Response:
  """Show what a QR payload would change, without changing anything."""
  parsed = await _restore_body(request)
  if isinstance(parsed, web.Response):
    return parsed
  body, keys = parsed
  params = request.app[PARAMS_KEY]
  try:
    values = await asyncio.to_thread(parse_params_qr_payload, params, body.get("values") if isinstance(body.get("values"), dict) else body.get("payload"))
    preview = await asyncio.to_thread(preview_param_restore_values, params, values, keys)
  except Exception as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=400)
  return web.json_response({"ok": True, "preview": preview})


async def api_params_restore_json(request: web.Request) -> web.Response:
  """Apply a QR payload. Values are validated one at a time, so a bad key cannot half-write."""
  parsed = await _restore_body(request)
  if isinstance(parsed, web.Response):
    return parsed
  body, keys = parsed
  params = request.app[PARAMS_KEY]
  try:
    values = await asyncio.to_thread(parse_params_qr_payload, params, body.get("values") if isinstance(body.get("values"), dict) else body.get("payload"))
    restored = await asyncio.to_thread(restore_param_values_validated, params, values, keys)
  except Exception as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=400)
  return web.json_response({"ok": True, **restored})


async def api_params_backup_json(request: web.Request) -> web.Response:
  """The backup as JSON rather than a QR string - for callers that just want the values."""
  params = request.app[PARAMS_KEY]
  try:
    values = await asyncio.to_thread(get_all_param_values_for_backup, params)
  except Exception as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=500)
  return web.json_response({"ok": True, "count": len(values), "values": values})


def register(app: web.Application) -> None:
  app.router.add_get("/api/param_changes", api_param_changes)
  app.router.add_get("/api/param_changes/verify", api_param_changes_verify)
  app.router.add_get("/api/param_fingerprint", api_param_fingerprint)
  app.router.add_post("/api/param_fingerprint/baseline", api_param_fingerprint_baseline)
  app.router.add_get("/api/params_backup", api_params_backup_json)
  app.router.add_post("/api/params_restore", api_params_restore)
  app.router.add_get("/api/params_qr_dependency", api_params_qr_dependency)
  app.router.add_post("/api/params_qr_dependency/ensure", api_params_qr_dependency_ensure)
  app.router.add_get("/api/params_qr_backup", api_params_qr_backup)
  app.router.add_post("/api/params_restore_preview", api_params_restore_preview)
  app.router.add_post("/api/params_restore_json", api_params_restore_json)
  app.router.add_get("/download/params_backup.json", api_params_backup_download)
