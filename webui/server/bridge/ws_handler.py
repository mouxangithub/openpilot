"""WebSocket hub — push UI state, home, panels, model overlay + RPC."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from aiohttp import web

from webui.server.bridge.model_overlay import (
  OVERLAY_PARAM_KEYS,
  invalidate_overlay_params_cache,
  overlay_anim_key,
  overlay_frame_key,
  overlay_geometry_key,
  overlay_wire_payload,
  snapshot_model_overlay,
)
from webui.server.bridge.params_api import panel_values, put_param
from webui.server.bridge.state_hub import get_home, get_home_json, get_state, get_state_json, home_seq, state_seq
from webui.server.bridge.ws_rpc import bootstrap_payload, custom_panel_data, dispatch_http

log = logging.getLogger("webui.ws")

_connections: set[web.WebSocketResponse] = set()
_meta: dict[web.WebSocketResponse, dict[str, Any]] = {}
_panel_hash: dict[str, str] = {}
_custom_hash: dict[str, str] = {}
_broadcast_task: asyncio.Task | None = None

STATE_INTERVAL = 0.2
PANEL_INTERVAL = 0.4
HOME_INTERVAL = 1.5
CUSTOM_INTERVAL = 1.0
MODEL_INTERVAL = 0.1
MODEL_INTERVAL_LOW = 0.2
_last_i18n_lang: str | None = None
I18N_INTERVAL = 0.5
STREAM_HEALTH_INTERVAL = 3.0
_stream_health_hash = ""


def _values_hash(values: dict[str, Any]) -> str:
  return json.dumps(values, sort_keys=True, default=str)


def _data_hash(data: Any) -> str:
  return json.dumps(data, sort_keys=True, default=str)


def ws_connection_count() -> int:
  return len(_connections)


async def ws_opui_handler(request: web.Request) -> web.WebSocketResponse:
  ws = web.WebSocketResponse(heartbeat=30)
  await ws.prepare(request)
  _connections.add(ws)
  try:
    from webui.server.bridge.webui_bg_services import note_ws_client_connected
    note_ws_client_connected()
  except Exception:
    pass
  _meta[ws] = {
    "state": True,
    "home": True,
    "i18n": False,
    "stream_health": False,
    "watch_panel": None,
    "model_overlay": None,
    "last_state_seq": -1,
    "last_home_seq": -1,
    "last_panel_hash": "",
    "last_custom_hash": "",
    "last_model_hash": "",
    "last_geometry_hash": "",
    "last_anim_hash": "",
  }
  try:
    await ws.send_json({
      "type": "hello",
      "ok": True,
      "proto": 2,
      "bootstrap": bootstrap_payload(),
    })
    state_json = get_state_json()
    if state_json:
      await ws.send_str(state_json)
    else:
      await ws.send_json({"type": "state", "seq": state_seq(), "data": get_state()})
    _meta[ws]["last_state_seq"] = state_seq()
    home_json = get_home_json()
    if home_json:
      await ws.send_str(home_json)
    else:
      await ws.send_json({"type": "home", "seq": home_seq(), "data": get_home()})
    _meta[ws]["last_home_seq"] = home_seq()

    async for msg in ws:
      if msg.type == web.WSMsgType.TEXT:
        try:
          payload = json.loads(msg.data)
        except json.JSONDecodeError:
          await ws.send_json({"type": "error", "error": "invalid json"})
          continue
        await _handle_client(ws, payload)
      elif msg.type in (web.WSMsgType.CLOSE, web.WSMsgType.ERROR):
        break
  finally:
    meta = _meta.pop(ws, None)
    if meta and meta.get("watch_panel") == "sunnylink":
      try:
        from webui.server.bridge.webui_bg_services import sunnylink_panel_watch
        sunnylink_panel_watch(-1)
      except Exception:
        pass
    _connections.discard(ws)
    try:
      from webui.server.bridge.webui_bg_services import note_ws_client_disconnected
      note_ws_client_disconnected()
    except Exception:
      pass
  return ws


async def _handle_client(ws: web.WebSocketResponse, msg: dict[str, Any]) -> None:
  mtype = msg.get("type")
  meta = _meta.get(ws)
  if not meta:
    return

  if mtype == "subscribe":
    channels = set(msg.get("channels") or [])
    if channels:
      meta["state"] = "state" in channels
      meta["home"] = "home" in channels
      meta["i18n"] = "i18n" in channels
      meta["stream_health"] = "stream_health" in channels
    if meta["state"]:
      payload = get_state_json()
      if payload:
        await ws.send_str(payload)
      else:
        await ws.send_json({"type": "state", "seq": state_seq(), "data": get_state()})
      meta["last_state_seq"] = state_seq()
    if meta["home"]:
      payload = get_home_json()
      if payload:
        await ws.send_str(payload)
      else:
        await ws.send_json({"type": "home", "seq": home_seq(), "data": get_home()})
      meta["last_home_seq"] = home_seq()
    if meta["i18n"]:
      from webui.server.bridge.i18n_api import snapshot_i18n
      await ws.send_json({"type": "i18n", "data": snapshot_i18n()})
    return

  if mtype == "watch_panel":
    panel_id = str(msg.get("panel") or "")
    old_panel = meta.get("watch_panel")
    meta["watch_panel"] = panel_id or None
    try:
      from webui.server.bridge.webui_bg_services import sunnylink_panel_watch
      if old_panel == "sunnylink" and panel_id != "sunnylink":
        sunnylink_panel_watch(-1)
      if panel_id == "sunnylink" and old_panel != "sunnylink":
        sunnylink_panel_watch(1)
        from webui.server.bridge.webui_bg_services import maybe_refresh_sunnylink_cache
        maybe_refresh_sunnylink_cache(force=True)
    except Exception:
      pass
    meta["last_panel_hash"] = ""
    meta["last_custom_hash"] = ""
    if panel_id:
      data = await asyncio.to_thread(panel_values, panel_id)
      h = _values_hash(data.get("values", {}))
      meta["last_panel_hash"] = h
      _panel_hash[panel_id] = h
      await ws.send_json({"type": "panel", "panel": panel_id, "data": data})
      custom = await asyncio.to_thread(custom_panel_data, panel_id)
      if custom:
        ch = _data_hash(custom)
        meta["last_custom_hash"] = ch
        _custom_hash[panel_id] = ch
        await ws.send_json({"type": "panel_custom", "panel": panel_id, "data": custom})
    return

  if mtype == "watch_model_overlay":
    w = int(msg.get("w") or 1600)
    h = int(msg.get("h") or 900)
    fps = int(msg.get("fps") or 10)
    fps = max(3, min(20, fps))
    prev = meta.get("model_overlay")
    if prev and prev.get("w") == w and prev.get("h") == h and prev.get("fps") == fps:
      return
    meta["model_overlay"] = {"w": w, "h": h, "fps": fps}
    meta["last_model_hash"] = ""
    meta["last_geometry_hash"] = ""
    meta["last_anim_hash"] = ""
    frame = await asyncio.to_thread(snapshot_model_overlay, w, h)
    meta["last_model_hash"] = overlay_frame_key(frame)
    meta["last_geometry_hash"] = overlay_geometry_key(frame)
    meta["last_anim_hash"] = overlay_anim_key(frame)
    await ws.send_json({"type": "model_overlay", "data": frame})
    return

  if mtype == "unwatch_model_overlay":
    meta["model_overlay"] = None
    meta["last_model_hash"] = ""
    meta["last_geometry_hash"] = ""
    meta["last_anim_hash"] = ""
    return

  if mtype == "rpc":
    req_id = msg.get("id")
    method = str(msg.get("method") or "GET").upper()
    path = str(msg.get("path") or "")
    body = msg.get("body") if isinstance(msg.get("body"), dict) else {}
    result = await asyncio.to_thread(dispatch_http, method, path, body)
    await ws.send_json({"type": "rpc_result", "id": req_id, **result})
    if result.get("ok") and method == "PUT" and "/api/opui/params/" in path:
      key = path.rsplit("/", 1)[-1].split("?")[0]
      await _broadcast_panel_updates_for_key(key)
      if key in OVERLAY_PARAM_KEYS:
        invalidate_overlay_params_cache()
      if key == "LanguageSetting":
        await _broadcast_i18n(force=True)
    if result.get("ok") and method == "PUT" and path.rstrip("/").endswith("/api/opui/display/brightness"):
      await _broadcast_panel_updates_for_key("Brightness")
    if result.get("ok") and method == "POST" and path.rstrip("/").endswith("/api/opui/device/language"):
      await _broadcast_i18n(force=True)
    return

  if mtype == "put_param":
    req_id = msg.get("id")
    key = str(msg.get("key") or "")
    value = str(msg.get("value", ""))
    needs_cycle = bool(msg.get("needs_cycle", False))
    result = await asyncio.to_thread(put_param, key, value, needs_cycle=needs_cycle)
    await ws.send_json({"type": "put_param_result", "id": req_id, **result})
    if result.get("ok"):
      await _broadcast_panel_updates_for_key(key)
      if key in OVERLAY_PARAM_KEYS:
        invalidate_overlay_params_cache()
      if key == "LanguageSetting":
        await _broadcast_i18n(force=True)
    return

  if mtype == "ping":
    await ws.send_json({"type": "pong"})
    return

  await ws.send_json({"type": "error", "error": f"unknown type: {mtype}"})


async def _broadcast_i18n(force: bool = False) -> None:
  global _last_i18n_lang
  from webui.server.bridge.i18n_api import snapshot_i18n

  data = snapshot_i18n()
  lang = str(data.get("language") or "")
  if not force and lang == _last_i18n_lang:
    return
  _last_i18n_lang = lang
  dead: list[web.WebSocketResponse] = []
  for ws, meta in list(_meta.items()):
    if not meta.get("i18n"):
      continue
    try:
      await ws.send_json({"type": "i18n", "data": data})
    except Exception:
      dead.append(ws)
  for ws in dead:
    _connections.discard(ws)
    _meta.pop(ws, None)


async def _broadcast_panel_updates_for_key(_key: str) -> None:
  dead: list[web.WebSocketResponse] = []
  for ws, meta in list(_meta.items()):
    panel_id = meta.get("watch_panel")
    if not panel_id:
      continue
    try:
      data = await asyncio.to_thread(panel_values, panel_id)
      h = _values_hash(data.get("values", {}))
      if h != meta.get("last_panel_hash"):
        meta["last_panel_hash"] = h
        _panel_hash[panel_id] = h
        await ws.send_json({"type": "panel", "panel": panel_id, "data": data})
      custom = await asyncio.to_thread(custom_panel_data, panel_id)
      if custom:
        ch = _data_hash(custom)
        if ch != meta.get("last_custom_hash"):
          meta["last_custom_hash"] = ch
          _custom_hash[panel_id] = ch
          await ws.send_json({"type": "panel_custom", "panel": panel_id, "data": custom})
    except Exception:
      dead.append(ws)
  for ws in dead:
    _connections.discard(ws)
    _meta.pop(ws, None)


async def _broadcast_model_overlays(now: float) -> None:
  due: list[tuple[web.WebSocketResponse, dict[str, Any], dict[str, Any]]] = []
  for ws, meta in list(_meta.items()):
    ov = meta.get("model_overlay")
    if not ov:
      continue
    fps = int(ov.get("fps") or 10)
    interval = max(MODEL_INTERVAL_LOW, 1.0 / max(3, min(20, fps)))
    if now - meta.get("last_model_push_at", 0) < interval:
      continue
    meta["last_model_push_at"] = now
    due.append((ws, meta, ov))

  if not due:
    return

  sizes = {(int(ov["w"]), int(ov["h"])) for _, _, ov in due}
  frames: dict[tuple[int, int], dict[str, Any]] = {}
  for w, h in sizes:
    frames[(w, h)] = await asyncio.to_thread(snapshot_model_overlay, w, h)

  sends: list[tuple[web.WebSocketResponse, str]] = []
  dead: list[web.WebSocketResponse] = []
  for ws, meta, ov in due:
    wh = (int(ov["w"]), int(ov["h"]))
    frame = frames[wh]
    try:
      gk = overlay_geometry_key(frame)
      ak = overlay_anim_key(frame)
      if frame.get("clear"):
        if gk == meta.get("last_geometry_hash") and meta.get("last_geometry_hash"):
          continue
        meta["last_geometry_hash"] = gk
        meta["last_anim_hash"] = ak
        meta["last_model_hash"] = overlay_frame_key(frame)
      elif frame.get("anim_only"):
        if ak == meta.get("last_anim_hash"):
          continue
        meta["last_anim_hash"] = ak
        meta["last_model_hash"] = overlay_frame_key(frame)
      else:
        if gk == meta.get("last_geometry_hash") and ak == meta.get("last_anim_hash"):
          continue
        meta["last_geometry_hash"] = gk
        meta["last_anim_hash"] = ak
        meta["last_model_hash"] = overlay_frame_key(frame)
      payload = json.dumps(
        {"type": "model_overlay", "data": overlay_wire_payload(frame)},
        separators=(",", ":"),
        default=str,
      )
      sends.append((ws, payload))
    except Exception:
      dead.append(ws)

  if sends:
    results = await asyncio.gather(
      *[ws.send_str(payload) for ws, payload in sends],
      return_exceptions=True,
    )
    for (ws, _), result in zip(sends, results):
      if isinstance(result, Exception):
        dead.append(ws)

  for ws in dead:
    _connections.discard(ws)
    _meta.pop(ws, None)


async def ws_broadcast_loop() -> None:
  last_state_push = 0.0
  last_panel_push = 0.0
  last_home_push = 0.0
  last_custom_push = 0.0
  last_model_push = 0.0
  last_i18n_push = 0.0
  last_stream_push = 0.0
  while True:
    try:
      await asyncio.sleep(0.5 if not _connections else 0.05)
      if not _connections:
        continue
      now = asyncio.get_event_loop().time()

      if now - last_state_push >= STATE_INTERVAL:
        last_state_push = now
        seq = state_seq()
        dead: list[web.WebSocketResponse] = []
        for ws, meta in list(_meta.items()):
          if not meta.get("state") or meta.get("last_state_seq") == seq:
            continue
          try:
            payload = get_state_json(seq)
            if payload:
              await ws.send_str(payload)
            else:
              await ws.send_json({"type": "state", "seq": seq, "data": get_state()})
            meta["last_state_seq"] = seq
          except Exception:
            dead.append(ws)
        for ws in dead:
          _connections.discard(ws)
          _meta.pop(ws, None)

      if now - last_panel_push >= PANEL_INTERVAL:
        last_panel_push = now
        watched = {m.get("watch_panel") for m in _meta.values() if m.get("watch_panel")}
        for panel_id in watched:
          data = await asyncio.to_thread(panel_values, panel_id)
          h = _values_hash(data.get("values", {}))
          if _panel_hash.get(panel_id) != h:
            _panel_hash[panel_id] = h
            dead = []
            for ws, meta in list(_meta.items()):
              if meta.get("watch_panel") != panel_id:
                continue
              try:
                await ws.send_json({"type": "panel", "panel": panel_id, "data": data})
                meta["last_panel_hash"] = h
              except Exception:
                dead.append(ws)
            for ws in dead:
              _connections.discard(ws)
              _meta.pop(ws, None)

      if now - last_custom_push >= CUSTOM_INTERVAL:
        last_custom_push = now
        watched = {m.get("watch_panel") for m in _meta.values() if m.get("watch_panel")}
        for panel_id in watched:
          if panel_id == "sunnylink":
            try:
              from webui.server.bridge.webui_bg_services import maybe_refresh_sunnylink_cache
              maybe_refresh_sunnylink_cache()
            except Exception:
              pass
          custom = await asyncio.to_thread(custom_panel_data, panel_id)
          if not custom:
            continue
          ch = _data_hash(custom)
          if _custom_hash.get(panel_id) == ch:
            continue
          _custom_hash[panel_id] = ch
          dead = []
          for ws, meta in list(_meta.items()):
            if meta.get("watch_panel") != panel_id:
              continue
            try:
              await ws.send_json({"type": "panel_custom", "panel": panel_id, "data": custom})
              meta["last_custom_hash"] = ch
            except Exception:
              dead.append(ws)
          for ws in dead:
            _connections.discard(ws)
            _meta.pop(ws, None)

      if now - last_model_push >= MODEL_INTERVAL:
        last_model_push = now
        await _broadcast_model_overlays(now)

      if now - last_home_push >= HOME_INTERVAL:
        last_home_push = now
        seq = home_seq()
        dead = []
        for ws, meta in list(_meta.items()):
          if not meta.get("home") or meta.get("last_home_seq") == seq:
            continue
          try:
            payload = get_home_json(seq)
            if payload:
              await ws.send_str(payload)
            else:
              await ws.send_json({"type": "home", "seq": seq, "data": get_home()})
            meta["last_home_seq"] = seq
          except Exception:
            dead.append(ws)
        for ws in dead:
          _connections.discard(ws)
          _meta.pop(ws, None)

      if now - last_stream_push >= STREAM_HEALTH_INTERVAL:
        last_stream_push = now
        if any(m.get("stream_health") for m in _meta.values()):
          global _stream_health_hash
          from webui.server.bridge.stream_health_api import snapshot_stream_health
          health = await asyncio.to_thread(snapshot_stream_health)
          ch = _data_hash(health)
          if ch != _stream_health_hash:
            _stream_health_hash = ch
            payload = json.dumps({"type": "stream_health", "data": health}, separators=(",", ":"), default=str)
            dead = []
            for ws, meta in list(_meta.items()):
              if not meta.get("stream_health"):
                continue
              try:
                await ws.send_str(payload)
              except Exception:
                dead.append(ws)
            for ws in dead:
              _connections.discard(ws)
              _meta.pop(ws, None)

      if now - last_i18n_push >= I18N_INTERVAL:
        last_i18n_push = now
        await _broadcast_i18n()
    except asyncio.CancelledError:
      raise
    except Exception as exc:
      log.warning("ws broadcast error: %s", exc)


def start_ws_broadcast(app: web.Application) -> None:
  global _broadcast_task
  if _broadcast_task is not None and not _broadcast_task.done():
    return

  async def _runner(_app: web.Application) -> None:
    global _broadcast_task
    _broadcast_task = asyncio.create_task(ws_broadcast_loop())

  async def _cleanup(_app: web.Application) -> None:
    global _broadcast_task
    if _broadcast_task:
      _broadcast_task.cancel()
      try:
        await _broadcast_task
      except asyncio.CancelledError:
        pass
      _broadcast_task = None

  app.on_startup.append(_runner)
  app.on_cleanup.append(_cleanup)
