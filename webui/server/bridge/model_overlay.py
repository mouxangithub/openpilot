"""Project modelV2 lane/path overlay for web canvas (numpy ModelProjector; no pyray/EGL)."""

from __future__ import annotations

import hashlib
import os
import struct
import threading
import time
from dataclasses import dataclass
from typing import Any

_projector: Any = None
_overlay_sm = None
_cache_lock = threading.Lock()

from webui.server.bridge.cereal_services import OVERLAY_SERVICES, make_submaster

_OVERLAY_SERVICES = list(OVERLAY_SERVICES)

OVERLAY_PARAM_KEYS = frozenset({
  "ChevronInfo",
  "IsMetric",
  "ModelManager_ActiveBundle",
  "CameraOffset",
  "RainbowMode",
  "CarParams",
})

MAX_PATH_GRADIENT_STOPS = 16
_COORD_DECIMALS = 1


class _OverlayParamCache:
  def __init__(self) -> None:
    self._valid = False
    self._chevron_opt = 0
    self._is_metric = False
    self._camera_offset = 0.0
    self._rainbow = False
    self._long_ctrl: bool | None = None

  def invalidate(self) -> None:
    self._valid = False
    self._long_ctrl = None

  def _refresh(self) -> None:
    if self._valid:
      return
    self._chevron_opt = 0
    self._is_metric = False
    self._camera_offset = 0.0
    self._rainbow = False
    try:
      from openpilot.common.params import Params
      from openpilot.cereal import messaging
      from opendbc.car.structs import car

      p = Params()
      self._chevron_opt = int(p.get("ChevronInfo") or 0)
      self._is_metric = p.get_bool("IsMetric")
      if p.get("ModelManager_ActiveBundle"):
        self._camera_offset = float(p.get("CameraOffset", return_default=True))
      self._rainbow = p.get_bool("RainbowMode")
      if car_params := p.get("CarParams"):
        cp = messaging.log_from_bytes(car_params, car.CarParams)
        self._long_ctrl = bool(cp.openpilotLongitudinalControl)
    except Exception:
      pass
    self._valid = True

  def cache_key(self) -> str:
    self._refresh()
    lc = "?" if self._long_ctrl is None else ("1" if self._long_ctrl else "0")
    return (
      f"{self._chevron_opt}|{int(self._is_metric)}|{self._camera_offset:.3f}|"
      f"{int(self._rainbow)}|{lc}"
    )

  @property
  def chevron_opt(self) -> int:
    self._refresh()
    return self._chevron_opt

  @property
  def is_metric(self) -> bool:
    self._refresh()
    return self._is_metric

  @property
  def camera_offset(self) -> float:
    self._refresh()
    return self._camera_offset

  @property
  def rainbow(self) -> bool:
    self._refresh()
    return self._rainbow

  def longitudinal_control(self, sm) -> bool:
    if sm.valid.get("carParams"):
      self._long_ctrl = bool(sm["carParams"].openpilotLongitudinalControl)
      return self._long_ctrl
    if self._long_ctrl is not None:
      return self._long_ctrl
    self._refresh()
    return bool(self._long_ctrl)


_overlay_params = _OverlayParamCache()


@dataclass
class _FrameCacheEntry:
  geom_input_key: tuple[Any, ...]
  geometry_key: str
  frame: dict[str, Any]


_frame_cache: dict[tuple[int, int], _FrameCacheEntry] = {}
_MAX_FRAME_CACHE = 3
_FULL_GEOMETRY_INTERVAL_SEC = 2.0
_last_full_geometry_at = 0.0


def _trim_frame_cache() -> None:
  while len(_frame_cache) > _MAX_FRAME_CACHE:
    _frame_cache.pop(next(iter(_frame_cache)))


def invalidate_overlay_params_cache() -> None:
  _overlay_params.invalidate()
  invalidate_overlay_frame_cache()


def invalidate_overlay_frame_cache() -> None:
  with _cache_lock:
    _frame_cache.clear()


def _empty(w: int, h: int, *, clear: bool = False, frame_key: str | None = None) -> dict[str, Any]:
  fk = frame_key or (f"clear:{w}x{h}" if clear else f"empty:{w}x{h}")
  return {
    "ok": True,
    "width": w,
    "height": h,
    "lanes": [],
    "edges": [],
    "path": [],
    "path_polygon": [],
    "leads": [],
    "experimental": False,
    "rainbow": False,
    "allow_throttle": True,
    "path_blend": 1.0,
    "path_gradient": [],
    "chevron_alpha": 0.0,
    "model_mono_time": 0,
    "geometry_key": fk,
    "anim_key": "0:0.0",
    "frame_key": fk,
    "clear": clear,
    "anim_only": False,
  }


def _quantize(value: float) -> float:
  return round(float(value), _COORD_DECIMALS)


def _quantize_poly(poly: list[Any]) -> list[list[float]]:
  out: list[list[float]] = []
  for pt in poly or []:
    if not pt or len(pt) < 2:
      continue
    out.append([_quantize(pt[0]), _quantize(pt[1])])
  return out


def _limit_gradient(stops: list[dict[str, Any]], max_stops: int = MAX_PATH_GRADIENT_STOPS) -> list[dict[str, Any]]:
  if len(stops) <= max_stops:
    return stops
  if max_stops < 2:
    return stops[:1]
  out: list[dict[str, Any]] = []
  last = len(stops) - 1
  for i in range(max_stops):
    idx = round(i * last / (max_stops - 1))
    out.append(stops[int(idx)])
  return out


def _pack_coords(payload: dict[str, Any]) -> bytes:
  chunks: list[bytes] = [
    struct.pack(
      "!IHHBBB",
      int(payload.get("model_mono_time") or 0),
      int(payload.get("width") or 0),
      int(payload.get("height") or 0),
      int(bool(payload.get("experimental"))),
      int(bool(payload.get("rainbow"))),
      int(bool(payload.get("allow_throttle", True))),
    ),
  ]
  for lane in payload.get("lanes") or []:
    chunks.append(struct.pack("!f", float(lane.get("prob", 0.0))))
    for x, y in lane.get("polygon") or []:
      chunks.append(struct.pack("!ff", float(x), float(y)))
  for edge in payload.get("edges") or []:
    chunks.append(struct.pack("!f", float(edge.get("std", 0.0))))
    for x, y in edge.get("polygon") or []:
      chunks.append(struct.pack("!ff", float(x), float(y)))
  for x, y in payload.get("path_polygon") or []:
    chunks.append(struct.pack("!ff", float(x), float(y)))
  for stop in payload.get("path_gradient") or []:
    rgba = stop.get("rgba") or []
    chunks.append(struct.pack("!f", float(stop.get("pos", 0.0))))
    chunks.extend(struct.pack("!B", int(v)) for v in rgba[:4])
  for lead in payload.get("leads") or []:
    chunks.append(struct.pack("!ff", float(lead.get("alpha", 0)) / 255.0, float(lead.get("d_rel", 0.0))))
    for x, y in lead.get("glow") or []:
      chunks.append(struct.pack("!ff", float(x), float(y)))
    for x, y in lead.get("chevron") or []:
      chunks.append(struct.pack("!ff", float(x), float(y)))
    for m in lead.get("metrics") or []:
      chunks.append(m.encode("utf-8"))
  return b"".join(chunks)


def _digest_geometry(payload: dict[str, Any]) -> str:
  digest = hashlib.md5(_pack_coords(payload)).hexdigest()[:16]
  return digest


def _anim_key(path_blend: float, chevron_alpha: float) -> str:
  return f"{round(float(path_blend), 2)}:{round(float(chevron_alpha), 3)}"


def _assign_frame_keys(payload: dict[str, Any]) -> dict[str, Any]:
  mono = int(payload.get("model_mono_time") or 0)
  digest = _digest_geometry(payload)
  gk = f"{mono}:{digest}"
  ak = _anim_key(payload.get("path_blend", 1.0), payload.get("chevron_alpha", 0.0))
  payload["geometry_key"] = gk
  payload["anim_key"] = ak
  payload["frame_key"] = f"{gk}|{ak}"
  payload.setdefault("anim_only", False)
  payload.setdefault("clear", False)
  return payload


def overlay_frame_key(frame: dict[str, Any]) -> str:
  if frame.get("clear"):
    return str(frame.get("frame_key") or "clear")
  explicit = frame.get("frame_key")
  if explicit:
    return str(explicit)
  return _assign_frame_keys(dict(frame))["frame_key"]


def overlay_geometry_key(frame: dict[str, Any]) -> str:
  return str(frame.get("geometry_key") or overlay_frame_key(frame).split("|", 1)[0])


def overlay_anim_key(frame: dict[str, Any]) -> str:
  if frame.get("anim_key"):
    return str(frame["anim_key"])
  parts = overlay_frame_key(frame).split("|", 1)
  return parts[1] if len(parts) > 1 else "0:0.0"


def _finalize_overlay(payload: dict[str, Any]) -> dict[str, Any]:
  payload["lanes"] = [
    {**lane, "polygon": _quantize_poly(lane.get("polygon") or [])}
    for lane in payload.get("lanes") or []
  ]
  payload["edges"] = [
    {**edge, "polygon": _quantize_poly(edge.get("polygon") or [])}
    for edge in payload.get("edges") or []
  ]
  payload["path"] = _quantize_poly(payload.get("path") or [])
  payload["path_polygon"] = _quantize_poly(payload.get("path_polygon") or [])
  payload["path_gradient"] = _limit_gradient(list(payload.get("path_gradient") or []))
  payload["leads"] = [
    {
      **lead,
      "glow": _quantize_poly(lead.get("glow") or []),
      "chevron": _quantize_poly(lead.get("chevron") or []),
    }
    for lead in payload.get("leads") or []
  ]
  return _assign_frame_keys(payload)


def _get_projector(width: int, height: int):
  global _projector

  if _projector is None:
    from webui.server.bridge.model_projection import ModelProjector
    _projector = ModelProjector(width, height)
  else:
    _projector.set_viewport(width, height)
  return _projector


def _get_overlay_sm():
  global _overlay_sm
  if _overlay_sm is None:
    _overlay_sm = make_submaster(_OVERLAY_SERVICES, poll="modelV2")
  return _overlay_sm


def _resolve_sm():
  """Dedicated SubMaster — do not read state_hub's shared SM (update races)."""
  sm = _get_overlay_sm()
  sm.update(100)
  return sm, True


def _geom_input_key(sm, width: int, height: int, *, use_wide: bool) -> tuple[Any, ...]:
  mono = int(sm["modelV2"].logMonoTime) if sm.valid.get("modelV2") else 0
  calib_frame = int(sm.recv_frame.get("extrinsicsCalibration", 0) or 0)
  road_frame = int(sm.recv_frame.get("narrowRoadCameraState", 0) or 0)
  wide_frame = int(sm.recv_frame.get("wideRoadCameraState", 0) or 0)
  return (mono, width, height, _overlay_params.cache_key(), calib_frame, road_frame, wide_frame, int(use_wide))


def _lead_metrics(lead_data, v_ego: float) -> list[str]:
  try:
    from openpilot.common.constants import CV
    from openpilot.selfdrive.ui.sunnypilot.onroad.chevron_metrics import ChevronOptions

    opt = _overlay_params.chevron_opt
    if opt == ChevronOptions.OFF:
      return []

    is_metric = _overlay_params.is_metric
    d_rel, v_rel = lead_data.dRel, lead_data.vRel
    lines: list[str] = []

    if opt in (ChevronOptions.DISTANCE_ONLY, ChevronOptions.ALL):
      val = max(0.0, d_rel)
      unit = "m" if is_metric else "ft"
      if not is_metric:
        val *= 3.28084
      lines.append(f"{val:.0f} {unit}")

    if opt in (ChevronOptions.SPEED_ONLY, ChevronOptions.ALL):
      multiplier = CV.MS_TO_KPH if is_metric else CV.MS_TO_MPH
      val = max(0.0, (v_rel + v_ego) * multiplier)
      unit = "km/h" if is_metric else "mph"
      lines.append(f"{val:.0f} {unit}")

    if opt in (ChevronOptions.TTC_ONLY, ChevronOptions.ALL):
      val = (d_rel / v_ego) if (d_rel > 0 and v_ego > 0) else 0.0
      lines.append(f"{val:.1f} s" if (0 < val < 200) else "---")

    return lines
  except Exception:
    return []


def _apply_anim_fields(frame: dict[str, Any], anim: dict[str, float]) -> dict[str, Any]:
  gk = str(frame.get("geometry_key") or "")
  path_blend = anim["path_blend"]
  chevron_alpha = anim["chevron_alpha"]
  ak = _anim_key(path_blend, chevron_alpha)
  return {
    "ok": True,
    "width": frame.get("width"),
    "height": frame.get("height"),
    "geometry_key": gk,
    "anim_key": ak,
    "frame_key": f"{gk}|{ak}",
    "model_mono_time": frame.get("model_mono_time", 0),
    "path_blend": path_blend,
    "chevron_alpha": chevron_alpha,
    "anim_only": True,
    "clear": False,
  }


def overlay_wire_payload(frame: dict[str, Any]) -> dict[str, Any]:
  """Shrink frames for WebSocket wire transfer (client merges anim_only locally)."""
  if frame.get("anim_only"):
    return {
      "ok": bool(frame.get("ok", True)),
      "anim_only": True,
      "width": frame.get("width"),
      "height": frame.get("height"),
      "geometry_key": frame.get("geometry_key"),
      "anim_key": frame.get("anim_key"),
      "frame_key": frame.get("frame_key"),
      "path_blend": frame.get("path_blend", 1.0),
      "chevron_alpha": frame.get("chevron_alpha", 0.0),
    }
  if frame.get("clear"):
    return {
      "ok": True,
      "clear": True,
      "width": frame.get("width"),
      "height": frame.get("height"),
      "geometry_key": frame.get("geometry_key"),
      "anim_key": frame.get("anim_key"),
      "frame_key": frame.get("frame_key"),
      "lanes": [],
      "edges": [],
      "path_polygon": [],
      "leads": [],
    }
  return frame


def _build_overlay_frame(sm, width: int, height: int) -> dict[str, Any]:
  model_mono_time = int(sm["modelV2"].logMonoTime) if sm.valid.get("modelV2") else 0

  started = bool(sm.valid.get("deviceState") and sm["deviceState"].started)
  if not started or not sm.valid.get("modelV2"):
    return _finalize_overlay({**_empty(width, height), "model_mono_time": model_mono_time})

  projector = _get_projector(width, height)
  if not projector.update_transform(sm):
    return _finalize_overlay({**_empty(width, height), "model_mono_time": model_mono_time})

  long_ctrl = _overlay_params.longitudinal_control(sm)
  projector.set_longitudinal_control(long_ctrl)
  projector.set_camera_offset(_overlay_params.camera_offset)

  allow_throttle = True
  try:
    if sm.valid.get("longitudinalPlan"):
      allow_throttle = bool(sm["longitudinalPlan"].allowThrottle or not long_ctrl)
  except Exception:
    pass

  rainbow = _overlay_params.rainbow
  experimental_mode = bool(sm["selfdriveState"].experimentalMode) if sm.valid.get("selfdriveState") else False

  overlay = projector.build_overlay(
    sm,
    experimental_mode=experimental_mode,
    allow_throttle=allow_throttle,
    rainbow=rainbow,
    lead_metrics_fn=_lead_metrics,
  )
  if overlay.get("empty"):
    return _finalize_overlay({**_empty(width, height), "model_mono_time": model_mono_time})

  return _finalize_overlay({
    "ok": True,
    "width": width,
    "height": height,
    "lanes": overlay["lanes"],
    "edges": overlay["edges"],
    "path": overlay["path"],
    "path_polygon": overlay["path_polygon"],
    "leads": overlay["leads"],
    "experimental": overlay["experimental"],
    "rainbow": overlay["rainbow"],
    "allow_throttle": overlay["allow_throttle"],
    "path_blend": overlay["path_blend"],
    "path_gradient": overlay["path_gradient"],
    "chevron_alpha": overlay["chevron_alpha"],
    "model_mono_time": model_mono_time,
    "clear": False,
    "anim_only": False,
  })


def snapshot_model_overlay(width: int = 1600, height: int = 900, *, static_mock: bool = False) -> dict[str, Any]:
  if os.environ.get("WEBUI_DEV_PC") == "1":
    return _finalize_overlay(_mock_overlay(width, height, static=static_mock))

  try:
    from webui.server.bridge.state_hub import get_device_thermal
    thermal = get_device_thermal()
    if thermal in ("critical", "danger"):
      return _empty(width, height, clear=True, frame_key=f"thermal:{width}x{height}")
  except Exception:
    pass

  try:
    sm, _owned = _resolve_sm()
    projector = _get_projector(width, height)
    use_wide = projector.sync_camera_mode(sm)
    gkey = _geom_input_key(sm, width, height, use_wide=use_wide)
    wh = (int(width), int(height))

    global _last_full_geometry_at
    now = time.monotonic()
    force_full = (now - _last_full_geometry_at) >= _FULL_GEOMETRY_INTERVAL_SEC

    with _cache_lock:
      entry = _frame_cache.get(wh)

    if entry and entry.geom_input_key == gkey and not force_full:
      projector = _get_projector(width, height)
      long_ctrl = _overlay_params.longitudinal_control(sm)
      allow_throttle = True
      try:
        if sm.valid.get("longitudinalPlan"):
          allow_throttle = bool(sm["longitudinalPlan"].allowThrottle or not long_ctrl)
      except Exception:
        pass
      experimental_mode = bool(sm["selfdriveState"].experimentalMode) if sm.valid.get("selfdriveState") else False
      anim = projector.refresh_anim_state(
        sm,
        experimental_mode=experimental_mode,
        allow_throttle=allow_throttle,
        long_ctrl=long_ctrl,
      )
      return _apply_anim_fields(entry.frame, anim)

    frame = _build_overlay_frame(sm, width, height)
    _last_full_geometry_at = now
    with _cache_lock:
      _frame_cache[wh] = _FrameCacheEntry(
        geom_input_key=gkey,
        geometry_key=str(frame.get("geometry_key") or ""),
        frame={k: v for k, v in frame.items() if k not in ("anim_only",)},
      )
      _trim_frame_cache()
    return frame
  except Exception as exc:
    out = _empty(width, height)
    out["ok"] = False
    out["error"] = str(exc)
    return _finalize_overlay(out)


def _mock_lane_polygon(cx: float, w: float, h: float, offset: float, half_width: float) -> list[list[float]]:
  top_y = h * 0.28
  bot_y = h * 0.96
  top_scale = 0.35
  bot_scale = 1.0
  top_cx = cx + offset * w * top_scale
  bot_cx = cx + offset * w * bot_scale
  tw = half_width * w * top_scale
  bw = half_width * w * bot_scale
  return [
    [bot_cx - bw, bot_y], [bot_cx + bw, bot_y],
    [top_cx + tw, top_y], [top_cx - tw, top_y],
  ]


def _mock_overlay(w: int, h: int, *, static: bool = False) -> dict[str, Any]:
  import time
  cx = w * 0.5
  if static:
    sway = 0.0
    mono = 1
  else:
    sway = 0.012 * (w / 1600.0) * (1.0 + 0.15 * ((time.monotonic() * 0.7) % 2.0 - 1.0))
    mono = int(time.monotonic() * 1e9)
  lanes = []
  for offset, prob, hw in [(-0.14, 0.85, 0.045), (-0.05, 0.9, 0.04), (0.05, 0.9, 0.04), (0.14, 0.85, 0.045)]:
    poly = _mock_lane_polygon(cx, w, h, offset + sway, hw)
    lanes.append({
      "prob": prob,
      "polygon": poly,
      "center": [[(poly[0][0] + poly[1][0]) * 0.25 + (poly[2][0] + poly[3][0]) * 0.25, y]
                 for y in [h * 0.96, h * 0.72, h * 0.48, h * 0.28]],
    })

  path_poly = _mock_lane_polygon(cx, w, h, sway, 0.055)
  path = [
    [(path_poly[0][0] + path_poly[1][0]) / 2, path_poly[0][1]],
    [(path_poly[2][0] + path_poly[3][0]) / 2, (path_poly[0][1] + path_poly[2][1]) / 2],
    [(path_poly[2][0] + path_poly[3][0]) / 2, path_poly[2][1]],
  ]
  lead_cx = cx + w * 0.02 + sway * w
  lead_y = h * 0.44
  lead_s = w * 0.038
  mock_lead = {
    "glow": [
      [lead_cx - lead_s * 1.6, lead_y + lead_s],
      [lead_cx, lead_y - lead_s * 1.2],
      [lead_cx + lead_s * 1.6, lead_y + lead_s],
    ],
    "chevron": [
      [lead_cx - lead_s, lead_y + lead_s * 0.55],
      [lead_cx, lead_y - lead_s * 0.75],
      [lead_cx + lead_s, lead_y + lead_s * 0.55],
    ],
    "alpha": 210,
    "d_rel": 28.5,
    "metrics": ["28m", "-2.1"],
  }
  return {
    "ok": True,
    "width": w,
    "height": h,
    "lanes": lanes,
    "edges": [],
    "path": path,
    "path_polygon": path_poly,
    "leads": [mock_lead],
    "experimental": True,
    "rainbow": False,
    "allow_throttle": True,
    "path_blend": 1.0,
    "path_gradient": [
      {"pos": 0.0, "rgba": [13, 248, 122, 102]},
      {"pos": 0.5, "rgba": [114, 255, 92, 89]},
      {"pos": 1.0, "rgba": [114, 255, 92, 0]},
    ],
    "chevron_alpha": 0.0,
    "model_mono_time": mono,
    "dev_pc": True,
    "clear": False,
    "anim_only": False,
  }
