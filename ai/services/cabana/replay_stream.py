"""ReplayStream — replay data-state logic implementing the StreamSource protocol.

Extracted from replay_ws so the WS layer only handles throttling and sending.
All frame bookkeeping (latest map, prev_sig dedup, tick consumption) lives here;
the WS message sequence is unchanged.
"""
from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ai.services.cabana import replay as _replay
from ai.services.cabana.replay import (
  REPLAY_FRAME_QUEUE_SIZE,
  REPLAY_START_BUFFER,
)
from ai.services.cabana.replay_util import latest_frames_at_rel as _latest_frames_at_rel
from ai.services.cabana.stream_base import CanFrame, FrameCallback


class ReplayStream:
  """StreamSource implementation backed by qlog/rlog CAN frames."""

  mode = "replay"

  # Dedicated pool for heavy log scans: a stuck/abandoned scan must never
  # starve aid's default executor (video info, decoders, LLM, ...).
  _scan_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="replay-scan")

  def __init__(self, route_name: str, *, full: bool = False, routes_dir: Path | None = None):
    self.route_name = route_name
    self.full = full
    rd = routes_dir if routes_dir is not None else _replay._get_routes_dir()
    self.route_path: Path | None = None
    self.qlogs: list[Path] = []
    self.rlogs: list[Path] = []
    if route_name and rd is not None:
      candidate = rd / route_name
      if candidate.is_dir():
        self.route_path = candidate
        self.qlogs = _replay._find_qlogs(candidate)
        self.rlogs = _replay._find_rlogs(candidate)
      elif candidate.is_file():
        self.route_path = candidate
        self.qlogs = [candidate]

    self.stream_paths: list[Path] = []
    self.source = ""
    if self.qlogs or self.rlogs:
      self.stream_paths, self.source = _replay._replay_log_paths(self.qlogs, self.rlogs, full=full)

    # Loaded data state
    self.all_frames: list[dict[str, Any]] = []
    self.decimated = False
    self.from_cache = False
    self.streaming_load = False
    self.load_complete = asyncio.Event()
    self.frame_queue: asyncio.Queue[Any] | None = None
    self.reader_task: Any = None
    self._cache_task: Any = None
    self.first_time = 0.0
    self.last_time = 0.0

    # Playback state
    self.frame_i = 0
    self.latest: dict[tuple[int, int], dict[str, Any]] = {}
    self.prev_sig: dict[tuple[int, int], tuple[float, str]] = {}
    self._sent_any = False
    self._pending_seek: float | None = None
    self._speed = 1.0
    self._callbacks: list[FrameCallback] = []
    self._abort = threading.Event()

  # -- StreamSource protocol -------------------------------------------------

  def start(self) -> None:
    """No-op: replay loading is driven explicitly via load_async()."""

  def stop(self) -> None:
    """Abort any in-flight load/scan and detach callbacks (session gone)."""
    self._abort.set()
    self._callbacks.clear()

  def messages(self, address: int, t0: float, t1: float) -> list[CanFrame]:
    """Frames matching address with t0 <= time <= t1, sorted by time."""
    frames = [
      f for f in self.all_frames
      if int(f["address"]) == int(address) and t0 <= float(f["time"]) <= t1
    ]
    frames.sort(key=lambda f: float(f["time"]))
    return frames

  def last_msgs(self) -> dict[tuple[int, int], CanFrame]:
    """Latest frame per (bus, address) — from the live playback buffer if primed."""
    if self.latest:
      return dict(self.latest)
    result: dict[tuple[int, int], dict[str, Any]] = {}
    for f in self.all_frames:
      result[(int(f["bus"]), int(f["address"]))] = f
    return result

  def subscribe(self, cb: FrameCallback) -> None:
    if cb not in self._callbacks:
      self._callbacks.append(cb)

  def unsubscribe(self, cb: FrameCallback) -> None:
    if cb in self._callbacks:
      self._callbacks.remove(cb)

  def seek(self, t: float) -> None:
    self._pending_seek = max(0.0, float(t))

  def speed(self, v: float) -> None:
    self._speed = max(0.1, min(10.0, float(v)))

  def take_seek(self) -> float | None:
    """Consume a pending seek request (set via seek() by the control loop)."""
    pending = self._pending_seek
    self._pending_seek = None
    return pending

  # -- loading ----------------------------------------------------------------

  async def load_async(
    self,
    loop: asyncio.AbstractEventLoop,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
  ) -> tuple[str, bool, bool]:
    """Load CAN frames; returns (source, decimated, from_cache).

    Fast path: cached frames or single-pass qlog read. Streaming path: worker
    thread pushes batches through frame_queue while playback starts early.
    """
    cb = progress_cb or (lambda _p: None)
    if self.route_path is not None and self.route_path.is_dir():
      cached = await loop.run_in_executor(
        self._scan_executor,
        lambda: _replay._load_route_cache(self.route_path, want_full=self.full),
      )
      if cached:
        cb({"phase": "cache_hit", "can_frames": len(cached)})
        self.all_frames = list(cached)
        self.decimated = False
        self.from_cache = True
        self._refresh_bounds()
        return self.source, False, True

    # Default fast path: qlog-only, read in one pass (no background drain / no rlog).
    if not self.full and self.source == "qlog":

      def read_qlog_only() -> tuple[list[dict[str, Any]], bool]:
        cb({"phase": "fast_qlog", "files": len(self.stream_paths), "parallel": len(self.stream_paths) > 1})
        return _replay._collect_can_frames(self.stream_paths, cb)

      frames, dec = await loop.run_in_executor(self._scan_executor, read_qlog_only)
      if frames or not self.rlogs:
        self.all_frames = frames
        self.decimated = dec
        self.from_cache = False
        self._refresh_bounds()
        if self.route_path is not None and self.route_path.is_dir() and frames:
          self._cache_task = asyncio.ensure_future(loop.run_in_executor(
            self._scan_executor,
            lambda: _replay._save_route_cache(self.route_path, frames, decimated=dec, full=False),
          ))
        return self.source, dec, False
      # qlog yielded no CAN frames (recent openpilot no longer writes CAN to
      # qlog) — fall back to streaming the rlog instead of failing the session.
      cb({"phase": "qlog_no_can", "rlogs": len(self.rlogs)})
      self.stream_paths = self.rlogs
      self.source = "rlog"

    self.frame_queue = asyncio.Queue(maxsize=REPLAY_FRAME_QUEUE_SIZE)
    self.streaming_load = True
    self.reader_task = loop.run_in_executor(self._scan_executor, self._stream_logs_worker, self.frame_queue, loop, cb)
    partial: list[dict[str, Any]] = []
    while len(partial) < REPLAY_START_BUFFER:
      if self._abort.is_set():
        raise RuntimeError("replay session aborted")
      item = await self.frame_queue.get()
      if item is None:
        break
      if isinstance(item, tuple) and item[0] == "error":
        raise RuntimeError(item[1])
      partial.extend(item)
    self.all_frames = partial
    self.decimated = False
    self.from_cache = False
    self._refresh_bounds()
    return self.source, False, False

  def _stream_logs_worker(
    self,
    frame_queue: asyncio.Queue[Any],
    loop: asyncio.AbstractEventLoop,
    cb: Callable[[dict[str, Any]], None],
  ) -> None:
    """Worker-thread twin of the old stream_logs(): scan logs, push batches."""
    collected: list[dict[str, Any]] = []
    can_total = 0
    decimated_local = False
    state: dict[str, bool] = {}
    aborted = False
    try:
      cb({
        "phase": "fast_rlog" if self.source == "rlog" else "qlog",
        "files": len(self.stream_paths),
        "parallel": len(self.stream_paths) > 1,
      })
      for file_name, batch in _replay._iter_can_batches(self.stream_paths, state=state):
        if self._abort.is_set():
          aborted = True
          break
        collected.extend(batch)
        can_total += len(batch)
        cb({"phase": "scanning", "file": file_name, "can_frames": can_total})
        if not _replay._threadsafe_queue_put(frame_queue, batch, loop, abort=self._abort):
          aborted = True
          break
      if not aborted:
        collected.sort(key=lambda f: f["time"])
        collected, decimated_final = _replay._decimate(collected)
        decimated_local = bool(state.get("decimated")) or decimated_final
        if self.route_path is not None and self.route_path.is_dir() and collected:
          # Mirror replay.py's convention: qlog-derived caches are qlog-only
          # (full=False); anything that read the rlog is cached as full CAN.
          _replay._save_route_cache(self.route_path, collected, decimated=decimated_local, full=(self.source != "qlog"))
    except Exception as e:
      if not self._abort.is_set():
        _replay._threadsafe_queue_put(frame_queue, ("error", str(e)), loop, abort=self._abort, timeout=5.0)
    finally:
      # Always deliver the sentinel so load_async/drain_async can finish.
      if self._abort.is_set():
        # Session is dead: hand the put off asynchronously (a pending put task
        # is harmless; a blocked thread or a missing sentinel is not — without
        # the sentinel the consumer waits out the full load timeout).
        asyncio.run_coroutine_threadsafe(frame_queue.put(None), loop)
      else:
        ok = _replay._threadsafe_queue_put(frame_queue, None, loop, abort=self._abort, timeout=10.0)
        if not ok:
          asyncio.run_coroutine_threadsafe(frame_queue.put(None), loop)

  async def drain_async(self) -> None:
    """Drain the streaming frame queue into all_frames (ex-drain_stream_queue)."""
    if self.frame_queue is None:
      self.load_complete.set()
      return
    while True:
      item = await self.frame_queue.get()
      if item is None:
        break
      if isinstance(item, tuple) and item[0] == "error":
        raise RuntimeError(item[1])
      self.all_frames.extend(item)
    if self.reader_task is not None:
      await self.reader_task
    self.load_complete.set()
    self._refresh_bounds()

  def _refresh_bounds(self) -> None:
    if self.all_frames:
      self.first_time = float(self.all_frames[0]["time"])
      self.last_time = float(self.all_frames[-1]["time"])

  # -- playback bookkeeping -----------------------------------------------------

  def bounds(self) -> tuple[int, float]:
    """(frame_count, last_time) — last_time reflects the streaming buffer growth."""
    self._refresh_bounds()
    if self.all_frames:
      return len(self.all_frames), self.last_time
    return 0, self.last_time

  @property
  def at_end(self) -> bool:
    return self.frame_i >= len(self.all_frames)

  def preview_at(self, rel_sec: float) -> list[dict[str, Any]]:
    """Latest frame per (bus, address) at route-relative time (seek/scrub preview)."""
    return _latest_frames_at_rel(self.all_frames, rel_sec, self.first_time)

  def prime(self, next_emit: float) -> None:
    """Consume frames up to next_emit into the latest buffer without emitting."""
    n = len(self.all_frames)
    while self.frame_i < n and float(self.all_frames[self.frame_i]["time"]) <= next_emit + 1e-6:
      f = self.all_frames[self.frame_i]
      self.latest[(int(f["bus"]), int(f["address"]))] = f
      self.frame_i += 1

  def reset_to(self, next_emit: float) -> list[dict[str, Any]]:
    """Reset playback state to next_emit; returns the snapshot (seek preview)."""
    self.frame_i = 0
    self.latest.clear()
    self.prev_sig.clear()
    self.prime(next_emit)
    return list(self.latest.values())

  def tick(self, next_emit: float) -> tuple[list[dict[str, Any]], float]:
    """Consume frames up to next_emit; returns (delta, progress).

    Delta dedups per (bus, address) via prev_sig; first emission is the full
    snapshot. Registered callbacks receive the delta.
    """
    progress = max(0.0, next_emit - self.first_time)
    n = len(self.all_frames)
    delta: list[dict[str, Any]] = []
    while self.frame_i < n and float(self.all_frames[self.frame_i]["time"]) <= next_emit + 1e-6:
      f = self.all_frames[self.frame_i]
      k = (int(f["bus"]), int(f["address"]))
      sig = (float(f["time"]), str(f.get("data", "")))
      if self.prev_sig.get(k) != sig:
        self.prev_sig[k] = sig
        delta.append(f)
      self.latest[k] = f
      self.frame_i += 1
    if not delta and not self._sent_any and self.latest:
      delta = list(self.latest.values())
    if delta:
      self._sent_any = True
      for cb in list(self._callbacks):
        try:
          cb(delta)
        except Exception:
          pass
    return delta, progress
