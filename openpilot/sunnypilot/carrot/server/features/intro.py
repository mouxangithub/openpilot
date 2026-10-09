"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""First-run wizard state and its driving-control presets.

The preset table is a copy of CarrotPilot's, but which keys it can actually write is decided
here, at apply time, against sunnypilot's own parameter table: `HyundaiCameraSCC`,
`EnableCornerRadar` and `CanfdHDA2` are Hyundai-only and do not exist in this fork, so they
are reported as skipped instead of being invented. A preset that silently wrote a subset
would look successful while leaving the car in a different configuration than the user chose.

Whether the wizard should appear is decided on the device, and defaults to "no": an existing
tuned device must never have its settings overwritten by a wizard it was shown by mistake.
"""

import asyncio
import json
import os

from aiohttp import web

from ..config import CARROT_INTRO_STATE_PATH
from ..services.params import ParamWriteError, set_param_value
from .params import PARAMS_KEY

# Values copied from CarrotPilot's intro/presets.py. Keys absent from sunnypilot's
# parameter table are skipped at apply time rather than dropped here, so the gap is visible.
PRESETS: dict[str, dict[str, int]] = {
  "radar_long": {
    "HyundaiCameraSCC": 1,
    "SpeedFromPCM": 0,
    "DisableDM": 0,
    "EnableRadarTracks": 0,
    "EnableCornerRadar": 1,
    "AutoCruiseControl": 1,
    "AutoEngage": 2,
  },
  "camera_long": {
    "HyundaiCameraSCC": 1,
    "SpeedFromPCM": 0,
    "DisableDM": 0,
    "EnableRadarTracks": 0,
    "EnableCornerRadar": 0,
    "AutoCruiseControl": 1,
    "AutoEngage": 2,
  },
  "stock": {
    "HyundaiCameraSCC": 0,
    "SpeedFromPCM": 2,
    "DisableDM": 0,
    "EnableRadarTracks": 0,
    "EnableCornerRadar": 0,
    "AutoCruiseControl": 0,
    "AutoEngage": 2,
  },
}


def _read_state() -> dict:
  try:
    with open(CARROT_INTRO_STATE_PATH, encoding="utf-8") as f:
      data = json.load(f)
  except Exception:
    return {}
  return data if isinstance(data, dict) else {}


def _write_state(state: dict) -> dict:
  os.makedirs(os.path.dirname(CARROT_INTRO_STATE_PATH), exist_ok=True)
  tmp_path = CARROT_INTRO_STATE_PATH + ".tmp"
  with open(tmp_path, "w", encoding="utf-8") as f:
    json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
    f.write("\n")
    f.flush()
    os.fsync(f.fileno())
  os.replace(tmp_path, CARROT_INTRO_STATE_PATH)
  return state


def _writable_keys(params, values: dict) -> tuple[dict, list[str]]:
  try:
    from openpilot.common.params import UnknownKeyName

    def known(name: str) -> bool:
      try:
        params.check_key(name)
        return True
      except UnknownKeyName:
        return False
      except Exception:
        return False
  except Exception:
    def known(name: str) -> bool:
      try:
        params.get_type(name)
        return True
      except Exception:
        return False

  keep = {}
  skipped = []
  for name, value in values.items():
    if known(name):
      keep[name] = value
    else:
      skipped.append(name)
  return keep, skipped


async def api_intro_state(request: web.Request) -> web.Response:
  state = await asyncio.to_thread(_read_state)
  # "No state file" must mean done, not fresh: this update lands on devices that are already
  # tuned, and the wizard writes driving-control parameters. Showing it to them would
  # overwrite a working setup, so the wizard only returns after an explicit reset.
  done = bool(state.get("done", True))
  return web.json_response({
    "ok": True,
    "should_show": not done,
    "done": done,
    "completed_at": state.get("completed_at", ""),
    "preset": state.get("preset", ""),
    "presets": sorted(PRESETS),
  })


async def api_intro_complete(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    body = {}
  if not isinstance(body, dict):
    body = {}
  state = await asyncio.to_thread(_read_state)
  state["done"] = True
  state["preset"] = str(body.get("preset") or state.get("preset") or "")
  state["completed_at"] = str(body.get("completed_at") or "")
  await asyncio.to_thread(_write_state, state)
  return web.json_response({"ok": True, "done": True, "preset": state["preset"]})


async def api_intro_reset(request: web.Request) -> web.Response:
  await asyncio.to_thread(_write_state, {"done": False})
  return web.json_response({"ok": True, "done": False})


async def api_intro_apply_preset(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    return web.json_response({"ok": False, "error": "invalid json"}, status=400)
  if not isinstance(body, dict):
    return web.json_response({"ok": False, "error": "body must be a JSON object"}, status=400)

  name = str(body.get("name") or body.get("preset") or "").strip()
  values = PRESETS.get(name)
  if values is None:
    return web.json_response({"ok": False, "error": f"unknown preset {name}", "presets": sorted(PRESETS)}, status=400)

  params = request.app[PARAMS_KEY]
  keep, skipped = _writable_keys(params, values)
  if not keep:
    return web.json_response({
      "ok": False,
      "error": f"no parameter of preset {name} exists in this fork",
      "skipped": skipped,
    }, status=400)

  applied: dict[str, int] = {}
  failures: list[dict[str, str]] = []
  for key, value in keep.items():
    try:
      set_param_value(params, key, value)
      applied[key] = value
    except ParamWriteError as exc:
      failures.append({"key": key, "err": str(exc)})

  state = await asyncio.to_thread(_read_state)
  state["preset"] = name
  await asyncio.to_thread(_write_state, state)

  return web.json_response({
    "ok": not failures,
    "preset": name,
    "applied": applied,
    "skipped": skipped,
    "fails": failures,
    # Stated plainly: a partial preset leaves the car in a configuration the UI did not offer.
    "partial": bool(skipped or failures),
  })


def register(app: web.Application) -> None:
  app.router.add_get("/api/intro/state", api_intro_state)
  app.router.add_post("/api/intro/complete", api_intro_complete)
  app.router.add_post("/api/intro/reset", api_intro_reset)
  app.router.add_post("/api/intro/apply_preset", api_intro_apply_preset)
