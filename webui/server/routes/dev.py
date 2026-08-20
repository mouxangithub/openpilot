"""Dev-only routes for PC preview simulation."""

from __future__ import annotations

import os

from aiohttp import web

from webui.server.deps import json_response


def _dev_enabled() -> bool:
  return os.environ.get("WEBUI_DEV_PC") == "1"


def _sync_sim_flags() -> None:
  from webui.dev.mock_runtime import SIM

  if not SIM.get("started"):
    SIM["engaged"] = False
    SIM["ui_status"] = "disengaged"
    return
  if SIM.get("engaged") or SIM.get("ui_status") == "engaged":
    SIM["engaged"] = True
    if SIM.get("ui_status") in (None, "", "disengaged"):
      SIM["ui_status"] = "engaged"
  elif SIM.get("ui_status") == "disengaged":
    SIM["engaged"] = False


def _apply_sim_patch(body: dict) -> None:
  from webui.dev.mock_runtime import SIM

  for k, v in body.items():
    if k in SIM:
      SIM[k] = v
  if "engaged" in body and body["engaged"]:
    SIM["ui_status"] = body.get("ui_status") or SIM.get("ui_status") or "engaged"
  if "engaged" in body and not body["engaged"]:
    SIM["ui_status"] = body.get("ui_status") or "disengaged"
  if body.get("started") is False:
    SIM["engaged"] = False
    SIM["ui_status"] = "disengaged"
  _sync_sim_flags()


def _dev_response(extra: dict | None = None) -> dict:
  from webui.dev.mock_runtime import SIM
  from webui.server.bridge.home_api import snapshot_home
  from webui.server.bridge.state_hub import _set_home, get_state, refresh_dev_state

  refresh_dev_state()
  _set_home(snapshot_home())
  out = {"ok": True, "simulation": dict(SIM), "state": get_state(), "home": snapshot_home()}
  if extra:
    out.update(extra)
  return out


async def api_dev_simulation_get(_request: web.Request) -> web.Response:
  if not _dev_enabled():
    return json_response({"ok": False, "error": "not in dev mode"}, status=404)
  return json_response(_dev_response())


async def api_dev_simulation_post(request: web.Request) -> web.Response:
  if not _dev_enabled():
    return json_response({"ok": False, "error": "not in dev mode"}, status=404)
  try:
    body = await request.json()
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  if not isinstance(body, dict):
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  _apply_sim_patch(body)
  return json_response(_dev_response())


async def api_dev_presets(request: web.Request) -> web.Response:
  if not _dev_enabled():
    return json_response({"ok": False, "error": "not in dev mode"}, status=404)
  from webui.dev.mock_runtime import SIM

  preset = request.match_info.get("preset", "")
  presets = {
    "home": {"started": False, "engaged": False, "ui_status": "disengaged", "alert_text1": "", "alert_text2": "", "alert_size": "none"},
    "onroad_engaged": {
      "started": True, "engaged": True, "ui_status": "engaged", "speed_kmh": 88,
      "alert_text1": "", "alert_text2": "", "alert_size": "none",
      "torque_bar": True, "torque_utilization": 0.62, "developer_ui": 3,
      "confidence_target": 0.85,
    },
    "onroad_disengaged": {"started": True, "engaged": False, "ui_status": "disengaged", "speed_kmh": 45, "alert_text1": "", "alert_text2": "", "alert_size": "none"},
    "override": {"started": True, "engaged": True, "ui_status": "override", "speed_kmh": 100, "alert_text1": "", "alert_text2": "", "alert_size": "none"},
    "lat_only": {"started": True, "engaged": True, "ui_status": "lat_only", "speed_kmh": 60, "alert_text1": "", "alert_text2": "", "alert_size": "none"},
    "alert_critical": {
      "started": True, "engaged": False, "ui_status": "disengaged", "speed_kmh": 0,
      "alert_text1": "Brake!", "alert_text2": "Take control immediately", "alert_status": "critical", "alert_size": "mid",
    },
    "e2e_green": {
      "started": True, "engaged": True, "ui_status": "engaged", "speed_kmh": 0,
      "standstill": True, "e2e_green_light": True, "e2e_lead_depart": False, "alert_size": "none",
    },
    "standstill_timer": {
      "started": True, "engaged": False, "ui_status": "disengaged", "speed_kmh": 0,
      "standstill": True, "standstill_timer_enabled": True, "standstill_timer": 125,
      "alert_size": "none",
    },
    "long_only": {
      "started": True, "engaged": True, "ui_status": "long_only", "speed_kmh": 65,
      "alert_size": "none",
    },
    "alert_full": {
      "started": True, "engaged": False, "ui_status": "disengaged", "speed_kmh": 40,
      "alert_text1": "TAKE CONTROL", "alert_text2": "Steering unavailable",
      "alert_status": "critical", "alert_size": "full",
    },
    "home_update": {
      "started": False, "engaged": False, "ui_status": "disengaged",
      "update_available": True, "fetch_available": False,
      "new_description": "sunnypilot 2026.08.12-dev",
      "new_release_notes": "<h2>WebUI P2</h2><p>Home UPDATE pill + overlay.</p>",
      "offroad_alerts": [],
    },
    "home_alerts": {
      "started": False, "engaged": False, "ui_status": "disengaged",
      "update_available": False,
      "offroad_alerts": [
        {"key": "Offroad_ConnectivityNeeded", "text": "Connect to internet to check for updates.", "severity": 1},
      ],
    },
    "confidence_low": {
      "started": True, "engaged": True, "ui_status": "engaged", "speed_kmh": 55,
      "torque_bar": True, "torque_utilization": 0.35, "developer_ui": 0,
      "confidence_target": 0.12, "alert_size": "none",
    },
    "confidence_high": {
      "started": True, "engaged": True, "ui_status": "engaged", "speed_kmh": 95,
      "torque_bar": True, "torque_utilization": 0.78, "developer_ui": 2,
      "confidence_target": 0.92, "experimental_mode": True, "alert_size": "none",
    },
    "onroad_overlay": {
      "started": True, "engaged": True, "ui_status": "engaged", "speed_kmh": 72,
      "experimental_mode": True, "experimental_mode_confirmed": True,
      "torque_bar": True, "torque_utilization": 0.5, "developer_ui": 3,
      "confidence_target": 0.7, "alert_size": "none",
    },
    "sound_engage": {
      "started": True, "engaged": True, "ui_status": "engaged", "speed_kmh": 72,
      "alert_sound": "engage", "alert_size": "none",
    },
    "sound_disengage": {
      "started": True, "engaged": False, "ui_status": "disengaged", "speed_kmh": 45,
      "alert_sound": "disengage", "alert_size": "none",
    },
    "sound_warning": {
      "started": True, "engaged": False, "ui_status": "disengaged", "speed_kmh": 0,
      "alert_sound": "warningImmediate", "alert_size": "mid",
      "alert_text1": "Brake!", "alert_text2": "Take control immediately", "alert_status": "critical",
    },
    "software_agnos": {
      "started": False, "engaged": False, "ui_status": "disengaged",
      "agnos_update_required": True,
      "agnos_ready_to_reboot": False,
      "agnos_current_version": "11.9.9",
      "agnos_target_version": "12.0.0",
      "agnos_sim_rebooting": False,
      "agnos_sim_reboot_until": 0.0,
    },
  }
  if preset not in presets:
    return json_response({"ok": False, "error": f"unknown preset: {preset}"}, status=400)
  SIM.update(presets[preset])
  _sync_sim_flags()
  return json_response(_dev_response({"preset": preset}))


def register_dev_routes(app: web.Application) -> None:
  if not _dev_enabled():
    return
  app.router.add_get("/api/opui/dev/simulation", api_dev_simulation_get)
  app.router.add_post("/api/opui/dev/simulation", api_dev_simulation_post)
  app.router.add_post("/api/opui/dev/preset/{preset}", api_dev_presets)
