"""Pure replay timeline helpers (no openpilot / aiohttp imports)."""

from __future__ import annotations

from typing import Any

REPLAY_SNAPSHOT_INTERVAL = 0.25  # ~4 Hz UI updates (delta per address)
REPLAY_MAX_SNAPSHOT_FRAMES = 96


def compact_can_batch(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
  """Keep latest frame per bus+address — enough for the replay table, fewer WS payloads."""
  latest: dict[tuple[int, int], dict[str, Any]] = {}
  for frame in frames:
    latest[(int(frame["bus"]), int(frame["address"]))] = frame
  return list(latest.values())


def latest_frames_at_rel(
  frames: list[dict[str, Any]],
  rel_sec: float,
  first_time: float | None = None,
) -> list[dict[str, Any]]:
  """Latest CAN frame per bus+address at route-relative time (for seek / scrub preview)."""
  if not frames:
    return []
  first_t = float(first_time if first_time is not None else frames[0]["time"])
  cutoff = first_t + max(0.0, float(rel_sec))
  latest: dict[tuple[int, int], dict[str, Any]] = {}
  for frame in frames:
    t = float(frame["time"])
    if t > cutoff + 1e-6:
      break
    latest[(int(frame["bus"]), int(frame["address"]))] = frame
  return list(latest.values())


def build_replay_snapshots(
  frames: list[dict[str, Any]],
  *,
  interval: float = REPLAY_SNAPSHOT_INTERVAL,
) -> list[tuple[float, list[dict[str, Any]]]]:
  """Timeline of CAN deltas: only addresses that changed since last snapshot."""
  if not frames:
    return []
  latest: dict[tuple[int, int], dict[str, Any]] = {}
  prev_sig: dict[tuple[int, int], tuple[float, str]] = {}
  first_t = float(frames[0]["time"])
  last_t = float(frames[-1]["time"])
  snapshots: list[tuple[float, list[dict[str, Any]]]] = []
  next_emit = first_t
  i = 0
  n = len(frames)

  def emit_delta(progress: float) -> None:
    delta: list[dict[str, Any]] = []
    for key, frame in latest.items():
      sig = (float(frame["time"]), str(frame.get("data", "")))
      if prev_sig.get(key) != sig:
        prev_sig[key] = sig
        delta.append(frame)
    if not delta and not snapshots:
      delta = list(latest.values())[:REPLAY_MAX_SNAPSHOT_FRAMES]
      for key, frame in latest.items():
        prev_sig[key] = (float(frame["time"]), str(frame.get("data", "")))
    if delta:
      if len(delta) > REPLAY_MAX_SNAPSHOT_FRAMES:
        delta = delta[:REPLAY_MAX_SNAPSHOT_FRAMES]
      snapshots.append((progress, delta))
    elif snapshots:
      snapshots.append((progress, []))

  while i < n or next_emit <= last_t + 1e-6:
    while i < n and float(frames[i]["time"]) <= next_emit + 1e-6:
      f = frames[i]
      latest[(int(f["bus"]), int(f["address"]))] = f
      i += 1
    if latest:
      emit_delta(next_emit - first_t)
    next_emit += interval
    if i >= n and next_emit > last_t + interval:
      break

  if frames and snapshots:
    final_p = last_t - first_t
    if snapshots[-1][0] < final_p - interval * 0.25:
      emit_delta(final_p)
  return snapshots
