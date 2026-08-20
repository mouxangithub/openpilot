"""Route registration."""

from __future__ import annotations

import asyncio
import json
import os

from aiohttp import web

from webui.server.deps import WEB_DIR, json_response, openpilot_root, read_version
from webui.server.bridge.params_api import batch_get, get_param, panel_schema, panel_values, put_param, remove_param
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
from webui.server.bridge.models_api import models_select, models_status
from webui.server.bridge.design_tokens import tokens_payload
from webui.server.bridge.assets_api import resolve_asset
from webui.server.bridge.stream_health_api import snapshot_stream_health
from webui.server.bridge.model_overlay import snapshot_model_overlay
from webui.server.bridge.ssh_api import ssh_fetch_keys, ssh_remove_keys, ssh_status
from webui.server.bridge.osm_api import osm_download_progress, osm_fetch_regions, osm_map_size_mb, osm_select_region, osm_clear_incomplete_us
from webui.server.bridge.vehicle_api import vehicle_platforms, vehicle_select, vehicle_brand_widgets
from webui.server.bridge.sunnylink_api import sunnylink_pair_url, sunnylink_status
from webui.server.bridge.firehose_api import firehose_status
from webui.server.bridge.storage_api import clear_storage, snapshot_storage
from webui.server.bridge.device_api import device_extras, device_pair_url, driver_view_status, regulatory_html, set_driver_view, set_language
from webui.server.bridge.steering_api import torque_versions
from webui.server.bridge.home_api import snapshot_home
from webui.server.bridge.onboarding_api import accept_sunnylink_consent, accept_terms, complete_training, onboarding_status
from webui.server.bridge.i18n_api import snapshot_i18n
from webui.server.bridge.webui_update_api import apply_webui_update, dismiss_webui_update, snapshot_webui_update
from webui.server.bridge.developer_api import developer_error_log
from webui.server.bridge.osm_api import osm_delete_maps
from webui.server.bridge.ws_handler import ws_opui_handler


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
  key = request.match_info.get("key", "")
  try:
    body = await request.json()
    value = str(body.get("value", ""))
    needs_cycle = bool(body.get("needs_cycle", False))
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  return json_response(await asyncio.to_thread(put_param, key, value, needs_cycle=needs_cycle))


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


async def api_trips(_request: web.Request) -> web.Response:
  return json_response(trips_stats())


async def api_models(_request: web.Request) -> web.Response:
  return json_response(models_status())


async def api_models_select(request: web.Request) -> web.Response:
  try:
    body = await request.json()
    ref = str(body.get("ref", ""))
    index = body.get("index")
    if index is not None:
      index = int(index)
  except Exception:
    return json_response({"ok": False, "error": "invalid json"}, status=400)
  return json_response(models_select(ref, index))


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
  return json_response(osm_fetch_regions(region_type))


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
  return json_response(osm_clear_incomplete_us())


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
  app.router.add_get("/api/opui/params/{key}", api_param_get)
  app.router.add_put("/api/opui/params/{key}", api_param_put)
  app.router.add_delete("/api/opui/params/{key}", api_param_delete)
  app.router.add_post("/api/opui/params/batch", api_params_batch)
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
  app.router.add_get("/api/opui/webui-update", api_webui_update)
  app.router.add_post("/api/opui/webui-update/dismiss", api_webui_update_dismiss)
  app.router.add_post("/api/opui/webui-update/apply", api_webui_update_apply)
  app.router.add_get("/api/opui/agnos", api_agnos)
  app.router.add_post("/api/opui/agnos/install", api_agnos_install)
  app.router.add_post("/api/opui/agnos/reboot", api_agnos_reboot)
  app.router.add_get("/api/opui/webrtc/schema", api_webrtc_schema)
  app.router.add_post("/api/opui/webrtc/offer", api_webrtc_offer)
  app.router.add_post("/api/opui/webrtc/notify", api_webrtc_notify)
  app.router.add_get("/ws/opui", ws_opui_handler)

  # Legacy alias
  async def api_toggles_legacy(_request: web.Request) -> web.Response:
    return json_response(panel_values("toggles"))

  app.router.add_get("/api/opui/params/toggles", api_toggles_legacy)

  app.router.add_static("/static/", path=str(WEB_DIR), name="static")

  async def index(_request: web.Request) -> web.FileResponse:
    return web.FileResponse(WEB_DIR / "index.html")

  app.router.add_get("/", index)
