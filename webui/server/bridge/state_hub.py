"""Persistent cereal reader + cached UI state for HTTP and WebSocket."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

from webui.server.bridge.cereal_services import STATE_HUB_SERVICES, filter_known_services, make_submaster
from webui.server.bridge.home_api import refresh_home_slow_cache, snapshot_home, snapshot_home_core
from webui.server.bridge.state_api import build_state_from_sm
from webui.server.bridge.car_context import refresh_car_context
from webui.server.bridge.startup_blockers import set_startup_gate_cache, startup_blockers_from_sm

_lock = threading.Lock()
_sm_lock = threading.Lock()
_state: dict[str, Any] | None = None
_home: dict[str, Any] | None = None
_shared_sm: Any = None
_state_seq = 0
_home_seq = 0
_cached_state_json: dict[int, str] = {}
_cached_home_json: dict[int, str] = {}
_running = False
_thread: threading.Thread | None = None


def start_state_hub() -> None:
  global _running, _thread
  if _running:
    return
  try:
    from webui.server.bridge.headless_util import is_headless_mode
    headless = is_headless_mode()
    refresh_home_slow_cache(headless=headless)
    if headless:
      from webui.server.bridge.webui_bg_services import start_webui_bg_services
      start_webui_bg_services()
  except Exception:
    pass
  try:
    _set_home(snapshot_home())
  except Exception:
    pass
  _running = True
  _thread = threading.Thread(target=_run_loop, name="webui-state-hub", daemon=True)
  _thread.start()


def stop_state_hub() -> None:
  global _running
  _running = False


def get_device_thermal() -> str:
  with _lock:
    if _state is not None:
      return str(_state.get("device", {}).get("thermal", "ok")).lower()
  return "ok"


def get_state_json(seq: int | None = None) -> str | None:
  with _lock:
    if _state is None:
      return None
    s = _state_seq if seq is None else seq
    cached = _cached_state_json.get(s)
    if cached is not None:
      return cached
    payload = json.dumps({"type": "state", "seq": s, "data": _state}, separators=(",", ":"), default=str)
    _cached_state_json.clear()
    _cached_state_json[s] = payload
    return payload


def get_home_json(seq: int | None = None) -> str | None:
  with _lock:
    if _home is None:
      return None
    s = _home_seq if seq is None else seq
    cached = _cached_home_json.get(s)
    if cached is not None:
      return cached
    payload = json.dumps({"type": "home", "seq": s, "data": _home}, separators=(",", ":"), default=str)
    _cached_home_json.clear()
    _cached_home_json[s] = payload
    return payload


def state_ready() -> bool:
  with _lock:
    return _state is not None


def home_ready() -> bool:
  with _lock:
    return _home is not None


def get_started() -> bool | None:
  with _lock:
    if _state is None:
      return None
    return bool(_state.get("started"))


def get_state() -> dict[str, Any]:
  with _lock:
    if _state is not None:
      return dict(_state)
  if os.environ.get("WEBUI_DEV_PC") == "1":
    from webui.dev.mock_runtime import snapshot_dev_ui_state
    return snapshot_dev_ui_state()
  return {
    "ok": False,
    "error": "state_not_ready",
    "started": False,
    "engaged": False,
    "ui_status": "disengaged",
  }


def get_home() -> dict[str, Any]:
  with _lock:
    if _home is not None:
      return dict(_home)
  return snapshot_home()


def get_startup_gate() -> dict[str, Any]:
  from webui.server.bridge.startup_blockers import get_startup_gate as _gate
  return _gate()


def state_seq() -> int:
  with _lock:
    return _state_seq


def home_seq() -> int:
  with _lock:
    return _home_seq


def get_shared_sm() -> Any:
  """Latest SubMaster from the state hub thread (read-only; do not call update)."""
  with _sm_lock:
    return _shared_sm


def _publish_shared_sm(sm: Any) -> None:
  global _shared_sm
  with _sm_lock:
    _shared_sm = sm


def _update_shared_sm(sm: Any) -> None:
  """Update cereal reader and publish under one lock (readers see consistent frames)."""
  global _shared_sm
  with _sm_lock:
    sm.update(100)
    _shared_sm = sm


def refresh_dev_state() -> None:
  """PC dev only — push mock state immediately after simulation changes."""
  if os.environ.get("WEBUI_DEV_PC") != "1":
    return
  from webui.dev.mock_runtime import snapshot_dev_ui_state
  _set_state(snapshot_dev_ui_state())


def _set_state(st: dict[str, Any]) -> None:
  global _state, _state_seq
  with _lock:
    _state = st
    _state_seq += 1
    _cached_state_json.clear()


def _set_home(home: dict[str, Any]) -> None:
  global _home, _home_seq
  with _lock:
    _home = home
    _home_seq += 1
    _cached_home_json.clear()


def _cold_state_snapshot() -> dict[str, Any]:
  if os.environ.get("WEBUI_DEV_PC") == "1":
    from webui.dev.mock_runtime import snapshot_dev_ui_state
    return snapshot_dev_ui_state()
  try:
    sm = make_submaster(list(STATE_HUB_SERVICES))
    sm.update(300)
    started = bool(sm.valid.get("deviceState") and sm["deviceState"].started)
    refresh_car_context(sm, started)
    return build_state_from_sm(sm)
  except Exception as exc:
    return {
      "ok": False,
      "error": str(exc),
      "started": False,
      "engaged": False,
      "ui_status": "disengaged",
    }


def _run_loop() -> None:
  if os.environ.get("WEBUI_DEV_PC") == "1":
    _dev_loop()
    return
  _device_loop()


def _dev_loop() -> None:
  from webui.dev.mock_runtime import snapshot_dev_ui_state

  home_ticks = 0
  home_slow_ticks = 0
  home_interval = 50
  home_slow_interval = 300
  while _running:
    _set_state(snapshot_dev_ui_state())
    home_ticks += 1
    home_slow_ticks += 1
    if home_ticks >= home_interval:
      if home_slow_ticks >= home_slow_interval:
        refresh_home_slow_cache(headless=False)
        home_slow_ticks = 0
      _set_home(snapshot_home_core())
      home_ticks = 0
    time.sleep(0.1)


def _device_loop() -> None:
  try:
    from webui.server.bridge.headless_util import is_headless_mode
    headless = is_headless_mode()
  except Exception:
    headless = False
  home_interval = 50 if headless else 25

  services = filter_known_services(list(STATE_HUB_SERVICES))
  try:
    sm = make_submaster(services)
  except Exception as exc:
    _set_state({
      "ok": False,
      "error": str(exc),
      "started": False,
      "engaged": False,
      "ui_status": "disengaged",
    })
    return
  _publish_shared_sm(sm)
  home_ticks = 0
  home_slow_ticks = 0
  home_slow_interval = 300
  started = False
  while _running:
    try:
      _update_shared_sm(sm)
      started = bool(sm.valid.get("deviceState") and sm["deviceState"].started)
      refresh_car_context(sm, started)
      try:
        set_startup_gate_cache(startup_blockers_from_sm(sm))
      except Exception:
        pass
      _set_state(build_state_from_sm(sm))
    except Exception as exc:
      _set_state({
        "ok": False,
        "error": str(exc),
        "started": False,
        "engaged": False,
        "ui_status": "disengaged",
      })
    home_ticks += 1
    home_slow_ticks += 1
    if home_ticks >= home_interval:
      try:
        if home_slow_ticks >= home_slow_interval:
          refresh_home_slow_cache(headless=headless)
          home_slow_ticks = 0
        _set_home(snapshot_home_core(started=started))
      except Exception:
        pass
      home_ticks = 0
    time.sleep(0.1)
