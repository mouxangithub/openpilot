"""Route log/video/time-series tools (tools/lib, tools/scripts)."""

from __future__ import annotations

import base64
import io
import os
from pathlib import Path
from typing import Any

from ai.tools.op_run import ROUTES_DIR, resolve_route_ref, validate_route_ref

_CAMERA_FILES = {
  "front": ("fcamera.hevc", "cameras"),
  "wide": ("ecamera.hevc", "ecameras"),
  "driver": ("dcamera.hevc", "dcameras"),
}

_DEFAULT_SIGNALS = {
  "carState": ["vEgo", "steeringAngleDeg", "gas", "brake", "standstill"],
  "controlsState": ["enabled", "curvature"],
  "carControl": ["latActive", "longActive"],
  "livePose": ["accelerationDevice/x"],
}


def _import_logreader():
  try:
    from openpilot.tools.lib.logreader import LogReader, ReadMode
    return LogReader, ReadMode
  except ImportError:
    from tools.lib.logreader import LogReader, ReadMode  # type: ignore
    return LogReader, ReadMode


def _downsample(series: list, max_points: int) -> list:
  if len(series) <= max_points:
    return series
  step = max(1, len(series) // max_points)
  return series[::step][:max_points]


def _extract_signal(group: dict, path: str) -> list | None:
  if path in group:
    vals = group[path]
    try:
      return [float(x) if x is not None else None for x in list(vals)]
    except (TypeError, ValueError):
      return None
  return None


def route_time_series(
  route: str,
  *,
  topics: list[str] | None = None,
  max_messages: int = 8000,
  max_points: int = 200,
) -> dict[str, Any]:
  err = validate_route_ref(route)
  if err:
    return {"ok": False, "error": err}
  route_arg = resolve_route_ref(route)
  topic_set = set(topics or list(_DEFAULT_SIGNALS.keys()))
  try:
    from openpilot.tools.lib.log_time_series import msgs_to_time_series
    LogReader, ReadMode = _import_logreader()
  except Exception as e:
    return {"ok": False, "error": f"Dependencies unavailable: {e}"}

  try:
    lr = LogReader(route_arg, ReadMode.AUTO)
    batch = []
    scanned = 0
    for msg in lr:
      if scanned >= max_messages:
        break
      scanned += 1
      if msg.which() in topic_set:
        batch.append(msg)
    if not batch:
      return {"ok": False, "error": "No matching messages in route", "route": route_arg}
    ts = msgs_to_time_series(batch)
    out: dict[str, Any] = {}
    for topic in sorted(topic_set):
      if topic not in ts:
        continue
      group = ts[topic]
      times = _downsample(list(group.get("t", [])), max_points)
      signals: dict[str, Any] = {"t": times}
      for sig_path in _DEFAULT_SIGNALS.get(topic, []):
        vals = _extract_signal(group, sig_path)
        if vals is not None:
          signals[sig_path] = _downsample(vals, max_points)
      out[topic] = signals
    return {
      "ok": True,
      "route": route_arg,
      "messages_scanned": scanned,
      "topics": out,
      "script": "tools/lib/log_time_series.py",
      "hint": "Use plotjuggler_data_summary for aggregates; PC: tools/plotjuggler/juggle.py",
    }
  except Exception as e:
    return {"ok": False, "error": str(e), "route": route_arg}


def route_video_info(route_name: str) -> dict[str, Any]:
  if not route_name or ".." in route_name or "/" in route_name or "\\" in route_name:
    return {"ok": False, "error": "Invalid route name"}
  try:
    from ai.cabana import _list_route_media, _route_dir
  except Exception as e:
    return {"ok": False, "error": str(e)}

  base = _route_dir(route_name)
  if base is None:
    return {"ok": False, "error": f"Route not found: {route_name}"}

  media = _list_route_media(route_name)
  segments_detail: list[dict[str, Any]] = []
  total_bytes = 0
  for path in sorted(base.rglob("*")):
    if not path.is_file():
      continue
    low = path.name.lower()
    if low not in ("qcamera.ts", "fcamera.hevc", "ecamera.hevc", "dcamera.hevc"):
      continue
    try:
      size = path.stat().st_size
      total_bytes += size
      frame_count = None
      if low.endswith(".hevc"):
        try:
          from openpilot.tools.lib.framereader import FrameReader
          frame_count = FrameReader(str(path)).frame_count
        except Exception:
          pass
      segments_detail.append({
        "segment": path.parent.name if path.parent != base else "0",
        "file": path.name,
        "size_mb": round(size / (1024 * 1024), 2),
        "frame_count": frame_count,
      })
    except OSError:
      continue

  return {
    "ok": True,
    "route": route_name,
    "media": media,
    "video_files": segments_detail[:40],
    "total_video_mb": round(total_bytes / (1024 * 1024), 2),
    "script": "tools/lib/framereader.py",
    "hint": "Use route_fetch_frame for a still; Cabana UI for qcamera replay.",
  }


def _find_local_video(route_name: str, segment: int, camera: str) -> Path | None:
  base = Path(ROUTES_DIR) / route_name
  if not base.is_dir():
    return None
  fname, _ = _CAMERA_FILES.get(camera, _CAMERA_FILES["front"])
  candidates = list(base.rglob(fname))
  if not candidates:
    return None
  seg_name = str(segment)
  for c in candidates:
    if c.parent.name == seg_name or (seg_name == "0" and c.parent == base):
      return c
  return candidates[0]


def route_fetch_frame(
  route: str,
  *,
  segment: int = 0,
  frame: int = 0,
  camera: str = "front",
  max_width: int = 640,
) -> dict[str, Any]:
  err = validate_route_ref(route)
  if err:
    return {"ok": False, "error": err}

  camera = (camera or "front").lower()
  if camera not in _CAMERA_FILES:
    return {"ok": False, "error": f"camera must be one of: {', '.join(_CAMERA_FILES)}"}

  # Local route folder name
  if "|" not in route and "/" not in route and not route.startswith("/"):
    video_path = _find_local_video(route, segment, camera)
    if video_path and video_path.suffix.lower() == ".hevc":
      try:
        from openpilot.tools.lib.framereader import FrameReader
        from PIL import Image
        fr = FrameReader(str(video_path))
        if frame >= fr.frame_count:
          return {"ok": False, "error": f"frame {frame} out of range (max {fr.frame_count - 1})"}
        arr = fr.get(frame)
        im = Image.fromarray(arr)
        if im.width > max_width:
          ratio = max_width / im.width
          im = im.resize((max_width, int(im.height * ratio)))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return {
          "ok": True,
          "route": route,
          "segment": segment,
          "frame": frame,
          "camera": camera,
          "source": "local",
          "path": str(video_path),
          "frame_count": fr.frame_count,
          "image_jpeg_base64": b64,
          "script": "tools/lib/framereader.py",
        }
      except Exception as e:
        return {"ok": False, "error": str(e)}

  # Cloud API (tools/scripts/fetch_image_from_route.py pattern)
  try:
    import requests
    from PIL import Image
    from openpilot.tools.lib.auth_config import get_token
    from openpilot.tools.lib.framereader import FrameReader
  except Exception as e:
    return {"ok": False, "error": f"Cloud frame fetch unavailable: {e}"}

  token = get_token()
  if not token:
    return {"ok": False, "error": "No comma auth token; run tools/lib/auth.py on dev machine or use local route folder name."}

  _, api_cam = _CAMERA_FILES[camera]
  url = f"https://api.konik.ai/v1/route/{route}/files"
  try:
    r = requests.get(url, headers={"Authorization": f"JWT {token}"}, timeout=30)
    r.raise_for_status()
    segments = r.json().get(api_cam, [])
    if segment >= len(segments):
      return {"ok": False, "error": f"segment {segment} not found ({len(segments)} segments)"}
    fr = FrameReader(segments[segment])
    if frame >= fr.frame_count:
      return {"ok": False, "error": f"frame {frame} out of range (max {fr.frame_count - 1})"}
    im = Image.fromarray(fr.get(frame))
    if im.width > max_width:
      ratio = max_width / im.width
      im = im.resize((max_width, int(im.height * ratio)))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=85)
    return {
      "ok": True,
      "route": route,
      "segment": segment,
      "frame": frame,
      "camera": camera,
      "source": "comma_api",
      "frame_count": fr.frame_count,
      "image_jpeg_base64": base64.b64encode(buf.getvalue()).decode("ascii"),
      "script": "tools/scripts/fetch_image_from_route.py",
    }
  except Exception as e:
    return {"ok": False, "error": str(e), "route": route}


def search_local_routes_for_can(hex_ids: list[str], *, limit: int = 15) -> dict[str, Any]:
  if not hex_ids:
    return {"ok": False, "error": "hex_ids required"}
  want = set()
  for h in hex_ids:
    h = h.strip().lower()
    if h.startswith("0x"):
      want.add(int(h, 16))
    else:
      try:
        want.add(int(h, 16))
      except ValueError:
        return {"ok": False, "error": f"Invalid hex id: {h}"}

  if not os.path.isdir(ROUTES_DIR):
    return {"ok": True, "matches": [], "hint": "No local routes directory"}

  from ai.tools.fingerprint_lib import extract_can_ids_from_route

  entries: list[dict[str, Any]] = []
  names = []
  for name in os.listdir(ROUTES_DIR):
    full = os.path.join(ROUTES_DIR, name)
    if os.path.isdir(full):
      try:
        names.append((os.path.getmtime(full), name))
      except OSError:
        continue
  names.sort(reverse=True)

  for _mtime, name in names[: max(limit * 3, 30)]:
    if len(entries) >= limit:
      break
    res = extract_can_ids_from_route(name, max_frames=4000)
    if not res.get("ok"):
      continue
    observed = res.get("observed") or {}
    obs_int = set()
    for k in observed:
      try:
        obs_int.add(int(k, 16) if isinstance(k, str) else int(k))
      except (TypeError, ValueError):
        pass
    if want.issubset(obs_int):
      entries.append({
        "route": name,
        "unique_ids": res.get("unique_ids"),
        "matched": [f"0x{a:X}" for a in sorted(want)],
      })

  return {
    "ok": True,
    "hex_ids": [f"0x{a:X}" for a in sorted(want)],
    "matches": entries,
    "script": "tools/car_porting/examples/find_segments_with_message.ipynb (local scan)",
    "hint": "For public DB segments use car_porting_search_segments_by_can with platform.",
  }
