"""Carrot navigation auxiliary APIs.

Exposes Param-backed payloads produced by carrot_man:
  - /api/opui/carrot/crossroad   → CarrotNaviCrossroad + CarrotNaviImage (+ carrotNaviMediaSP)
  - /api/opui/carrot/navi_debug  → CarrotNaviDebug
  - /api/opui/carrot/media       → carrotNaviMediaSP frames for tbt/lane/traffic_signal/center

These Params are JSON strings written by CarrotManager; the API only reads
and returns a normalized envelope. The crossroad and media endpoints consume
the SP-namespaced cereal service `carrotNaviMediaSP` for 7714 v2 image frames
(kinds: crossroad, tbt, lane, traffic_signal, center, ...). The media endpoint
additionally falls back to the `CarrotNaviMediaMock` param in PC dev preview so
offline rendering still works.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

from webui.server.bridge.params_api import _params
from webui.server.bridge.state_hub import get_shared_sm


CROSSROAD_PARAM = "CarrotNaviCrossroad"
IMAGE_PARAM = "CarrotNaviImage"
DEBUG_PARAM = "CarrotNaviDebug"
MEDIA_PARAM = "CarrotNaviMediaMock"
MEDIA_SERVICE = "carrotNaviMediaSP"
MEDIA_MAX_AGE_SECONDS = 2.0
MEDIA_CROSSROAD_NAMES = {"crossroad_minimized", "crossroad_expanded"}

# Media kinds the webui consumes, mapped to the carrotNaviMediaSP `name` values
# (see sunnypilot/carrot/carrot_navi.py IMAGE_NAMES). For each kind we prefer the
# first available fresh frame, in priority order.
MEDIA_KIND_NAMES: dict[str, tuple[str, ...]] = {
  "crossroad": ("crossroad_minimized", "crossroad_expanded"),
  "tbt": ("tbt_current_full", "tbt_current_compact", "tbt_next"),
  "lane": ("lane_top", "lane_bottom"),
  "traffic_signal": ("traffic_signal",),
  "center": ("center_tbt_icon", "center_tbt_text", "center_tbt_fee"),
}
MEDIA_ALL_NAMES = tuple(n for _names in MEDIA_KIND_NAMES.values() for n in _names)


def _read_json_param(key: str) -> dict[str, Any] | None:
  p = _params()
  try:
    raw = p.get(key)
  except Exception:
    return None
  if not raw:
    return None
  if isinstance(raw, bytes):
    raw = raw.decode("utf-8", errors="replace")
  try:
    return json.loads(raw)
  except Exception:
    return None


def _frame_from_payload(name, payload, width, height, ts_ns, source_label, fresh=True) -> dict[str, Any] | None:
  """Normalize a raw image payload into the envelope the frontend expects."""
  if payload is None:
    payload = b""
  if isinstance(payload, str):
    payload = payload.encode("utf-8", errors="replace")
  if not payload:
    return None
  try:
    decoded = base64.b64decode(payload, validate=True)
    b64 = payload.decode("ascii") if isinstance(payload, bytes) else payload
    if not decoded:
      b64 = base64.b64encode(payload).decode("ascii")
  except Exception:
    b64 = base64.b64encode(payload).decode("ascii")
  return {
    "show": True,
    "name": name,
    "imageBase64": b64,
    "imageMime": "image/png",
    "imageEncoding": "base64",
    "imageWidth": int(width or 0),
    "imageHeight": int(height or 0),
    "imageHash": "",
    "imageUrl": "",
    "imageTooLarge": False,
    "totalMeters": 0.0,
    "remainRatio": 0.0,
    "ts": int(ts_ns / 1e6) if ts_ns > 0 else 0,
    "receivedMono": ts_ns / 1e9 if ts_ns > 0 else 0.0,
    "source": source_label,
    "fresh": bool(fresh),
  }


def _media_frame_age(ts_ns) -> float:
  if ts_ns <= 0:
    return 0.0
  return time.monotonic() - (ts_ns / 1e9)


def _read_media_frames_by_name(names) -> dict[str, dict[str, Any]]:
  """Return fresh carrotNaviMediaSP frames keyed by `name` for the requested names.

  The SP service only keeps the most recently published frame, so at most one
  `name` will be present unless the publisher batches. The frontend renders each
  returned frame into its kind slot and leaves other slots intact, so as frames
  stream in every kind eventually populates.
  """
  if not names:
    return {}
  sm = get_shared_sm()
  if sm is None:
    return {}
  try:
    if not sm.updated.get(MEDIA_SERVICE) or not sm.valid.get(MEDIA_SERVICE):
      return {}
    frame = sm[MEDIA_SERVICE]
  except Exception:
    return {}

  try:
    kind = str(getattr(frame, "kind", "") or "")
    name = str(getattr(frame, "name", "") or "")
    if kind != "image" or name not in names:
      return {}
    payload = getattr(frame, "payload", None) or b""
    received_ns = int(getattr(frame, "receivedMonoTimeNanos", 0) or 0)
    log_mono_ns = int(getattr(sm, "logMonoTime", {}).get(MEDIA_SERVICE, 0) or 0)
    ts_ns = received_ns if received_ns > 0 else log_mono_ns
    if ts_ns > 0 and _media_frame_age(ts_ns) > MEDIA_MAX_AGE_SECONDS:
      return {}
    out = _frame_from_payload(name, payload, getattr(frame, "width", 0),
                              getattr(frame, "height", 0), ts_ns,
                              f"carrotNaviMediaSP:{name}", fresh=True)
    if out is None:
      return {}
    return {name: out}
  except Exception:
    return {}


def _read_media_frame() -> dict[str, Any] | None:
  """Backward-compatible: latest crossroad image frame from carrotNaviMediaSP."""
  frames = _read_media_frames_by_name(MEDIA_CROSSROAD_NAMES)
  for name in MEDIA_CROSSROAD_NAMES:
    if name in frames:
      return frames[name]
  return None


def _read_mock_media_frames() -> dict[str, dict[str, Any]]:
  """Offline/dev mock frames stored in the ``CarrotNaviMediaMock`` param.

  Used by the PC dev preview (mock_runtime._seed_carrot_navi_params) so the
  media overlays can be demonstrated without a live carrotNaviMediaSP service.
  """
  raw = _read_json_param(MEDIA_PARAM)
  if not raw or not isinstance(raw, dict):
    return {}
  out: dict[str, dict[str, Any]] = {}
  for name, item in raw.items():
    if not isinstance(item, dict) or not item.get("show"):
      continue
    fr = _frame_from_payload(name, item.get("imageBase64", ""),
                             item.get("imageWidth", 0), item.get("imageHeight", 0),
                             0, f"mock:{name}", fresh=True)
    if fr is not None:
      out[name] = fr
  return out


def snapshot_carrot_crossroad() -> dict[str, Any]:
  """Return the latest complex-crossroad metadata and optional image."""
  crossroad = _read_json_param(CROSSROAD_PARAM)
  image = _read_json_param(IMAGE_PARAM)
  frame = _read_media_frame()
  if crossroad is None and image is None and frame is None:
    return {"ok": True, "crossroad": None, "image": None, "frame": None, "has_crossroad": False}

  # Normalize: older crossroad payloads used distanceM / imageCode; keep them.
  out_crossroad = None
  if crossroad is not None:
    out_crossroad = {
      "distanceM": int(crossroad.get("distanceM", 0) or 0),
      "imageCode": int(crossroad.get("imageCode", 0) or 0),
      "imageUrl": str(crossroad.get("imageUrl", "") or ""),
      "totalMeters": float(crossroad.get("totalMeters", 0.0) or 0.0),
      "remainRatio": float(crossroad.get("remainRatio", 0.0) or 0.0),
      "ts": int(crossroad.get("ts", 0) or 0),
    }

  out_image = None
  if image is not None:
    out_image = {
      "show": bool(image.get("show", False)),
      "imageBase64": str(image.get("imageBase64", "") or ""),
      "imageMime": str(image.get("imageMime", "") or ""),
      "imageEncoding": str(image.get("imageEncoding", "") or ""),
      "imageWidth": int(image.get("imageWidth", 0) or 0),
      "imageHeight": int(image.get("imageHeight", 0) or 0),
      "imageHash": str(image.get("imageHash", "") or ""),
      "imageUrl": str(image.get("imageUrl", "") or ""),
      "imageTooLarge": bool(image.get("imageTooLarge", False)),
      "totalMeters": float(image.get("totalMeters", 0.0) or 0.0),
      "remainRatio": float(image.get("remainRatio", 0.0) or 0.0),
      "ts": int(image.get("ts", 0) or 0),
      "receivedMono": float(image.get("receivedMono", 0.0) or 0.0),
    }

  return {
    "ok": True,
    "crossroad": out_crossroad,
    "image": out_image,
    "frame": frame,
    "has_crossroad": out_crossroad is not None,
  }


def snapshot_carrot_navi_debug() -> dict[str, Any]:
  """Return the last handled navi event debug summary."""
  debug = _read_json_param(DEBUG_PARAM)
  if debug is None:
    return {"ok": True, "debug": None, "has_debug": False}
  return {
    "ok": True,
    "debug": {
      "receivedAt": str(debug.get("receivedAt", "") or ""),
      "eventTimeMs": int(debug.get("eventTimeMs", 0) or 0),
      "type": str(debug.get("type", "") or ""),
      "summary": debug.get("summary") if isinstance(debug.get("summary"), dict) else {},
    },
    "has_debug": True,
  }


def snapshot_carrot_media() -> dict[str, Any]:
  """Return the latest carrotNaviMediaSP image frames grouped by media kind.

  Covers ``tbt``, ``lane``, ``traffic_signal`` and ``center`` (plus ``crossroad``
  for completeness). Live SP frames take precedence; missing kinds fall back to
  the ``CarrotNaviMediaMock`` param so the PC preview still renders them.

  The ``frames`` dict is keyed by the raw ``name`` (e.g. ``tbt_current_full``);
  ``byKind`` maps a media kind to the list of its present names. The frontend
  renders each kind into its own slot and leaves untouched slots intact, so a
  single-slot SP service still populates every kind as frames stream in.
  """
  live = _read_media_frames_by_name(set(MEDIA_ALL_NAMES))
  mock = _read_mock_media_frames()

  frames: dict[str, dict[str, Any]] = {}
  by_kind: dict[str, list[str]] = {}
  for kind, names in MEDIA_KIND_NAMES.items():
    present: list[str] = []
    for name in names:
      fr = live.get(name) or mock.get(name)
      if fr is not None:
        frames[name] = fr
        present.append(name)
    if present:
      by_kind[kind] = present

  return {
    "ok": True,
    "frames": frames,
    "byKind": by_kind,
    "has_any": bool(frames),
  }
