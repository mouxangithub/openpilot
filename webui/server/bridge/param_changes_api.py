"""HTTP API endpoints for param change history and settings fingerprint.

Ported from CarrotPilot (cp):
  selfdrive/carrot/server/features/params.py (param_changes + fingerprint sections)

Adapted for sunnypilot (sp) webui architecture with /api/opui/ prefix.
"""
from __future__ import annotations

import asyncio

from aiohttp import web

from webui.server.deps import json_response
from webui.server.bridge.param_changes_service import (
  append_param_change,
  count_changes_since,
  get_settings_fingerprint,
  note_known_value,
  param_fingerprint,
  read_fingerprint_baseline,
  read_param_changes,
  verify_param_changes,
  write_fingerprint_baseline,
)


async def api_param_changes(request: web.Request) -> web.Response:
  """Return param change history, newest first.

  GET /api/opui/carrot/settings/param_changes?limit=50&name=...&source=...
  """
  try:
    limit = int(request.query.get("limit", "50"))
  except ValueError:
    limit = 50
  name = str(request.query.get("name", "")).strip()
  source = str(request.query.get("source", "")).strip()
  changes = await asyncio.to_thread(read_param_changes, max(0, min(limit, 500)), name, source)
  return json_response({"ok": True, "changes": changes})


async def api_param_changes_verify(request: web.Request) -> web.Response:
  """Re-walk the hash chain and report the first break, if any."""
  return json_response(await asyncio.to_thread(verify_param_changes))


async def api_param_fingerprint(request: web.Request) -> web.Response:
  """One short digest of every carrot tuning setting, plus comparison to saved baseline."""
  try:
    return json_response(await asyncio.to_thread(get_settings_fingerprint))
  except Exception as e:
    return json_response({"ok": False, "error": str(e)}, status=500)


async def api_param_fingerprint_baseline(request: web.Request) -> web.Response:
  """Set the current settings as the reference fingerprint to compare against from now on."""
  try:
    from webui.server.bridge.carrot_tuning_api import CARROT_TUNING_DEFAULTS, carrot_value_str
    values = {}
    for key in sorted(CARROT_TUNING_DEFAULTS.keys()):
      values[key] = carrot_value_str(key) or ""
  except Exception:
    values = {}
  fingerprint = await asyncio.to_thread(
    lambda: param_fingerprint(values)["fingerprint"]
  )
  result = await asyncio.to_thread(write_fingerprint_baseline, fingerprint)
  return json_response({"ok": True, "baseline": result})
