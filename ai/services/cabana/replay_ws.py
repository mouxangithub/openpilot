"""Cabana replay WS endpoint (offline replay over WebSocket).

``ws_offline`` is the legacy endpoint (unchanged message protocol);
``run_replay_ws`` is the shared executor also used by the unified
``/api/cabana/stream/ws`` endpoint.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from aiohttp import web

from ai.services.cabana.car_params import _resolve_car_params
from ai.services.cabana.dbc import _suggest_dbc_for_car
from ai.services.cabana.deps import LogReader
from ai.services.cabana.deps import cloudlog
from ai.services.cabana.decoder import decode_frames as _decode_frames
from ai.services.cabana.decoder import decode_frames_multi as _decode_frames_multi
from ai.services.cabana.decoder import get_decoder as _get_decoder
from ai.services.cabana.decoder import get_decoders as _get_decoders
from ai.services.cabana.frame import encode_frame_data
from ai.services.cabana.replay import _get_routes_dir
from ai.services.cabana.replay import _video_info_for_route
from ai.services.cabana.replay import _video_time_at
from ai.services.cabana.replay_stream import ReplayStream
from ai.services.cabana.replay_util import (
  REPLAY_SNAPSHOT_INTERVAL,
  compact_can_batch as _compact_can_batch,
)


def _truthy(value: Any) -> bool:
  if isinstance(value, bool):
    return value
  return str(value).strip().lower() in ("1", "true", "yes")


def _param(query: Any, init_msg: dict[str, Any] | None, key: str, default: Any = None) -> Any:
  """Resolve a replay parameter: init message overrides query string."""
  if init_msg is not None and init_msg.get(key) is not None:
    return init_msg[key]
  return query.get(key, default)


async def run_replay_ws(
  request: web.Request,
  ws: web.WebSocketResponse,
  *,
  init_msg: dict[str, Any] | None = None,
) -> None:
  """Run a replay session over an already-prepared WebSocket."""
  query = request.query

  async def ws_send(payload: dict[str, Any]) -> bool:
    try:
      await ws.send_str(json.dumps(payload, separators=(",", ":")))
      return True
    except (ConnectionResetError, asyncio.CancelledError):
      return False
    except Exception as e:
      if e.__class__.__name__ == "ClientConnectionResetError":
        return False
      raise

  if LogReader is None:
    await ws_send({"type": "error", "error": "LogReader not available"})
    await ws.close()
    return

  route = str(_param(query, init_msg, "route", "") or "")
  routes_dir = _get_routes_dir()
  if not route or routes_dir is None:
    await ws.send_str(json.dumps({"type": "error", "error": "No route specified"}))
    await ws.close()
    return

  full_can = _truthy(_param(query, init_msg, "full", "0"))
  stream = ReplayStream(route, full=full_can, routes_dir=routes_dir)
  if not stream.qlogs and not stream.rlogs:
    await ws.send_str(json.dumps({
      "type": "error",
      "error": "No qlog/rlog found in route",
      "hint": "This folder has no driving logs (e.g. boot/ is not a route). Pick a route with qlog or rlog.",
    }))
    await ws.close()
    return

  qlogs = stream.qlogs
  rlogs = stream.rlogs
  speed = float(_param(query, init_msg, "speed", "1.0"))
  start_time = float(_param(query, init_msg, "start_time", "0"))
  autoplay = _truthy(_param(query, init_msg, "autoplay", "1"))
  paused = not autoplay
  encoding = "base64" if str(_param(query, init_msg, "encoding", "hex") or "hex").lower() == "base64" else "hex"
  decode_enabled = _truthy(_param(query, init_msg, "decode", "0"))

  loop = asyncio.get_running_loop()

  # Optional server-side signal decoding (opt-in; never changes default behavior).
  # ``bus_dbc`` (JSON object bus->dbc name) selects the per-bus multi-DBC path;
  # otherwise a single DBC is used best-effort (warning behavior unchanged).
  decoder_signals: list[dict[str, Any]] = []
  multi_decoders: dict[str, dict[int, list[dict[str, Any]]]] | None = None
  if decode_enabled:
    bus_map: dict[str, str] | None = None
    bus_dbc_raw = _param(query, init_msg, "bus_dbc", None)
    if bus_dbc_raw:
      if isinstance(bus_dbc_raw, str):
        try:
          bus_dbc_raw = json.loads(bus_dbc_raw)
        except (ValueError, TypeError):
          bus_dbc_raw = None
      if isinstance(bus_dbc_raw, dict) and bus_dbc_raw:
        bus_map = {str(k): str(v) for k, v in bus_dbc_raw.items() if v}
    if bus_map:
      try:
        multi_decoders = await loop.run_in_executor(None, _get_decoders, bus_map)
      except Exception:
        multi_decoders = None
      if not multi_decoders:
        multi_decoders = None
        decode_enabled = False
        await ws_send({"type": "warning", "error": "decode unavailable"})
    else:
      dbc_name = str(_param(query, init_msg, "dbc", "") or "")
      if not dbc_name:
        def resolve_dbc() -> str | None:
          cp = _resolve_car_params(route)
          return _suggest_dbc_for_car(cp) if cp else None
        try:
          dbc_name = str(await loop.run_in_executor(None, resolve_dbc) or "")
        except Exception:
          dbc_name = ""
      table = None
      if dbc_name:
        try:
          table = await loop.run_in_executor(None, _get_decoder, dbc_name)
        except Exception:
          table = None
      if table:
        decoder_signals = [s for sigs in table.values() for s in sigs]
      else:
        decode_enabled = False
        await ws_send({"type": "warning", "error": "decode unavailable"})

  def out_frames(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if encoding == "hex":
      return frames
    return [{**f, "data": encode_frame_data(str(f.get("data", "")), encoding)} for f in frames]

  async def maybe_decode(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not frames:
      return frames
    if multi_decoders:
      return await loop.run_in_executor(None, _decode_frames_multi, multi_decoders, frames)
    if not decoder_signals:
      return frames
    return await loop.run_in_executor(None, _decode_frames, decoder_signals, frames)

  seq_counter = 0

  def can_payload(frames: list[dict[str, Any]], progress: float, *, preview: bool = False) -> dict[str, Any]:
    nonlocal seq_counter
    seq_counter += 1
    payload: dict[str, Any] = {
      "type": "can",
      "seq": seq_counter,
      "source": stream.source,
      "frames": frames,
      "progress": progress,
    }
    if preview:
      payload["preview"] = True
    return payload

  async def control_loop():
    nonlocal paused, speed
    async for msg in ws:
      try:
        data = json.loads(msg.data)
        cmd = data.get("action")
        if cmd == "pause":
          paused = True
        elif cmd == "play":
          paused = False
        elif cmd == "speed":
          speed = max(0.1, min(10.0, float(data.get("value", 1.0))))
          stream.speed(speed)
        elif cmd == "seek":
          stream.seek(max(0.0, float(data.get("time", 0.0))))
      except Exception:
        pass

  control_task = asyncio.create_task(control_loop())

  # Client went away mid-session (page refresh, popup closed, reconnect):
  # control_loop's `async for` ends as soon as the socket closes — abort any
  # in-flight scan immediately so the worker thread frees up. Harmless when
  # the session is already ending (finally also stops the stream).
  control_task.add_done_callback(lambda _task: stream.stop())
  progress_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

  def progress_cb(payload: dict[str, Any]) -> None:
    loop.call_soon_threadsafe(progress_queue.put_nowait, payload)

  stream_paths = stream.stream_paths
  source = stream.source

  async def progress_reporter() -> None:
    if not await ws_send({
      "type": "loading",
      "phase": "start",
      "source": source,
      "files": len(stream_paths),
      "qlogs": len(qlogs),
      "rlogs": len(rlogs),
    }):
      return
    while True:
      try:
        payload = await asyncio.wait_for(progress_queue.get(), timeout=2.0)
        if not await ws_send({"type": "loading", **payload}):
          return
      except TimeoutError:
        if not await ws_send({"type": "loading", "phase": "scanning", "heartbeat": True}):
          return

  reporter_task = asyncio.create_task(progress_reporter())
  try:
    decimated, from_cache = False, False
    try:
      source, decimated, from_cache = await stream.load_async(loop, progress_cb)
    finally:
      reporter_task.cancel()
      try:
        await reporter_task
      except asyncio.CancelledError:
        pass
  except Exception:
    reporter_task.cancel()
    raise

  drain_task: asyncio.Task[None] | None = None
  if stream.streaming_load:

    async def drain_and_notify() -> None:
      await stream.drain_async()
      if stream.all_frames:
        await ws.send_str(json.dumps({
          "type": "metadata_update",
          "duration": stream.all_frames[-1]["time"] - stream.all_frames[0]["time"],
          "frame_count": len(stream.all_frames),
        }))

    drain_task = asyncio.create_task(drain_and_notify())

  try:
    if not stream.all_frames and stream.streaming_load:
      try:
        await asyncio.wait_for(stream.load_complete.wait(), timeout=120.0)
      except TimeoutError:
        # First chunks are usually buffered long before the full index
        # completes; keep playing what we have instead of dropping the
        # connection. The background drain task keeps topping up frames.
        cloudlog.warning("cabana replay: initial load timeout after 120s, continuing with buffered frames")
    elif stream.streaming_load:
      # Do not block UI on full background drain — metadata uses partial buffer first.
      pass
    else:
      stream.load_complete.set()

    if not stream.all_frames:
      tried = []
      if qlogs:
        tried.append(f"qlog×{len(qlogs)}")
      if rlogs:
        tried.append(f"rlog×{len(rlogs)}")
      detail = ", ".join(tried) if tried else "no logs"
      await ws.send_str(json.dumps({
        "type": "error",
        "error": f"No CAN frames found ({detail}). qlog is heavily decimated; ensure rlog exists.",
      }))
      await ws.close()
      return

    first_time = stream.all_frames[0]["time"]
    last_time = stream.all_frames[-1]["time"]
    duration = last_time - first_time
    original_count = len(stream.all_frames)

    init_state = stream.preview_at(start_time)

    video_info: dict[str, Any] = {"fps": 20.0, "segment_length_sec": 60, "available": False}
    try:
      video_info = await loop.run_in_executor(None, _video_info_for_route, route)
    except Exception:
      pass

    await ws.send_str(json.dumps({
      "type": "metadata",
      "duration": duration,
      "frame_count": len(stream.all_frames),
      "original_frame_count": original_count,
      "decimated": decimated,
      "truncated": bool(decimated),
      "start_time": first_time,
      "source": source,
      "cached": from_cache,
      "full_can": full_can,
      "has_rlog": bool(rlogs),
      "streaming": stream.streaming_load,
      "snapshots": 0,
      "init_frames": init_state or [],
      "video": video_info,
    }))

    if init_state:
      init_progress = max(0.0, start_time)
      await ws_send(can_payload(out_frames(await maybe_decode(list(init_state))), init_progress, preview=True))

    await ws.send_str(json.dumps({
      "type": "loading",
      "phase": "ready",
      "can_frames": len(stream.all_frames),
      "original_frame_count": original_count,
    }))

    await asyncio.sleep(0)

    # Design intent: do NOT block the playback loop waiting for the background
    # drain to finish — the first buffered frames are already primed (prime()
    # below), so playback starts immediately while drain_task keeps filling the
    # buffer. The loop below handles the not-yet-complete drain via its
    # `load_complete` branches (bounds() == 0 poll and at_end wait).

    # Stream playback without pre-building the full snapshot list (avoids multi-second stall).
    interval = REPLAY_SNAPSHOT_INTERVAL
    next_emit = first_time + max(0.0, start_time)
    playback_start = time.monotonic()
    base_progress = max(0.0, start_time)

    stream.prime(next_emit)

    while True:
      n, last_time = stream.bounds()
      if n == 0:
        if stream.load_complete.is_set():
          break
        await asyncio.sleep(0.05)  # intentional poll while streaming drain fills the buffer
        continue

      pending_seek = stream.take_seek()
      if pending_seek is not None:
        st_rel = pending_seek
        next_emit = first_time + st_rel
        base_progress = st_rel
        playback_start = time.monotonic()
        seek_state = stream.reset_to(next_emit)
        video_time = None
        try:
          video_time = await loop.run_in_executor(None, _video_time_at, route, st_rel)
        except Exception:
          video_time = None
        await ws.send_str(json.dumps({"type": "seeked", "time": st_rel, "video_time": video_time}))
        if seek_state:
          await ws_send(can_payload(
            out_frames(await maybe_decode(_compact_can_batch(seek_state))), st_rel, preview=True,
          ))
        continue

      if stream.at_end and next_emit > last_time + interval:
        if stream.streaming_load and not stream.load_complete.is_set():
          await asyncio.sleep(0.02)  # intentional poll while streaming drain continues
          continue
        break

      progress = max(0.0, next_emit - first_time)
      rel = (progress - base_progress) / max(speed, 0.01)
      target = playback_start + rel
      while time.monotonic() < target and not paused:  # noqa: ASYNC110  (playback pacing)
        await asyncio.sleep(0.01)
      if paused:
        paused_at = time.monotonic()
        while paused:  # noqa: ASYNC110  (paused wait loop)
          await asyncio.sleep(0.05)
        playback_start += time.monotonic() - paused_at
        base_progress = progress

      delta, tick_progress = stream.tick(next_emit)

      if delta:
        if not await ws_send(can_payload(out_frames(await maybe_decode(_compact_can_batch(delta))), tick_progress)):
          break
      elif not await ws_send({"type": "progress", "progress": tick_progress}):
        break

      next_emit += interval
      await asyncio.sleep(0)

    await ws_send({"type": "done"})
  except Exception as e:
    await ws_send({"type": "error", "error": str(e)})
  finally:
    stream.stop()
    if drain_task is not None:
      drain_task.cancel()
      try:
        await drain_task
      except (asyncio.CancelledError, Exception):
        pass
    control_task.cancel()
    try:
      await control_task
    except asyncio.CancelledError:
      pass
    await ws.close()


async def ws_offline(request: web.Request) -> web.WebSocketResponse:
  """Legacy offline replay endpoint (protocol unchanged)."""
  ws = web.WebSocketResponse()
  await ws.prepare(request)
  await run_replay_ws(request, ws)
  return ws
