"""Cabana replay_ws module."""
from ai.services.cabana.deps import *
from ai.services.cabana.frame import can_frame_to_dict as _can_frame_to_dict
from ai.services.cabana.replay import (
  CACHE_VERSION,
  MAX_REPLAY_FRAMES,
  QLOG_CACHE_MAX_FRAMES,
  REPLAY_FRAME_QUEUE_SIZE,
  REPLAY_START_BUFFER,
  REPLAY_STREAM_BATCH,
  _cabana_cache_dir,
  _collect_can_frames,
  _find_qlogs,
  _find_rlogs,
  _get_routes_dir,
  _iter_can_batches,
  _load_route_cache,
  _replay_log_paths,
  _route_cache_file,
  _save_route_cache,
  _threadsafe_queue_put,
)
from ai.services.cabana.dbc import _parse_dbc_signals, _suggest_dbc_for_car
from ai.services.cabana.car_params import _resolve_car_params

async def ws_offline(request: web.Request) -> web.WebSocketResponse:
  ws = web.WebSocketResponse()
  await ws.prepare(request)

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
    return ws

  route = request.query.get("route", "")
  routes_dir = _get_routes_dir()
  if not route or routes_dir is None:
    await ws.send_str(json.dumps({"type": "error", "error": "No route specified"}))
    await ws.close()
    return ws

  route_path = routes_dir / route
  if route_path.is_dir():
    qlogs = _find_qlogs(route_path)
    rlogs = _find_rlogs(route_path)
  else:
    qlogs = [route_path] if route_path.is_file() else []
    rlogs = []

  if not qlogs and not rlogs:
    await ws.send_str(json.dumps({
      "type": "error",
      "error": "No qlog/rlog found in route",
      "hint": "This folder has no driving logs (e.g. boot/ is not a route). Pick a route with qlog or rlog.",
    }))
    await ws.close()
    return ws

  speed = float(request.query.get("speed", "1.0"))
  start_time = float(request.query.get("start_time", "0"))
  autoplay = request.query.get("autoplay", "1").lower() in ("1", "true", "yes")
  full_can = request.query.get("full", "0").lower() in ("1", "true", "yes")
  paused = not autoplay
  seek_time_rel: float | None = None

  async def control_loop():
    nonlocal paused, speed, seek_time_rel
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
        elif cmd == "seek":
          seek_time_rel = max(0.0, float(data.get("time", 0.0)))
      except Exception:
        pass

  control_task = asyncio.create_task(control_loop())
  loop = asyncio.get_running_loop()
  progress_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

  def progress_cb(payload: dict[str, Any]) -> None:
    loop.call_soon_threadsafe(progress_queue.put_nowait, payload)

  stream_paths, source = _replay_log_paths(qlogs, rlogs, full=full_can)
  frame_queue: asyncio.Queue[Any] | None = None
  reader_task: asyncio.Task[Any] | None = None
  load_complete = asyncio.Event()
  streaming_load = False

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
      except asyncio.TimeoutError:
        if not await ws_send({"type": "loading", "phase": "scanning", "heartbeat": True}):
          return

  async def drain_stream_queue() -> None:
    nonlocal all_frames
    if frame_queue is None:
      load_complete.set()
      return
    while True:
      item = await frame_queue.get()
      if item is None:
        break
      if isinstance(item, tuple) and item[0] == "error":
        raise RuntimeError(item[1])
      all_frames.extend(item)
    if reader_task is not None:
      await reader_task
    load_complete.set()
    if streaming_load and all_frames:
      await ws.send_str(json.dumps({
        "type": "metadata_update",
        "duration": all_frames[-1]["time"] - all_frames[0]["time"],
        "frame_count": len(all_frames),
      }))

  async def load_replay_frames() -> tuple[list[dict[str, Any]], bool, str, bool]:
    nonlocal frame_queue, reader_task, streaming_load
    if route_path.is_dir():
      cached = await loop.run_in_executor(
        None, lambda: _load_route_cache(route_path, want_full=full_can),
      )
      if cached:
        progress_cb({"phase": "cache_hit", "can_frames": len(cached)})
        return cached, False, source, True

    # Default fast path: qlog-only, read in one pass (no background drain / no rlog).
    if not full_can and source == "qlog":

      def read_qlog_only() -> tuple[list[dict[str, Any]], bool]:
        progress_cb({"phase": "fast_qlog", "files": len(stream_paths), "parallel": len(stream_paths) > 1})
        frames, dec = _collect_can_frames(stream_paths, progress_cb)
        return frames, dec

      frames, dec = await loop.run_in_executor(None, read_qlog_only)
      if route_path.is_dir() and frames:
        asyncio.ensure_future(loop.run_in_executor(
          None,
          lambda: _save_route_cache(route_path, frames, decimated=dec, full=False),
        ))
      return frames, dec, source, False

    frame_queue = asyncio.Queue(maxsize=REPLAY_FRAME_QUEUE_SIZE)
    streaming_load = True

    def stream_logs() -> None:
      collected: list[dict[str, Any]] = []
      can_total = 0
      decimated_local = False
      try:
        progress_cb({
          "phase": "fast_rlog" if source == "rlog" else "qlog",
          "files": len(stream_paths),
          "parallel": len(stream_paths) > 1,
        })
        for file_name, batch in _iter_can_batches(stream_paths):
          collected.extend(batch)
          can_total += len(batch)
          progress_cb({"phase": "scanning", "file": file_name, "can_frames": can_total})
          _threadsafe_queue_put(frame_queue, batch, loop)
        collected.sort(key=lambda f: f["time"])
        if len(collected) > MAX_REPLAY_FRAMES:
          stride = max(1, len(collected) // MAX_REPLAY_FRAMES)
          collected = collected[::stride]
          decimated_local = True
        if route_path.is_dir() and collected:
          _save_route_cache(route_path, collected, decimated=decimated_local, full=full_can)
      except Exception as e:
        _threadsafe_queue_put(frame_queue, ("error", str(e)), loop)
      finally:
        _threadsafe_queue_put(frame_queue, None, loop)

    reader_task = loop.run_in_executor(None, stream_logs)
    partial: list[dict[str, Any]] = []
    while len(partial) < REPLAY_START_BUFFER:
      item = await frame_queue.get()
      if item is None:
        break
      if isinstance(item, tuple) and item[0] == "error":
        raise RuntimeError(item[1])
      partial.extend(item)
    return partial, False, source, False

  all_frames: list[dict[str, Any]] = []
  decimated = False
  from_cache = False

  reporter_task = asyncio.create_task(progress_reporter())
  try:
    all_frames, decimated, source, from_cache = await load_replay_frames()
  finally:
    reporter_task.cancel()
    try:
      await reporter_task
    except asyncio.CancelledError:
      pass

  drain_task: asyncio.Task[None] | None = None
  if streaming_load:
    drain_task = asyncio.create_task(drain_stream_queue())

  try:
    if not all_frames and streaming_load:
      await asyncio.wait_for(load_complete.wait(), timeout=120.0)
    elif streaming_load:
      # Do not block UI on full background drain — metadata uses partial buffer first.
      pass
    else:
      load_complete.set()

    if not all_frames:
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
      return ws

    first_time = all_frames[0]["time"]
    last_time = all_frames[-1]["time"]
    duration = last_time - first_time
    original_count = len(all_frames)

    init_state = _latest_frames_at_rel(all_frames, start_time, first_time)

    await ws.send_str(json.dumps({
      "type": "metadata",
      "duration": duration,
      "frame_count": len(all_frames),
      "original_frame_count": original_count,
      "decimated": decimated,
      "start_time": first_time,
      "source": source,
      "cached": from_cache,
      "full_can": full_can,
      "has_rlog": bool(rlogs),
      "streaming": streaming_load,
      "snapshots": 0,
      "init_frames": init_state or [],
    }))

    if init_state:
      init_progress = max(0.0, start_time)
      await ws_send({
        "type": "can",
        "frames": init_state,
        "progress": init_progress,
        "preview": True,
      })

    await ws.send_str(json.dumps({
      "type": "loading",
      "phase": "ready",
      "can_frames": len(all_frames),
      "original_frame_count": original_count,
    }))

    await asyncio.sleep(0)

    if streaming_load and drain_task is not None and not load_complete.is_set():
      try:
        await asyncio.wait_for(load_complete.wait(), timeout=90.0)
      except asyncio.TimeoutError:
        pass

    # Stream playback without pre-building the full snapshot list (avoids multi-second stall).
    latest: dict[tuple[int, int], dict[str, Any]] = {}
    prev_sig: dict[tuple[int, int], tuple[float, str]] = {}
    frame_i = 0
    interval = REPLAY_SNAPSHOT_INTERVAL
    next_emit = first_time + max(0.0, start_time)
    playback_start = time.monotonic()
    base_progress = max(0.0, start_time)
    sent_any = False

    def _refresh_bounds() -> tuple[int, float]:
      n_local = len(all_frames)
      if n_local:
        return n_local, float(all_frames[-1]["time"])
      return 0, last_time

    n, last_time = _refresh_bounds()
    while frame_i < n and float(all_frames[frame_i]["time"]) <= next_emit + 1e-6:
      f = all_frames[frame_i]
      latest[(int(f["bus"]), int(f["address"]))] = f
      frame_i += 1

    while True:
      n, last_time = _refresh_bounds()
      if n == 0:
        if load_complete.is_set():
          break
        await asyncio.sleep(0.05)
        continue

      if seek_time_rel is not None:
        st_rel = seek_time_rel
        seek_time_rel = None
        next_emit = first_time + st_rel
        base_progress = st_rel
        frame_i = 0
        latest.clear()
        prev_sig.clear()
        n, _ = _refresh_bounds()
        while frame_i < n and float(all_frames[frame_i]["time"]) <= next_emit + 1e-6:
          f = all_frames[frame_i]
          latest[(int(f["bus"]), int(f["address"]))] = f
          frame_i += 1
        playback_start = time.monotonic()
        await ws.send_str(json.dumps({"type": "seeked", "time": st_rel}))
        seek_state = list(latest.values())
        if seek_state:
          await ws_send({
            "type": "can",
            "frames": _compact_can_batch(seek_state),
            "progress": st_rel,
            "preview": True,
          })
        continue

      if frame_i >= n and next_emit > last_time + interval:
        if streaming_load and not load_complete.is_set():
          await asyncio.sleep(0.02)
          continue
        break

      progress = max(0.0, next_emit - first_time)
      rel = (progress - base_progress) / max(speed, 0.01)
      target = playback_start + rel
      while time.monotonic() < target and not paused:
        await asyncio.sleep(0.01)
      if paused:
        paused_at = time.monotonic()
        while paused:
          await asyncio.sleep(0.05)
        playback_start += time.monotonic() - paused_at
        base_progress = progress

      delta: list[dict[str, Any]] = []
      n, _ = _refresh_bounds()
      while frame_i < n and float(all_frames[frame_i]["time"]) <= next_emit + 1e-6:
        f = all_frames[frame_i]
        k = (int(f["bus"]), int(f["address"]))
        sig = (float(f["time"]), str(f.get("data", "")))
        if prev_sig.get(k) != sig:
          prev_sig[k] = sig
          delta.append(f)
        latest[k] = f
        frame_i += 1

      if not delta and not sent_any and latest:
        delta = list(latest.values())

      if delta:
        sent_any = True
        if not await ws_send({
          "type": "can",
          "frames": _compact_can_batch(delta),
          "progress": progress,
        }):
          break
      elif not await ws_send({"type": "progress", "progress": progress}):
        break

      next_emit += interval
      await asyncio.sleep(0)

    await ws_send({"type": "done"})
  except Exception as e:
    await ws_send({"type": "error", "error": str(e)})
  finally:
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
  return ws
