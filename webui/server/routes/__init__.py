"""Route registration."""

from __future__ import annotations

import asyncio
import json
import os

from aiohttp import web

from webui.server.deps import WEB_DIR, json_response
from webui.server.bridge.panel_catalog import panel_schema
from webui.server.bridge.params_api import batch_get, get_param, panel_values, put_param, remove_param
from webui.server.bridge.state_api import snapshot_ui_state
from webui.server.bridge.system_api import manager_last_error, run_action, software_status
from webui.server.bridge.network_api import (
  network_advanced_status,
  wifi_connect,
  wifi_connect_hidden,
  wifi_forget,
  wifi_scan,
  wifi_set_metered,
  wifi_set_tethering,
  wifi_set_tethering_password,
  wifi_status,
)
from webui.server.bridge.webrtc_api import webrtc_notify, webrtc_offer, webrtc_schema
from webui.server.bridge.trips_api import trips_stats
from webui.server.bridge.models_api import accelerator_link_set, models_select, models_set_mirror, models_status, models_toggle_favorite
from webui.server.bridge.design_tokens import tokens_payload
from webui.server.bridge.assets_api import resolve_asset
from webui.server.bridge.stream_health_api import snapshot_stream_health
from webui.server.bridge.model_overlay import snapshot_model_overlay
from webui.server.bridge.ssh_api import ssh_fetch_keys, ssh_remove_keys, ssh_status
from webui.server.bridge.osm_api import osm_download_progress, osm_fetch_regions, osm_map_size_mb, osm_select_region, osm_clear_incomplete_selection
from webui.server.bridge.vehicle_api import vehicle_platforms, vehicle_select, vehicle_brand_widgets
from webui.server.bridge.sunnylink_api import sunnylink_pair_url, sunnylink_status
from webui.server.bridge.firehose_api import firehose_status
from webui.server.bridge.storage_api import clear_storage, snapshot_storage
from webui.server.bridge.device_api import device_extras, device_pair_url, driver_view_status, regulatory_html, set_driver_view, set_language
from webui.server.bridge.imu_calibration_api import (
  snapshot_imu_calibration,
  start_imu_calibration,
  cancel_imu_calibration,
  reset_imu_calibration,
  set_imu_calibration_enabled,
)
from webui.server.bridge.steering_api import torque_versions
from webui.server.bridge.home_api import snapshot_home
from webui.server.bridge.onboarding_api import accept_sunnylink_consent, accept_terms, complete_training, onboarding_status
from webui.server.bridge.i18n_api import snapshot_i18n
from webui.server.bridge.webui_update_api import apply_webui_update, dismiss_webui_update, snapshot_webui_update
from webui.server.bridge.developer_api import developer_error_log
from webui.server.bridge.carrot_navi_api import snapshot_carrot_crossroad, snapshot_carrot_navi_debug
from webui.server.bridge.carrot_settings_backup_api import (
  apply_setting_profile,
  build_params_qr_backup,
  create_setting_profile,
  delete_setting_profile,
  export_params_backup,
  preview_setting_profile,
  read_setting_favorites,
  read_setting_profiles,
  restore_params_backup,
  update_setting_favorites,
  update_setting_profile,
)
from webui.server.bridge.param_changes_api import (
  api_param_changes,
  api_param_changes_verify,
  api_param_fingerprint,
  api_param_fingerprint_baseline,
)
from webui.server.bridge.offroad_guard import require_offroad
from webui.server.bridge.osm_api import osm_delete_maps
from webui.server.bridge.bluetooth_api import api_bluetooth_status, api_bluetooth_mutate
from webui.server.bridge.ws_handler import ws_opui_handler


async def api_jetlink_status(_request: web.Request) -> web.Response:
  """Return jetlink accelerator link status."""
  try:
    from openpilot.sunnypilot import jetlink_adapter
    status = jetlink_adapter.status()
    if status is None:
      return json_response({"ok": True, "status": {"mode": "none", "connected": False, "enabled": False}})
    return json_response({
      "ok": True,
      "status": {
        "mode": getattr(status, "mode", "unknown"),
        "connected": getattr(status, "connected", False),
        "enabled": getattr(status, "enabled", False),
      }
    })
  except Exception as exc:
    return json_response({"ok": False, "error": str(exc), "status": {"mode": "none", "connected": False, "enabled": False}})


async def api_bootstrap(_request: web.Request) -> web.Response:
  if os.environ.get("WEBUI_DEV_PC") == "1":
    from webui.dev.agnos_sim import dev_bootstrap_blocked
    if dev_bootstrap_blocked():
      raise web.HTTPServiceUnavailable(
        text=json.dumps({"ok": False, "error": "dev_agnos_rebooting"}),
        content_type="application/json",
        headers={"Retry-After": "1"},
      )
  from webui.server.bridge.ws_rpc import bootstrap_payload
  return json_response(bootstrap_payload())


async def api_state(_request: web.Request) -> web.Response:
  from webui.server.bridge.state_hub import state_ready
  for _ in range(15):
    if state_ready():
      break
    await asyncio.sleep(0.1)
  if not state_ready():
    raise web.HTTPServiceUnavailable(
      text=json.dumps({"ok": False, "error": "state_not_ready"}),
      content_type="application/json",
      headers={"Retry-After": "1"},
    )
  return json_response(await asyncio.to_thread(snapshot_ui_state))


async def api_panels_schema(_request: web.Request) -> web.Response:
  return json_response(await asyncio.to_thread(panel_schema))


async def api_panel_get(request: web.Request) -> web.Response:
  panel_id = request.match_info.get("panel_id", "")
  return json_response(await asyncio.to_thread(panel_values, panel_id))


async def api_param_get(request: web.Request) -> web.Response:
  key = request.match_info.get("key", "")
  return json_response(get_param(key))


async def api_param_put(request: web.Request) -> web.Response:
  from webui.server.bridge.param_changes_service import append_param_change
  key = request.match_info.get("key", "")
  try:
    body = await request.json()
    value = str(body.get("value", ""))
    needs_cycle = bool(body.get("needs_cycle", False))
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  # Read previous value for history tracking
  prev_result = get_param(key)
  previous = prev_result.get("value") if prev_result.get("ok") else None
  result = await asyncio.to_thread(put_param, key, value, needs_cycle=needs_cycle)
  # Log to change history if value actually changed
  if result.get("ok") and previous is not None and str(previous) != value:
    append_param_change(key, previous, value, source="web_ui")
  return json_response(result)


async def api_param_delete(request: web.Request) -> web.Response:
  key = request.match_info.get("key", "")
  return json_response(remove_param(key))


async def api_params_batch(request: web.Request) -> web.Response:
  try:
    body = await request.json()
    keys = body.get("keys", [])
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  return json_response(batch_get(keys))


async def api_params_backup(request: web.Request) -> web.Response:
  from webui.server.bridge.params_backup_api import backup_params
  return json_response(backup_params())


async def api_params_backup_restore(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  from webui.server.bridge.params_backup_api import restore_params
  return json_response(restore_params(body.get("snapshot")))


async def api_navcard_get(request: web.Request) -> web.Response:
  from webui.server.bridge.navcard_api import navcard_snapshot
  return json_response(navcard_snapshot())


async def api_navcard_cancel(request: web.Request) -> web.Response:
  from webui.server.bridge.navcard_api import cancel_navigation
  return json_response(cancel_navigation())


async def api_following_profile_get(request: web.Request) -> web.Response:
  from webui.server.bridge.following_profile_api import snapshot_following_profile
  return json_response(snapshot_following_profile())


async def api_following_profile_put(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  from webui.server.bridge.following_profile_api import apply_following_profile
  return json_response(apply_following_profile(body))


async def api_action(request: web.Request) -> web.Response:
  action = request.match_info.get("action", "")
  payload = {}
  if request.can_read_body:
    try:
      payload = await request.json()
    except json.JSONDecodeError:
      payload = {}
  return json_response(run_action(action, payload))


async def api_software(_request: web.Request) -> web.Response:
  return json_response(software_status())


async def api_manager_error(_request: web.Request) -> web.Response:
  return json_response(manager_last_error())


async def api_wifi_status(_request: web.Request) -> web.Response:
  return json_response(wifi_status())


async def api_wifi_scan(request: web.Request) -> web.Response:
  trigger = request.rel_url.query.get("trigger", "").lower() in ("1", "true", "yes")
  return json_response(wifi_scan(trigger=trigger))


async def api_wifi_connect(request: web.Request) -> web.Response:
  try:
    body = await request.json()
    ssid = str(body.get("ssid", ""))
    password = str(body.get("password", ""))
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  return json_response(wifi_connect(ssid, password))


async def api_wifi_forget(request: web.Request) -> web.Response:
  try:
    body = await request.json()
    ssid = str(body.get("ssid", ""))
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  return json_response(wifi_forget(ssid))


async def api_network_advanced(_request: web.Request) -> web.Response:
  return json_response(network_advanced_status())


async def api_wifi_tethering(request: web.Request) -> web.Response:
  try:
    body = await request.json()
    active = bool(body.get("active", False))
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  return json_response(wifi_set_tethering(active))


async def api_wifi_tethering_password(request: web.Request) -> web.Response:
  try:
    body = await request.json()
    password = str(body.get("password", ""))
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  return json_response(wifi_set_tethering_password(password))


async def api_wifi_metered(request: web.Request) -> web.Response:
  try:
    body = await request.json()
    metered = int(body.get("metered", 0))
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  return json_response(wifi_set_metered(metered))


async def api_wifi_connect_hidden(request: web.Request) -> web.Response:
  try:
    body = await request.json()
    ssid = str(body.get("ssid", ""))
    password = str(body.get("password", ""))
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  return json_response(wifi_connect_hidden(ssid, password))


async def api_webrtc_schema(_request: web.Request) -> web.Response:
  loop = asyncio.get_running_loop()
  result = await loop.run_in_executor(None, webrtc_schema)
  return json_response(result)


async def api_webrtc_offer(request: web.Request) -> web.Response:
  try:
    body = await request.json()
    sdp = str(body.get("sdp", ""))
    camera = str(body.get("init_camera", "road"))
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  loop = asyncio.get_running_loop()
  result = await loop.run_in_executor(None, webrtc_offer, sdp, camera)
  return json_response(result)


async def api_webrtc_notify(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  loop = asyncio.get_running_loop()
  result = await loop.run_in_executor(None, webrtc_notify, body)
  return json_response(result)


async def api_trips(request: web.Request) -> web.Response:
  source = request.query.get("source")
  return json_response(trips_stats(source=source))


async def api_models(_request: web.Request) -> web.Response:
  return json_response(models_status())


async def api_models_select(request: web.Request) -> web.Response:
  try:
    body = await request.json()
    ref = str(body.get("ref", ""))
    index = body.get("index")
    source = str(body.get("source", "qcom"))
    if index is not None:
      index = int(index)
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  return json_response(models_select(ref, index, source=source))


async def api_models_accelerator(request: web.Request) -> web.Response:
  try:
    body = await request.json()
    mode = str(body.get("mode", ""))
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  return json_response(accelerator_link_set(mode))


async def api_models_favorite(request: web.Request) -> web.Response:
  try:
    body = await request.json()
    ref = str(body.get("ref", ""))
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  return json_response(models_toggle_favorite(ref))


async def api_models_mirror(request: web.Request) -> web.Response:
  try:
    body = await request.json()
    which = str(body.get("which", ""))
    mode = str(body.get("mode", ""))
    url = str(body.get("url", ""))
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  return json_response(models_set_mirror(which, mode, url))


async def api_tokens(_request: web.Request) -> web.Response:
  return json_response({"ok": True, **tokens_payload()})


async def api_asset(request: web.Request) -> web.Response:
  rel = request.match_info.get("path", "")
  path = resolve_asset(rel)
  if not path:
    return web.Response(status=404, text="not found")
  return web.FileResponse(path)


async def api_model_overlay(request: web.Request) -> web.Response:
  try:
    w = int(request.query.get("w", "1600"))
    h = int(request.query.get("h", "900"))
  except ValueError:
    w, h = 1600, 900
  static_mock = request.query.get("static") == "1"
  frame = await asyncio.to_thread(snapshot_model_overlay, w, h, static_mock=static_mock)
  etag = frame.get("frame_key") or ""
  if_none = request.headers.get("If-None-Match")
  if if_none and etag and if_none == etag:
    return web.Response(status=304, headers={"ETag": etag})
  return json_response(frame, headers={"ETag": etag} if etag else None)


async def api_ssh_status(_request: web.Request) -> web.Response:
  return json_response(ssh_status())


async def api_ssh_fetch(request: web.Request) -> web.Response:
  try:
    body = await request.json()
    username = str(body.get("username", ""))
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  return json_response(ssh_fetch_keys(username))


async def api_ssh_remove(_request: web.Request) -> web.Response:
  return json_response(ssh_remove_keys())


async def api_osm_regions(request: web.Request) -> web.Response:
  region_type = request.query.get("type", "Country")
  country = request.query.get("country", "")
  return json_response(osm_fetch_regions(region_type, country))


async def api_osm_select(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  return json_response(osm_select_region(
    str(body.get("country", "")),
    str(body.get("country_title", "")),
    str(body.get("state", "")),
    str(body.get("state_title", "")),
  ))


async def api_osm_clear(_request: web.Request) -> web.Response:
  return json_response(osm_clear_incomplete_selection())


async def api_osm_size(_request: web.Request) -> web.Response:
  return json_response(osm_map_size_mb())


async def api_osm_progress(_request: web.Request) -> web.Response:
  return json_response(osm_download_progress())


async def api_vehicle_platforms(_request: web.Request) -> web.Response:
  return json_response(vehicle_platforms())


async def api_vehicle_select(request: web.Request) -> web.Response:
  try:
    body = await request.json()
    bundle = str(body.get("bundle", ""))
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  return json_response(vehicle_select(bundle))


async def api_vehicle_brand_widgets(_request: web.Request) -> web.Response:
  return json_response(vehicle_brand_widgets())


async def api_developer_error_log(_request: web.Request) -> web.Response:
  return json_response(developer_error_log())


async def api_osm_delete(_request: web.Request) -> web.Response:
  return json_response(osm_delete_maps())


async def api_sunnylink_status(_request: web.Request) -> web.Response:
  return json_response(sunnylink_status())


async def api_sunnylink_pair(request: web.Request) -> web.Response:
  mode = request.rel_url.query.get("mode", "pair")
  return json_response(sunnylink_pair_url(mode))


async def api_firehose(_request: web.Request) -> web.Response:
  return json_response(firehose_status())


async def api_storage(_request: web.Request) -> web.Response:
  force = _request.rel_url.query.get("force") == "1"
  return json_response(await asyncio.to_thread(snapshot_storage, force=force))


async def api_storage_clear(request: web.Request) -> web.Response:
  try:
    body = await request.json()
    category = str(body.get("category", "")).strip()
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  if not category:
    return json_response({"ok": False, "error": "category required"}, status=400)
  return json_response(await asyncio.to_thread(clear_storage, category))


async def api_stream_health(_request: web.Request) -> web.Response:
  return json_response(snapshot_stream_health())


async def api_device_extras(_request: web.Request) -> web.Response:
  return json_response(device_extras())


async def api_device_pair(_request: web.Request) -> web.Response:
  return json_response(device_pair_url())


async def api_torque_versions(_request: web.Request) -> web.Response:
  return json_response(torque_versions())


async def api_device_regulatory(_request: web.Request) -> web.Response:
  return json_response(regulatory_html())


async def api_home(_request: web.Request) -> web.Response:
  return json_response(snapshot_home())


async def api_onboarding(_request: web.Request) -> web.Response:
  return json_response(onboarding_status())


async def api_onboarding_accept(_request: web.Request) -> web.Response:
  return json_response(accept_terms())


async def api_onboarding_complete(_request: web.Request) -> web.Response:
  return json_response(complete_training())


async def api_onboarding_sunnylink(request: web.Request) -> web.Response:
  try:
    body = await request.json()
    accept = bool(body.get("accept", True))
  except Exception:
    accept = True
  return json_response(accept_sunnylink_consent(accept))


async def api_driver_view_status(_request: web.Request) -> web.Response:
  return json_response(driver_view_status())


async def api_driver_view_set(request: web.Request) -> web.Response:
  try:
    body = await request.json()
    enabled = bool(body.get("enabled", False))
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  return json_response(set_driver_view(enabled))


async def api_i18n(_request: web.Request) -> web.Response:
  return json_response(snapshot_i18n())


async def api_set_language(request: web.Request) -> web.Response:
  try:
    body = await request.json()
    lang = str(body.get("language", "main"))
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  return json_response(set_language(lang))


async def api_imu_calibration(_request: web.Request) -> web.Response:
  return json_response(snapshot_imu_calibration())


async def api_imu_calibration_control(request: web.Request) -> web.Response:
  action = request.match_info.get("action", "")
  if action == "start":
    return json_response(start_imu_calibration())
  if action == "cancel":
    return json_response(cancel_imu_calibration())
  if action == "reset":
    return json_response(reset_imu_calibration())
  return json_response({"ok": False, "error": f"unknown action: {action}"}, status=400)


async def api_imu_calibration_enabled(request: web.Request) -> web.Response:
  try:
    body = await request.json()
    enabled = bool(body.get("enabled", False))
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  return json_response(set_imu_calibration_enabled(enabled))


async def api_webui_update(request: web.Request) -> web.Response:
  fetch = request.rel_url.query.get("fetch", "").lower() in ("1", "true", "yes")
  return json_response(snapshot_webui_update(fetch=fetch))


async def api_webui_update_dismiss(request: web.Request) -> web.Response:
  commit = ""
  try:
    body = await request.json()
    commit = str(body.get("commit", "") or "")
  except Exception:
    pass
  return json_response(dismiss_webui_update(commit or None))


async def api_webui_update_apply(_request: web.Request) -> web.Response:
  return json_response(apply_webui_update())


async def api_agnos(_request: web.Request) -> web.Response:
  from webui.server.bridge.agnos_api import agnos_snapshot
  return json_response(await asyncio.to_thread(agnos_snapshot))


async def api_carrot_crossroad(_request: web.Request) -> web.Response:
  return json_response(await asyncio.to_thread(snapshot_carrot_crossroad))


async def api_carrot_navi_debug(_request: web.Request) -> web.Response:
  return json_response(await asyncio.to_thread(snapshot_carrot_navi_debug))


async def api_carrot_media(_request: web.Request) -> web.Response:
  from webui.server.bridge.carrot_navi_api import snapshot_carrot_media
  return json_response(await asyncio.to_thread(snapshot_carrot_media))


async def api_agnos_install(_request: web.Request) -> web.Response:
  from webui.server.bridge.agnos_api import start_agnos_install
  return json_response(await asyncio.to_thread(start_agnos_install))


async def api_agnos_reboot(_request: web.Request) -> web.Response:
  from webui.server.bridge.agnos_api import agnos_reboot
  return json_response(await asyncio.to_thread(agnos_reboot))


async def api_headless_mode_get(_request: web.Request) -> web.Response:
  from webui.server.bridge.headless_api import snapshot_headless_mode
  return json_response(await asyncio.to_thread(snapshot_headless_mode))


async def api_headless_mode_put(request: web.Request) -> web.Response:
  from webui.server.bridge.headless_api import apply_headless_mode
  try:
    body = await request.json()
    mode = str(body.get("mode", ""))
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  return json_response(await asyncio.to_thread(apply_headless_mode, mode))


# ---------------------------------------------------------------------------
# Carrot settings: backup / restore / profiles / favorites
# ---------------------------------------------------------------------------
async def api_carrot_settings_backup(_request: web.Request) -> web.Response:
  return json_response(export_params_backup())


async def api_carrot_settings_backup_qr(_request: web.Request) -> web.Response:
  return json_response(build_params_qr_backup())


async def api_carrot_settings_restore(request: web.Request) -> web.Response:
  # Security: restore writes arbitrary Params — offroad only, validated keys.
  guard = require_offroad()
  if guard is not None:
    return json_response(guard, status=403)
  try:
    body = await request.json()
    values = body.get("values", {}) if isinstance(body, dict) else {}
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  return json_response(restore_params_backup(values))


async def api_carrot_profiles(_request: web.Request) -> web.Response:
  return json_response(read_setting_profiles())


async def api_carrot_profile_create(request: web.Request) -> web.Response:
  try:
    body = await request.json()
    name = str(body.get("name", "")) if isinstance(body, dict) else ""
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  try:
    profile = create_setting_profile(name)
  except ValueError as exc:
    code = str(exc)
    message = {
      "PROFILE_NAME_REQUIRED": "missing profile name",
      "PROFILE_LIMIT": "profile limit reached",
    }.get(code, code)
    return json_response({"ok": False, "error": code, "message": message}, status=400)
  return json_response({"ok": True, **profile})


async def api_carrot_profile_update(request: web.Request) -> web.Response:
  profile_id = request.match_info.get("profile_id", "")
  try:
    body = await request.json()
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  try:
    profile = update_setting_profile(profile_id, body)
  except ValueError as exc:
    code = str(exc)
    message = {
      "PROFILE_NAME_REQUIRED": "missing profile name",
      "PROFILE_NO_VALUES": "no valid values to save",
    }.get(code, code)
    return json_response({"ok": False, "error": code, "message": message}, status=400)
  except KeyError:
    return json_response({"ok": False, "error": "profile not found"}, status=404)
  return json_response({"ok": True, **profile})


async def api_carrot_profile_delete(request: web.Request) -> web.Response:
  profile_id = request.match_info.get("profile_id", "")
  try:
    delete_setting_profile(profile_id)
  except KeyError:
    return json_response({"ok": False, "error": "profile not found"}, status=404)
  return json_response({"ok": True})


async def api_carrot_profile_preview(request: web.Request) -> web.Response:
  profile_id = request.match_info.get("profile_id", "")
  try:
    body = await request.json()
    values = body.get("values") if isinstance(body, dict) else None
  except Exception:
    values = None
  try:
    return json_response(preview_setting_profile(profile_id, values))
  except KeyError:
    return json_response({"ok": False, "error": "profile not found"}, status=404)


async def api_carrot_profile_apply(request: web.Request) -> web.Response:
  # Security: apply writes Params — offroad only.
  guard = require_offroad()
  if guard is not None:
    return json_response(guard, status=403)
  profile_id = request.match_info.get("profile_id", "")
  try:
    body = await request.json()
    values = body.get("values") if isinstance(body, dict) else None
  except Exception:
    values = None
  try:
    result = apply_setting_profile(profile_id, values)
  except KeyError:
    return json_response({"ok": False, "error": "profile not found"}, status=404)
  return json_response({"ok": True, **result})


async def api_carrot_favorites(_request: web.Request) -> web.Response:
  return json_response(read_setting_favorites())


# ---------------------------------------------------------------------------
# Carrot settings: param change history + fingerprint
# ---------------------------------------------------------------------------
async def api_carrot_param_changes(request: web.Request) -> web.Response:
  return await api_param_changes(request)


async def api_carrot_param_changes_verify(request: web.Request) -> web.Response:
  return await api_param_changes_verify(request)


async def api_carrot_param_fingerprint(request: web.Request) -> web.Response:
  return await api_param_fingerprint(request)


async def api_carrot_param_fingerprint_baseline(request: web.Request) -> web.Response:
  return await api_param_fingerprint_baseline(request)


async def api_carrot_favorites_update(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  return json_response({"ok": True, **update_setting_favorites(body)})


def register_routes(app: web.Application) -> None:
  app.router.add_get("/api/opui/bootstrap", api_bootstrap)
  app.router.add_get("/api/opui/headless-mode", api_headless_mode_get)
  app.router.add_put("/api/opui/headless-mode", api_headless_mode_put)
  app.router.add_get("/api/opui/state", api_state)
  app.router.add_get("/api/opui/home", api_home)
  app.router.add_get("/api/opui/onboarding", api_onboarding)
  app.router.add_put("/api/opui/onboarding/accept_terms", api_onboarding_accept)
  app.router.add_put("/api/opui/onboarding/sunnylink", api_onboarding_sunnylink)
  app.router.add_put("/api/opui/onboarding/complete", api_onboarding_complete)
  app.router.add_get("/api/opui/i18n", api_i18n)
  app.router.add_get("/api/opui/panels", api_panels_schema)
  app.router.add_get("/api/opui/panels/{panel_id}", api_panel_get)
  # Fixed segments must be registered before /api/opui/params/{key}.
  app.router.add_get("/api/opui/params/backup", api_params_backup)
  app.router.add_post("/api/opui/params/backup/restore", api_params_backup_restore)
  app.router.add_get("/api/opui/params/{key}", api_param_get)
  app.router.add_put("/api/opui/params/{key}", api_param_put)
  app.router.add_delete("/api/opui/params/{key}", api_param_delete)
  app.router.add_post("/api/opui/params/batch", api_params_batch)
  app.router.add_get("/api/opui/navcard", api_navcard_get)
  app.router.add_post("/api/opui/navcard/cancel", api_navcard_cancel)
  app.router.add_get("/api/opui/following-profile", api_following_profile_get)
  app.router.add_put("/api/opui/following-profile", api_following_profile_put)
  app.router.add_post("/api/opui/action/{action}", api_action)
  app.router.add_get("/api/opui/software", api_software)
  app.router.add_get("/api/opui/system/manager_error", api_manager_error)
  app.router.add_get("/api/opui/wifi/status", api_wifi_status)
  app.router.add_get("/api/opui/wifi/scan", api_wifi_scan)
  app.router.add_post("/api/opui/wifi/connect", api_wifi_connect)
  app.router.add_post("/api/opui/wifi/forget", api_wifi_forget)
  app.router.add_get("/api/opui/network/advanced", api_network_advanced)
  app.router.add_post("/api/opui/wifi/tethering", api_wifi_tethering)
  app.router.add_post("/api/opui/wifi/tethering/password", api_wifi_tethering_password)
  app.router.add_post("/api/opui/wifi/metered", api_wifi_metered)
  app.router.add_post("/api/opui/wifi/connect/hidden", api_wifi_connect_hidden)
  app.router.add_get("/api/opui/trips", api_trips)
  app.router.add_get("/api/opui/models", api_models)
  app.router.add_post("/api/opui/models/select", api_models_select)
  app.router.add_post("/api/opui/models/accelerator", api_models_accelerator)
  app.router.add_post("/api/opui/models/favorite", api_models_favorite)
  app.router.add_post("/api/opui/models/mirror", api_models_mirror)
  app.router.add_get("/api/opui/tokens", api_tokens)
  app.router.add_get("/api/opui/assets/{path:.*}", api_asset)
  app.router.add_get("/api/opui/model/overlay", api_model_overlay)
  app.router.add_get("/api/opui/ssh/status", api_ssh_status)
  app.router.add_post("/api/opui/ssh/fetch", api_ssh_fetch)
  app.router.add_post("/api/opui/ssh/remove", api_ssh_remove)
  app.router.add_get("/api/opui/osm/regions", api_osm_regions)
  app.router.add_post("/api/opui/osm/select", api_osm_select)
  app.router.add_post("/api/opui/osm/clear", api_osm_clear)
  app.router.add_get("/api/opui/osm/size", api_osm_size)
  app.router.add_get("/api/opui/osm/progress", api_osm_progress)
  app.router.add_post("/api/opui/osm/delete", api_osm_delete)
  app.router.add_get("/api/opui/vehicle/platforms", api_vehicle_platforms)
  app.router.add_get("/api/opui/vehicle/brand-widgets", api_vehicle_brand_widgets)
  app.router.add_post("/api/opui/vehicle/select", api_vehicle_select)
  app.router.add_get("/api/opui/sunnylink/status", api_sunnylink_status)
  app.router.add_get("/api/opui/sunnylink/pair", api_sunnylink_pair)
  app.router.add_get("/api/opui/firehose", api_firehose)
  app.router.add_get("/api/opui/storage", api_storage)
  app.router.add_post("/api/opui/storage/clear", api_storage_clear)
  app.router.add_get("/api/opui/stream/health", api_stream_health)
  app.router.add_get("/api/opui/device/extras", api_device_extras)
  app.router.add_get("/api/opui/device/pair", api_device_pair)
  app.router.add_get("/api/opui/device/driver_view", api_driver_view_status)
  app.router.add_post("/api/opui/device/driver_view", api_driver_view_set)
  app.router.add_get("/api/opui/steering/torque-versions", api_torque_versions)
  app.router.add_get("/api/opui/device/regulatory", api_device_regulatory)
  app.router.add_get("/api/opui/developer/error-log", api_developer_error_log)
  app.router.add_post("/api/opui/device/language", api_set_language)
  app.router.add_get("/api/opui/imu/calibration", api_imu_calibration)
  app.router.add_post("/api/opui/imu/calibration/{action}", api_imu_calibration_control)
  app.router.add_post("/api/opui/imu/calibration/enabled", api_imu_calibration_enabled)
  app.router.add_get("/api/opui/webui-update", api_webui_update)
  app.router.add_post("/api/opui/webui-update/dismiss", api_webui_update_dismiss)
  app.router.add_post("/api/opui/webui-update/apply", api_webui_update_apply)
  app.router.add_get("/api/opui/agnos", api_agnos)
  app.router.add_get("/api/opui/carrot/crossroad", api_carrot_crossroad)
  app.router.add_get("/api/opui/carrot/navi_debug", api_carrot_navi_debug)
  app.router.add_get("/api/opui/carrot/media", api_carrot_media)
  # Carrot settings: backup / restore / profiles / favorites
  app.router.add_get("/api/opui/carrot/settings/backup", api_carrot_settings_backup)
  app.router.add_get("/api/opui/carrot/settings/backup/qr", api_carrot_settings_backup_qr)
  app.router.add_post("/api/opui/carrot/settings/restore", api_carrot_settings_restore)
  app.router.add_get("/api/opui/carrot/settings/profiles", api_carrot_profiles)
  app.router.add_post("/api/opui/carrot/settings/profiles", api_carrot_profile_create)
  app.router.add_put("/api/opui/carrot/settings/profiles/{profile_id}", api_carrot_profile_update)
  app.router.add_delete("/api/opui/carrot/settings/profiles/{profile_id}", api_carrot_profile_delete)
  app.router.add_post("/api/opui/carrot/settings/profiles/{profile_id}/preview", api_carrot_profile_preview)
  app.router.add_post("/api/opui/carrot/settings/profiles/{profile_id}/apply", api_carrot_profile_apply)
  app.router.add_get("/api/opui/carrot/settings/favorites", api_carrot_favorites)
  app.router.add_post("/api/opui/carrot/settings/favorites", api_carrot_favorites_update)
  # Carrot settings: param change history + fingerprint
  app.router.add_get("/api/opui/carrot/settings/param_changes", api_carrot_param_changes)
  app.router.add_get("/api/opui/carrot/settings/param_changes/verify", api_carrot_param_changes_verify)
  app.router.add_get("/api/opui/carrot/settings/param_fingerprint", api_carrot_param_fingerprint)
  app.router.add_post("/api/opui/carrot/settings/param_fingerprint/baseline", api_carrot_param_fingerprint_baseline)
  # Bluetooth HID remote setup
  app.router.add_get("/api/opui/bluetooth", api_bluetooth_status)
  app.router.add_post("/api/opui/bluetooth/{operation}", api_bluetooth_mutate)
  app.router.add_post("/api/opui/agnos/install", api_agnos_install)
  app.router.add_post("/api/opui/agnos/reboot", api_agnos_reboot)
  app.router.add_get("/api/opui/webrtc/schema", api_webrtc_schema)
  app.router.add_post("/api/opui/webrtc/offer", api_webrtc_offer)
  app.router.add_post("/api/opui/webrtc/notify", api_webrtc_notify)
  app.router.add_get("/api/opui/jetlink/status", api_jetlink_status)
  app.router.add_get("/ws/opui", ws_opui_handler)

  # Legacy alias
  async def api_toggles_legacy(_request: web.Request) -> web.Response:
    return json_response(panel_values("toggles"))

  app.router.add_get("/api/opui/params/toggles", api_toggles_legacy)

  app.router.add_static("/static/", path=str(WEB_DIR), name="static")

  async def _disable_static_cache(_request: web.Request, response: web.StreamResponse) -> None:
    path = _request.path
    if path == "/" or path.startswith("/static/"):
      response.headers.setdefault("Cache-Control", "no-cache, no-store, must-revalidate")
      response.headers.setdefault("Pragma", "no-cache")
      response.headers.setdefault("Expires", "0")
  app.on_response_prepare.append(_disable_static_cache)

  async def index(_request: web.Request) -> web.FileResponse:
    return web.FileResponse(WEB_DIR / "index.html")

  app.router.add_get("/", index)

  from webui.server.routes.dev import register_dev_routes
  register_dev_routes(app)
