"""Background Prime / Sunnylink refresh for headless WebUI (no native ui process)."""

from __future__ import annotations

import json
import threading
import time
from typing import Any

_running = False
_thread: threading.Thread | None = None
_ws_clients = 0
_ws_clients_lock = threading.Lock()
_sunnylink_watchers = 0
_sunnylink_lock = threading.Lock()
_last_sunnylink_refresh = 0.0
SUNNYLINK_REFRESH_INTERVAL = 5.0


def sunnylink_panel_watch(delta: int) -> None:
  """Track WebUI clients viewing the sunnylink settings panel."""
  global _sunnylink_watchers
  with _sunnylink_lock:
    prev = _sunnylink_watchers > 0
    _sunnylink_watchers = max(0, _sunnylink_watchers + int(delta))
    now = _sunnylink_watchers > 0
  if now and not prev:
    maybe_refresh_sunnylink_cache(force=True)


def is_sunnylink_panel_watched() -> bool:
  with _sunnylink_lock:
    return _sunnylink_watchers > 0


def _refresh_sunnylink_once() -> None:
  try:
    from openpilot.common.params import Params
    from openpilot.sunnypilot.sunnylink.api import UNREGISTERED_SUNNYLINK_DONGLE_ID, SunnylinkApi

    params = Params()
    if not params.get_bool("SunnylinkEnabled"):
      return
    _refresh_sunnylink_cache(params, SunnylinkApi, UNREGISTERED_SUNNYLINK_DONGLE_ID)
  except Exception:
    pass


def maybe_refresh_sunnylink_cache(force: bool = False) -> None:
  """Refresh Sunnylink role cache when the settings panel is open (any display mode)."""
  if not is_sunnylink_panel_watched():
    return
  global _last_sunnylink_refresh
  now = time.monotonic()
  if not force and (now - _last_sunnylink_refresh) < SUNNYLINK_REFRESH_INTERVAL:
    return
  _last_sunnylink_refresh = now
  threading.Thread(target=_refresh_sunnylink_once, name="sunnylink-refresh", daemon=True).start()


def note_ws_client_connected() -> None:
  global _ws_clients
  with _ws_clients_lock:
    _ws_clients += 1
    should_start = _ws_clients == 1
  if should_start:
    start_webui_bg_services()


def note_ws_client_disconnected() -> None:
  global _ws_clients
  with _ws_clients_lock:
    _ws_clients = max(0, _ws_clients - 1)
    should_stop = _ws_clients == 0
  if should_stop:
    stop_webui_bg_services()


def start_webui_bg_services() -> None:
  global _running, _thread
  if _running:
    return
  _running = True
  _thread = threading.Thread(target=_worker, name="webui-bg-services", daemon=True)
  _thread.start()
  threading.Thread(target=_refresh_sunnylink_once, name="sunnylink-refresh", daemon=True).start()


def stop_webui_bg_services() -> None:
  global _running
  _running = False


def _worker() -> None:
  try:
    from openpilot.common.realtime import drop_realtime
    drop_realtime()
  except Exception:
    pass

  prime_interval = 5.0
  sunny_interval = 5.0
  last_prime = 0.0
  last_sunny = 0.0

  try:
    import openpilot.cereal.messaging as messaging
    from openpilot.common.params import Params
    from openpilot.selfdrive.ui.lib.prime_state import PrimeState
    from openpilot.sunnypilot.sunnylink.api import UNREGISTERED_SUNNYLINK_DONGLE_ID, SunnylinkApi

    sm = messaging.SubMaster(["deviceState"], poll="deviceState")
    prime = PrimeState()
    params = Params()
  except Exception:
    return

  while _running:
    try:
      from webui.server.bridge.ws_handler import ws_connection_count
      has_clients = ws_connection_count() > 0
    except Exception:
      has_clients = True

    if not has_clients:
      time.sleep(1.0)
      continue

    try:
      sm.update(500)
      started = bool(sm.valid.get("deviceState") and sm["deviceState"].started)
      now = time.monotonic()

      if not started and (now - last_prime) >= prime_interval:
        prime._fetch_prime_status()
        last_prime = now

      if (
        (now - last_sunny) >= sunny_interval
        and params.get_bool("SunnylinkEnabled")
        and is_sunnylink_panel_watched()
      ):
        _refresh_sunnylink_cache(params, SunnylinkApi, UNREGISTERED_SUNNYLINK_DONGLE_ID)
        last_sunny = now
    except Exception:
      pass
    time.sleep(0.5)


def _refresh_sunnylink_cache(params, SunnylinkApi, unregistered_id: str) -> None:
  sl_dongle = params.get("SunnylinkDongleId") or unregistered_id
  if not sl_dongle or sl_dongle == unregistered_id:
    return
  try:
    api = SunnylinkApi(sl_dongle)
    token = api.get_token()
    session = __import__("requests").Session()
    for path, key in (("roles", "SunnylinkCache_Roles"), ("users", "SunnylinkCache_Users")):
      resp = api.api_get(f"device/{sl_dongle}/{path}", method="GET", access_token=token, session=session)
      if resp.status_code == 200:
        params.put(key, resp.text, block=False)
  except Exception:
    pass


def sunnylink_tier_from_params() -> dict[str, Any]:
  """Parse sponsor tier / pairing from Params cache (no pyray / ui_state)."""
  out = {
    "tier": "",
    "tier_color": "#808080",
    "is_sponsor": False,
    "is_paired": False,
    "description": "",
  }
  try:
    from openpilot.common.params import Params

    p = Params()
    roles_raw = p.get("SunnylinkCache_Roles") or "[]"
    users_raw = p.get("SunnylinkCache_Users") or "[]"
    roles = json.loads(roles_raw) if isinstance(roles_raw, str) else []
    users = json.loads(users_raw) if isinstance(users_raw, str) else []

    tier_rank = {
      "FREE": 0, "NOVICE": 1, "SUPPORTER": 2, "CONTRIBUTOR": 3, "BENEFACTOR": 4, "GUARDIAN": 5,
    }
    tier_colors = {
      "GUARDIAN": "#FFD500",
      "BENEFACTOR": "#3CB371",
      "CONTRIBUTOR": "#4682B4",
      "SUPPORTOR": "#9370DB",
    }
    best_tier = "FREE"
    is_sponsor = False
    for role in roles:
      if not isinstance(role, dict):
        continue
      role_type = str(role.get("role_type", "")).upper()
      role_tier = str(role.get("role_tier", "FREE")).upper()
      if role_type == "SPONSOR" and role_tier != "FREE":
        is_sponsor = True
        if tier_rank.get(role_tier, 0) > tier_rank.get(best_tier, 0):
          best_tier = role_tier

    not_paired = {"unregisteredsponsor", "temporarysponsor"}
    is_paired = any(
      isinstance(u, dict) and str(u.get("user_id", "")).lower() not in not_paired
      for u in users
    )

    tier_name = best_tier.capitalize() if best_tier != "FREE" else ""
    out["tier"] = tier_name
    out["is_sponsor"] = is_sponsor or bool(tier_name)
    out["is_paired"] = is_paired
    out["tier_color"] = tier_colors.get(best_tier, "#808080") if is_sponsor else "#808080"
    out["description"] = "Paired" if is_paired else "Not paired"
  except Exception:
    pass
  return out


def prime_status_from_cache() -> dict[str, bool]:
  try:
    from openpilot.common.params import Params
    from openpilot.selfdrive.ui.lib.prime_state import PrimeType
    from openpilot.system.athena.registration import UNREGISTERED_DONGLE_ID

    p = Params()
    dongle = p.get("DongleId") or ""
    paired = bool(dongle) and dongle not in ("", UNREGISTERED_DONGLE_ID)
    try:
      prime_type = PrimeType(int(p.get("PrimeType") or PrimeType.UNKNOWN))
    except (ValueError, TypeError):
      prime_type = PrimeType.UNKNOWN
    return {
      "paired": prime_type > PrimeType.UNPAIRED or paired,
      "prime": prime_type > PrimeType.NONE,
    }
  except Exception:
    return {"paired": False, "prime": False}
