"""WebSocket RPC — mirrors REST /api/opui/* for WS-only clients."""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from webui.server.bridge.design_tokens import tokens_payload
from webui.server.bridge.developer_api import developer_error_log
from webui.server.bridge.device_api import device_extras, device_pair_url, regulatory_html, set_language
from webui.server.bridge.steering_api import torque_versions
from webui.server.bridge.firehose_api import firehose_status
from webui.server.bridge.storage_api import clear_storage, snapshot_storage
from webui.server.bridge.home_api import snapshot_home
from webui.server.bridge.i18n_api import snapshot_i18n
from webui.server.bridge.model_overlay import snapshot_model_overlay
from webui.server.bridge.models_api import models_select, models_status, models_toggle_favorite
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
from webui.server.bridge.osm_api import (
  osm_delete_maps,
  osm_download_progress,
  osm_fetch_regions,
  osm_map_size_mb,
  osm_panel_custom,
  osm_regions,
  osm_select_region,
)
from webui.server.bridge.params_api import batch_get, get_param, panel_schema, panel_values, put_param
from webui.server.bridge.brightness_api import apply_brightness, snapshot_brightness
from webui.server.bridge.ssh_api import ssh_fetch_keys, ssh_remove_keys, ssh_status
from webui.server.bridge.state_hub import get_home, get_state
from webui.server.bridge.sunnylink_api import sunnylink_pair_url, sunnylink_status
from webui.server.bridge.system_api import manager_last_error, run_action, software_status
from webui.server.bridge.trips_api import trips_stats
from webui.server.bridge.vehicle_api import vehicle_brand_widgets, vehicle_platforms, vehicle_select
from webui.server.bridge.webrtc_api import webrtc_notify, webrtc_offer, webrtc_schema
from webui.server.bridge.webui_update_api import apply_webui_update, dismiss_webui_update, snapshot_webui_update
from webui.server.deps import openpilot_root, read_version

_PANEL_GET = re.compile(r"^/api/opui/panels/([^/]+)$")
_PARAM_GET = re.compile(r"^/api/opui/params/([^/]+)$")
_ACTION_POST = re.compile(r"^/api/opui/action/([^/]+)$")
_DEV_PRESET = re.compile(r"^/api/opui/dev/preset/([^/]+)$")


def bootstrap_payload() -> dict[str, Any]:
  from webui.server.bridge.headless_util import (
    get_headless_mode_pref,
    has_builtin_display_hardware,
    is_headless_mode,
  )
  from webui.server.bridge.state_hub import get_home, get_state, home_ready, home_seq, state_ready, state_seq

  headless = is_headless_mode()
  has_display = has_builtin_display_hardware()
  payload = {
    "ok": True,
    "name": "op-webui",
    "version": read_version(),
    "openpilot_root": str(openpilot_root()),
    "dev_pc": os.environ.get("WEBUI_DEV_PC") == "1",
    "headless": headless,
    "headless_mode": get_headless_mode_pref(),
    "has_builtin_display": has_display,
    "can_turn_off_headless": has_display,
    "recommended_overlay_fps": 5 if headless else 10,
    "design": {"width": 2160, "height": 1080, "variant": "BIG"},
    "webrtc": {"port": 5001},
    "state_seq": state_seq(),
    "home_seq": home_seq(),
    **tokens_payload(),
  }
  if state_ready():
    payload["state"] = get_state()
  if home_ready():
    payload["home"] = get_home()
  if payload["dev_pc"]:
    schema = panel_schema()
    if schema.get("ok"):
      payload["panels_schema"] = schema
  return payload


def custom_panel_data(panel_id: str) -> dict[str, Any] | None:
  if panel_id == "software":
    return software_status()
  if panel_id == "firehose":
    return firehose_status()
  if panel_id == "storage":
    return snapshot_storage()
  if panel_id == "sunnylink":
    return sunnylink_status()
  if panel_id == "trips":
    return trips_stats()
  if panel_id == "models":
    return models_status()
  if panel_id == "osm":
    return osm_panel_custom()
  if panel_id == "network":
    return {"ok": True, "wifi": wifi_status()}
  if panel_id == "vehicle":
    return {
      "ok": True,
      "platforms": vehicle_platforms(),
      "brand_widgets": vehicle_brand_widgets(),
    }
  return None


def dispatch_http(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
  body = body or {}
  parsed = urlparse(path)
  clean_path = parsed.path
  query = {k: v[0] for k, v in parse_qs(parsed.query).items() if v}

  try:
    if method == "GET" and clean_path == "/api/opui/bootstrap":
      return bootstrap_payload()

    if method == "GET" and clean_path == "/api/opui/state":
      return get_state()

    if method == "GET" and clean_path == "/api/opui/home":
      return get_home()

    if method == "GET" and clean_path == "/api/opui/i18n":
      return snapshot_i18n()

    if method == "GET" and clean_path == "/api/opui/headless-mode":
      from webui.server.bridge.headless_api import snapshot_headless_mode
      return snapshot_headless_mode()

    if method == "PUT" and clean_path == "/api/opui/headless-mode":
      from webui.server.bridge.headless_api import apply_headless_mode
      return apply_headless_mode(str(body.get("mode", "")))

    if method == "GET" and clean_path == "/api/opui/panels":
      return panel_schema()

    m = _PANEL_GET.match(clean_path)
    if method == "GET" and m:
      return panel_values(m.group(1))

    m = _PARAM_GET.match(clean_path)
    if method == "GET" and m:
      return get_param(m.group(1))

    if method == "PUT" and (m := _PARAM_GET.match(clean_path)):
      return put_param(
        m.group(1),
        str(body.get("value", "")),
        needs_cycle=bool(body.get("needs_cycle", False)),
      )

    if method == "POST" and clean_path == "/api/opui/params/batch":
      return batch_get(body.get("keys", []))

    if method == "GET" and clean_path == "/api/opui/display/brightness":
      return snapshot_brightness()

    if method == "PUT" and clean_path == "/api/opui/display/brightness":
      return apply_brightness(body.get("brightness", body.get("value", 0)))

    m = _ACTION_POST.match(clean_path)
    if method == "POST" and m:
      return run_action(m.group(1), body)

    if method == "GET" and clean_path == "/api/opui/software":
      return software_status()

    if method == "GET" and clean_path == "/api/opui/agnos":
      from webui.server.bridge.agnos_api import agnos_snapshot
      return agnos_snapshot()

    if method == "POST" and clean_path == "/api/opui/agnos/install":
      from webui.server.bridge.agnos_api import start_agnos_install
      return start_agnos_install()

    if method == "POST" and clean_path == "/api/opui/agnos/reboot":
      from webui.server.bridge.agnos_api import agnos_reboot
      return agnos_reboot()

    if method == "GET" and clean_path == "/api/opui/system/manager_error":
      return manager_last_error()

    if method == "GET" and clean_path == "/api/opui/wifi/status":
      return wifi_status()

    if method == "GET" and clean_path == "/api/opui/wifi/scan":
      trigger = query.get("trigger", "").lower() in ("1", "true", "yes")
      return wifi_scan(trigger=trigger)

    if method == "GET" and clean_path == "/api/opui/network/advanced":
      return network_advanced_status()

    if method == "POST" and clean_path == "/api/opui/wifi/tethering":
      return wifi_set_tethering(bool(body.get("active", False)))

    if method == "POST" and clean_path == "/api/opui/wifi/tethering/password":
      return wifi_set_tethering_password(str(body.get("password", "")))

    if method == "POST" and clean_path == "/api/opui/wifi/metered":
      return wifi_set_metered(int(body.get("metered", 0)))

    if method == "POST" and clean_path == "/api/opui/wifi/connect/hidden":
      return wifi_connect_hidden(str(body.get("ssid", "")), str(body.get("password", "")))

    if method == "POST" and clean_path == "/api/opui/wifi/connect":
      return wifi_connect(str(body.get("ssid", "")), str(body.get("password", "")))

    if method == "POST" and clean_path == "/api/opui/wifi/forget":
      return wifi_forget(str(body.get("ssid", "")))

    if method == "GET" and clean_path == "/api/opui/trips":
      return trips_stats()

    if method == "GET" and clean_path == "/api/opui/models":
      return models_status()

    if method == "POST" and clean_path == "/api/opui/models/select":
      index = body.get("index")
      return models_select(str(body.get("ref", "")), int(index) if index is not None else None)

    if method == "POST" and clean_path == "/api/opui/models/favorite":
      return models_toggle_favorite(str(body.get("ref", "")))

    if method == "GET" and clean_path == "/api/opui/tokens":
      return {"ok": True, **tokens_payload()}

    if method == "GET" and clean_path == "/api/opui/model/overlay":
      w = int(query.get("w", body.get("w", 1600)))
      h = int(query.get("h", body.get("h", 900)))
      return snapshot_model_overlay(w, h)

    if method == "GET" and clean_path == "/api/opui/ssh/status":
      return ssh_status()

    if method == "POST" and clean_path == "/api/opui/ssh/fetch":
      return ssh_fetch_keys(str(body.get("username", "")))

    if method == "POST" and clean_path == "/api/opui/ssh/remove":
      return ssh_remove_keys()

    if method == "GET" and clean_path == "/api/opui/osm/regions":
      q = parse_qs(parsed.query)
      region_type = (q.get("type") or ["Country"])[0]
      return osm_fetch_regions(region_type)

    if method == "POST" and clean_path == "/api/opui/osm/select":
      return osm_select_region(
        str(body.get("country", "")),
        str(body.get("country_title", "")),
        str(body.get("state", "")),
        str(body.get("state_title", "")),
      )

    if method == "GET" and clean_path == "/api/opui/osm/size":
      return osm_map_size_mb()

    if method == "GET" and clean_path == "/api/opui/osm/progress":
      return osm_download_progress()

    if method == "POST" and clean_path == "/api/opui/osm/delete":
      return osm_delete_maps()

    if method == "GET" and clean_path == "/api/opui/vehicle/platforms":
      return vehicle_platforms()

    if method == "GET" and clean_path == "/api/opui/vehicle/brand-widgets":
      return vehicle_brand_widgets()

    if method == "POST" and clean_path == "/api/opui/vehicle/select":
      return vehicle_select(str(body.get("bundle", "")))

    if method == "GET" and clean_path == "/api/opui/sunnylink/status":
      return sunnylink_status()

    if method == "GET" and clean_path == "/api/opui/sunnylink/pair":
      return sunnylink_pair_url()

    if method == "GET" and clean_path == "/api/opui/firehose":
      return firehose_status()

    if method == "GET" and clean_path == "/api/opui/storage":
      force = query.get("force") == "1"
      return snapshot_storage(force=force)

    if method == "POST" and clean_path == "/api/opui/storage/clear":
      category = str(body.get("category", "")).strip()
      if not category:
        return {"ok": False, "error": "category required"}
      return clear_storage(category)

    if method == "GET" and clean_path == "/api/opui/device/extras":
      return device_extras()

    if method == "GET" and clean_path == "/api/opui/device/pair":
      return device_pair_url()

    if method == "GET" and clean_path == "/api/opui/stream/health":
      from webui.server.bridge.stream_health_api import snapshot_stream_health
      return snapshot_stream_health()

    if method == "GET" and clean_path == "/api/opui/steering/torque-versions":
      return torque_versions()

    if method == "GET" and clean_path == "/api/opui/device/regulatory":
      return regulatory_html()

    if method == "GET" and clean_path == "/api/opui/developer/error-log":
      return developer_error_log()

    if method == "POST" and clean_path == "/api/opui/device/language":
      return set_language(str(body.get("language", "")))

    if method == "GET" and clean_path == "/api/opui/webui-update":
      fetch_remote = query.get("fetch", "").lower() in ("1", "true", "yes")
      return snapshot_webui_update(fetch=fetch_remote)

    if method == "POST" and clean_path == "/api/opui/webui-update/dismiss":
      return dismiss_webui_update(str(body.get("commit", "") or "") or None)

    if method == "POST" and clean_path == "/api/opui/webui-update/apply":
      return apply_webui_update()

    if method == "GET" and clean_path == "/api/opui/webrtc/schema":
      return webrtc_schema()

    if method == "POST" and clean_path == "/api/opui/webrtc/offer":
      return webrtc_offer(str(body.get("sdp", "")), str(body.get("init_camera", "road")))
    if method == "POST" and clean_path == "/api/opui/webrtc/notify":
      return webrtc_notify(body if isinstance(body, dict) else {})

    if method == "GET" and clean_path == "/api/opui/params/toggles":
      return panel_values("toggles")

    if os.environ.get("WEBUI_DEV_PC") == "1":
      if method == "GET" and clean_path == "/api/opui/dev/simulation":
        from webui.dev.mock_runtime import SIM
        return {"ok": True, "simulation": dict(SIM)}
      if method == "POST" and clean_path == "/api/opui/dev/simulation":
        from webui.dev.mock_runtime import SIM
        for k, v in body.items():
          if k in SIM:
            SIM[k] = v
        if SIM.get("started") and SIM.get("ui_status") == "engaged":
          SIM["engaged"] = True
        elif SIM.get("ui_status") == "disengaged":
          SIM["engaged"] = False
        return {"ok": True, "simulation": dict(SIM)}
      m = _DEV_PRESET.match(clean_path)
      if method == "POST" and m:
        from webui.server.routes.dev import api_dev_presets
        # inline preset logic
        from webui.dev.mock_runtime import SIM
        preset = m.group(1)
        presets = {
          "home": {"started": False, "engaged": False, "ui_status": "disengaged", "alert_text1": "", "alert_text2": ""},
          "onroad_engaged": {"started": True, "engaged": True, "ui_status": "engaged", "speed_kmh": 88},
          "onroad_disengaged": {"started": True, "engaged": False, "ui_status": "disengaged", "speed_kmh": 45},
          "override": {"started": True, "engaged": True, "ui_status": "override", "speed_kmh": 100},
          "lat_only": {"started": True, "engaged": True, "ui_status": "lat_only", "speed_kmh": 60},
          "alert_critical": {
            "started": True, "engaged": False, "ui_status": "disengaged", "speed_kmh": 0,
            "alert_text1": "Brake!", "alert_text2": "Take control immediately", "alert_status": "critical",
          },
        }
        if preset not in presets:
          return {"ok": False, "error": f"unknown preset: {preset}"}
        SIM.update(presets[preset])
        return {"ok": True, "preset": preset, "simulation": dict(SIM)}

    return {"ok": False, "error": f"unsupported rpc: {method} {clean_path}"}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}
