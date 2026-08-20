"""Headless modelV2 projector for WebUI canvas overlay (no pyray/EGL)."""

from __future__ import annotations

import colorsys
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from openpilot.cereal import log
from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.common.transformations.camera import DEVICE_CAMERAS, view_frame_from_device_frame
from openpilot.common.transformations.orientation import rot_from_euler
from openpilot.selfdrive.locationd.calibrationd import HEIGHT_INIT

CALIBRATED = log.ExtrinsicsCalibration.Status.calibrated
INF_POINT = np.array([1000.0, 0.0, 0.0], dtype=np.float64)
CLIP_MARGIN = 500.0
MIN_DRAW_DISTANCE = 10.0
MAX_DRAW_DISTANCE = 100.0
WIDE_MAX_MS = 10.0
ROAD_MIN_MS = 15.0

THROTTLE_COLORS = [
  (13, 248, 122, 102),
  (114, 255, 92, 89),
  (114, 255, 92, 0),
]
NO_THROTTLE_COLORS = [
  (242, 242, 242, 102),
  (242, 242, 242, 89),
  (242, 242, 242, 0),
]


@dataclass
class _ModelPoints:
  raw_points: np.ndarray = field(default_factory=lambda: np.empty((0, 3), dtype=np.float32))
  projected_points: np.ndarray = field(default_factory=lambda: np.empty((0, 2), dtype=np.float32))


@dataclass
class _LeadVehicle:
  glow: list[tuple[float, float]] = field(default_factory=list)
  chevron: list[tuple[float, float]] = field(default_factory=list)
  fill_alpha: int = 0


class ModelProjector:
  def __init__(self, width: int, height: int, fps: float = 20.0):
    self._width = int(width)
    self._height = int(height)
    self._fps = fps
    self._longitudinal_control = False
    self._camera_offset = 0.0
    self._blend_filter = FirstOrderFilter(1.0, 0.25, 1.0 / fps)
    self._prev_allow_throttle = True
    self._car_space_transform = np.zeros((3, 3), dtype=np.float32)
    self._transform_dirty = True
    self._device_camera = None
    self._view_from_calib = view_frame_from_device_frame.copy()
    self._view_from_wide_calib = view_frame_from_device_frame.copy()
    self._use_wide_camera = False
    self._matrix_cache_key: tuple[Any, ...] = (0, 0, 0, 0)
    self._path_offset_z = HEIGHT_INIT[0]
    self._lane_line_probs = np.zeros(4, dtype=np.float32)
    self._road_edge_stds = np.zeros(2, dtype=np.float32)
    self._acceleration_x = np.empty((0,), dtype=np.float32)
    self._lead_vehicles = [_LeadVehicle(), _LeadVehicle()]
    self._path = _ModelPoints()
    self._lane_lines = [_ModelPoints() for _ in range(4)]
    self._road_edges = [_ModelPoints() for _ in range(2)]
    self._exp_gradient: list[dict[str, Any]] = []
    self._started_frame = 0

  def set_viewport(self, width: int, height: int) -> None:
    w, h = int(width), int(height)
    if w == self._width and h == self._height:
      return
    self._width, self._height = w, h
    self._transform_dirty = True

  def set_longitudinal_control(self, enabled: bool) -> None:
    self._longitudinal_control = bool(enabled)

  def set_camera_offset(self, offset: float) -> None:
    self._camera_offset = float(offset)

  @property
  def use_wide_camera(self) -> bool:
    return self._use_wide_camera

  def sync_camera_mode(self, sm: Any) -> bool:
    self._use_wide_camera = self._pick_wide_camera(sm)
    return self._use_wide_camera

  def _pick_wide_camera(self, sm: Any) -> bool:
    experimental = bool(sm["selfdriveState"].experimentalMode) if sm.valid.get("selfdriveState") else False
    if not experimental:
      return False
    v = float(sm["carState"].vEgo) if sm.valid.get("carState") else 0.0
    if v < WIDE_MAX_MS:
      return True
    if v > ROAD_MIN_MS:
      return False
    return self._use_wide_camera

  def update_transform(self, sm: Any) -> bool:
    started = bool(sm.valid.get("deviceState") and sm["deviceState"].started)
    if not started:
      return False

    if self._started_frame == 0:
      self._started_frame = int(sm.recv_frame.get("deviceState", 0) or 0)

    if sm.recv_frame.get("extrinsicsCalibration", 0) < self._started_frame:
      return False
    if sm.recv_frame.get("modelV2", 0) < self._started_frame:
      return False

    if not self._device_camera and sm.seen.get("narrowRoadCameraState") and sm.seen.get("deviceState"):
      try:
        self._device_camera = DEVICE_CAMERAS[
          (str(sm["deviceState"].deviceType), str(sm["narrowRoadCameraState"].sensor))
        ]
      except Exception:
        self._device_camera = DEVICE_CAMERAS.get(("tici", "ar0231"))

    if not (sm.updated.get("extrinsicsCalibration") and sm.valid.get("extrinsicsCalibration")):
      return self._car_space_transform.any()

    calib = sm["extrinsicsCalibration"]
    if len(calib.rpyCalib) != 3 or calib.calStatus != CALIBRATED:
      return self._car_space_transform.any()

    device_from_calib = rot_from_euler(calib.rpyCalib)
    self._view_from_calib = view_frame_from_device_frame @ device_from_calib
    if hasattr(calib, "wideFromDeviceEuler") and len(calib.wideFromDeviceEuler) == 3:
      wide_from_device = rot_from_euler(calib.wideFromDeviceEuler)
      self._view_from_wide_calib = view_frame_from_device_frame @ wide_from_device @ device_from_calib

    use_wide = self.sync_camera_mode(sm)

    cache_key = (
      sm.recv_frame.get("extrinsicsCalibration", 0),
      self._width,
      self._height,
      int(use_wide),
    )
    if cache_key == self._matrix_cache_key and not self._transform_dirty:
      return True

    if self._device_camera is None:
      self._device_camera = DEVICE_CAMERAS.get(("tici", "ar0231"))

    intrinsic = self._device_camera.wide_road.intrinsics if use_wide else self._device_camera.narrow_road.intrinsics
    calibration = self._view_from_wide_calib if use_wide else self._view_from_calib
    zoom = 2.0 if use_wide else 1.1
    calib_transform = intrinsic @ calibration
    kep = calib_transform @ INF_POINT

    w, h = float(self._width), float(self._height)
    x, y = 0.0, 0.0
    cx, cy = intrinsic[0, 2], intrinsic[1, 2]
    zoom = max(zoom, w / (2 * cx), h / (2 * cy))
    margin = 5.0
    max_x_offset = max(0.0, cx * zoom - w / 2 - margin)
    max_y_offset = max(0.0, cy * zoom - h / 2 - margin)
    try:
      if abs(kep[2]) > 1e-6:
        x_offset = np.clip((kep[0] / kep[2] - cx) * zoom, -max_x_offset, max_x_offset)
        y_offset = np.clip((kep[1] / kep[2] - cy) * zoom, -max_y_offset, max_y_offset)
      else:
        x_offset, y_offset = 0.0, 0.0
    except (ZeroDivisionError, OverflowError):
      x_offset, y_offset = 0.0, 0.0

    video_transform = np.array([
      [zoom, 0.0, (w / 2 + x - x_offset) - (cx * zoom)],
      [0.0, zoom, (h / 2 + y - y_offset) - (cy * zoom)],
      [0.0, 0.0, 1.0],
    ], dtype=np.float64)
    self._car_space_transform = (video_transform @ calib_transform).astype(np.float32)
    self._matrix_cache_key = cache_key
    self._transform_dirty = False
    return True

  def refresh_anim_state(
    self,
    sm: Any,
    *,
    experimental_mode: bool,
    allow_throttle: bool,
    long_ctrl: bool,
  ) -> dict[str, float]:
    self._blend_filter.update(int(allow_throttle))
    path_blend = round(float(self._blend_filter.x), 2)
    chevron_alpha = 0.0
    if long_ctrl and sm.valid.get("radarState"):
      lead = sm["radarState"].leadOne
      if lead and lead.present:
        d_rel = float(lead.dRel)
        v_rel = float(lead.vRel)
        lead_buff = 40.0
        speed_buff = 10.0
        if d_rel < lead_buff:
          chevron_alpha = 1.0 - (d_rel / lead_buff)
          if v_rel < 0:
            chevron_alpha += (-1.0 * (v_rel / speed_buff))
          chevron_alpha = min(chevron_alpha, 1.0)
    return {"path_blend": path_blend, "chevron_alpha": chevron_alpha}

  def build_overlay(
    self,
    sm: Any,
    *,
    experimental_mode: bool,
    allow_throttle: bool,
    rainbow: bool,
    lead_metrics_fn: Callable | None = None,
  ) -> dict[str, Any]:
    if not sm.valid.get("modelV2"):
      return {"empty": True}

    model = sm["modelV2"]
    radar_state = sm["radarState"] if sm.valid.get("radarState") else None
    lead_one = radar_state.leadOne if radar_state else None
    render_lead = self._longitudinal_control and radar_state is not None

    if sm.updated.get("modelV2"):
      self._update_raw_points(model)
    if sm.updated.get("carParams"):
      self._longitudinal_control = bool(sm["carParams"].openpilotLongitudinalControl)

    extrinsics = sm["extrinsicsCalibration"] if sm.valid.get("extrinsicsCalibration") else None
    if extrinsics is not None and extrinsics.height:
      self._path_offset_z = extrinsics.height[0]
    else:
      self._path_offset_z = HEIGHT_INIT[0]

    path_x = self._path.raw_points[:, 0]
    if path_x.size == 0:
      return {"empty": True}

    self._update_model(lead_one, path_x)
    if render_lead:
      self._update_leads(radar_state, path_x)

    lanes = []
    for i, lane in enumerate(self._lane_lines):
      poly = lane.projected_points
      if poly.size == 0:
        continue
      prob = float(self._lane_line_probs[i])
      lanes.append({
        "prob": prob,
        "polygon": poly.tolist(),
        "center": self._poly_centerline(poly),
      })

    edges = []
    for i, edge in enumerate(self._road_edges):
      poly = edge.projected_points
      if poly.size == 0:
        continue
      std = float(self._road_edge_stds[i])
      edges.append({"std": std, "polygon": poly.tolist()})

    path_poly = self._path.projected_points
    path_center = self._path_centerline(path_poly)
    path_gradient = self._path_gradient(experimental_mode, allow_throttle, rainbow, path_poly)

    leads_out = []
    v_ego = float(sm["carState"].vEgo) if sm.valid.get("carState") else 0.0
    for i, lead in enumerate(self._lead_vehicles):
      if not lead.glow or not lead.chevron:
        continue
      metrics: list[str] = []
      if lead_metrics_fn and radar_state:
        ld = radar_state.leadOne if i == 0 else radar_state.leadTwo
        if ld and ld.present:
          try:
            metrics = lead_metrics_fn(ld, v_ego)
          except Exception:
            metrics = []
      leads_out.append({
        "glow": [list(p) for p in lead.glow],
        "chevron": [list(p) for p in lead.chevron],
        "alpha": int(lead.fill_alpha),
        "d_rel": float(radar_state.leadOne.dRel) if i == 0 and radar_state.leadOne else 0.0,
        "metrics": metrics,
      })

    anim = self.refresh_anim_state(
      sm,
      experimental_mode=experimental_mode,
      allow_throttle=allow_throttle,
      long_ctrl=self._longitudinal_control,
    )

    return {
      "empty": False,
      "lanes": lanes,
      "edges": edges,
      "path": path_center,
      "path_polygon": path_poly.tolist() if path_poly.size else [],
      "leads": leads_out,
      "experimental": experimental_mode,
      "rainbow": rainbow,
      "allow_throttle": allow_throttle,
      "path_blend": anim["path_blend"],
      "path_gradient": path_gradient,
      "chevron_alpha": anim["chevron_alpha"],
    }

  def _clip_rect(self) -> tuple[float, float, float, float]:
    return (-CLIP_MARGIN, -CLIP_MARGIN, self._width + 2 * CLIP_MARGIN, self._height + 2 * CLIP_MARGIN)

  def _update_raw_points(self, model) -> None:
    cam = self._camera_offset
    self._path.raw_points = np.array(
      [model.position.x, np.array(model.position.y) + cam, model.position.z], dtype=np.float32,
    ).T
    for i, lane_line in enumerate(model.laneLines):
      self._lane_lines[i].raw_points = np.array(
        [lane_line.x, np.array(lane_line.y) + cam, lane_line.z], dtype=np.float32,
      ).T
    for i, road_edge in enumerate(model.roadEdges):
      self._road_edges[i].raw_points = np.array(
        [road_edge.x, np.array(road_edge.y) + cam, road_edge.z], dtype=np.float32,
      ).T
    self._lane_line_probs = np.array(model.laneLineProbs, dtype=np.float32)
    self._road_edge_stds = np.array(model.roadEdgeStds, dtype=np.float32)
    self._acceleration_x = np.array(model.acceleration.x, dtype=np.float32)

  def _update_model(self, lead, path_x_array: np.ndarray) -> None:
    max_distance = float(np.clip(path_x_array[-1], MIN_DRAW_DISTANCE, MAX_DRAW_DISTANCE))
    max_idx = self._get_path_length_idx(self._lane_lines[0].raw_points[:, 0], max_distance)

    for i, lane in enumerate(self._lane_lines):
      lane.projected_points = self._map_line_to_polygon(
        lane.raw_points, 0.025 * float(self._lane_line_probs[i]), 0.0, max_idx, max_distance,
      )

    for road_edge in self._road_edges:
      road_edge.projected_points = self._map_line_to_polygon(
        road_edge.raw_points, 0.025, 0.0, max_idx, max_distance,
      )

    if lead and lead.present:
      lead_d = lead.dRel * 2.0
      max_distance = float(np.clip(lead_d - min(lead_d * 0.35, 10.0), 0.0, max_distance))

    max_idx = self._get_path_length_idx(path_x_array, max_distance)
    self._path.projected_points = self._map_line_to_polygon(
      self._path.raw_points, 0.9, self._path_offset_z, max_idx, max_distance, allow_invert=False,
    )
    self._update_experimental_gradient()

  def _update_leads(self, radar_state, path_x_array: np.ndarray) -> None:
    self._lead_vehicles = [_LeadVehicle(), _LeadVehicle()]
    leads = [radar_state.leadOne, radar_state.leadTwo]
    rect = (0.0, 0.0, float(self._width), float(self._height))
    for i, lead_data in enumerate(leads):
      if lead_data and lead_data.present:
        d_rel, y_rel, v_rel = lead_data.dRel, lead_data.yRel, lead_data.vRel
        idx = self._get_path_length_idx(path_x_array, d_rel)
        z = self._path.raw_points[idx, 2] if idx < len(self._path.raw_points) else 0.0
        point = self._map_to_screen(d_rel, -y_rel + self._camera_offset, z + self._path_offset_z)
        if point:
          self._lead_vehicles[i] = self._update_lead_vehicle(d_rel, v_rel, point, rect)

  def _update_experimental_gradient(self) -> None:
    self._exp_gradient = []
    pts = self._path.projected_points
    if pts.size == 0:
      return
    h = float(self._height)
    max_len = min(len(pts) // 2, len(self._acceleration_x))
    i = 0
    while i < max_len:
      track_y = pts[i][1]
      if track_y < 0 or track_y > h:
        i += 1
        continue
      lin_grad_point = 1.0 - track_y / h
      path_hue = float(np.clip(60 + self._acceleration_x[i] * 35, 0, 120))
      saturation = min(abs(self._acceleration_x[i] * 1.5), 1.0)
      lightness = float(np.interp(saturation, [0.0, 1.0], [0.95, 0.62]))
      alpha = float(np.interp(lin_grad_point, [0.75 / 2.0, 0.75], [0.4, 0.0]))
      rgb = colorsys.hls_to_rgb(path_hue / 360.0, lightness, saturation)
      self._exp_gradient.append({
        "pos": lin_grad_point,
        "rgba": [int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255), int(alpha * 255)],
      })
      i += 1 + (1 if (i + 2) < max_len else 0)

  def _path_gradient(
    self,
    experimental_mode: bool,
    allow_throttle: bool,
    rainbow: bool,
    path_poly: np.ndarray,
  ) -> list[dict[str, Any]]:
    if experimental_mode and self._exp_gradient:
      return self._exp_gradient
    if rainbow:
      return [{"pos": 0.0, "rgba": [255, 0, 128, 120]}, {"pos": 1.0, "rgba": [0, 200, 255, 0]}]
    blend = round(float(self._blend_filter.x), 2)
    colors = self._blend_rgba(NO_THROTTLE_COLORS, THROTTLE_COLORS, blend)
    return [{"pos": p, "rgba": list(c)} for p, c in zip([0.0, 0.5, 1.0], colors, strict=True)]

  @staticmethod
  def _blend_rgba(begin, end, t: float):
    if t >= 1.0:
      return end
    if t <= 0.0:
      return begin
    inv = 1.0 - t
    return [
      tuple(int(inv * a + t * b) for a, b in zip(start, stop, strict=True))
      for start, stop in zip(begin, end, strict=True)
    ]

  @staticmethod
  def _poly_centerline(poly: np.ndarray) -> list[list[float]]:
    if poly.size == 0:
      return []
    n = len(poly) // 2
    if n < 2:
      return poly.tolist()
    left = poly[:n]
    right = poly[n:][::-1]
    return [[(float(l[0]) + float(r[0])) / 2, (float(l[1]) + float(r[1])) / 2] for l, r in zip(left, right, strict=False)]

  @staticmethod
  def _path_centerline(path_poly: np.ndarray) -> list[list[float]]:
    if path_poly.size == 0:
      return []
    n = len(path_poly) // 2
    if n < 2:
      return path_poly.tolist()
    left = path_poly[:n]
    right = path_poly[n:][::-1]
    mid = [[(float(l[0]) + float(r[0])) / 2, (float(l[1]) + float(r[1])) / 2] for l, r in zip(left, right, strict=False)]
    return [mid[0], mid[len(mid) // 2], mid[-1]] if len(mid) >= 3 else mid

  @staticmethod
  def _get_path_length_idx(pos_x_array: np.ndarray, path_distance: float) -> int:
    if len(pos_x_array) == 0:
      return 0
    indices = np.where(pos_x_array <= path_distance)[0]
    return int(indices[-1]) if indices.size > 0 else 0

  def _map_to_screen(self, in_x, in_y, in_z):
    pt = self._car_space_transform @ np.array([in_x, in_y, in_z], dtype=np.float32)
    if abs(pt[2]) < 1e-6:
      return None
    x, y = float(pt[0] / pt[2]), float(pt[1] / pt[2])
    cx, cy, cw, ch = self._clip_rect()
    if not (cx <= x <= cx + cw and cy <= y <= cy + ch):
      return None
    return (x, y)

  def _map_line_to_polygon(
    self,
    line: np.ndarray,
    y_off: float,
    z_off: float,
    max_idx: int,
    max_distance: float,
    allow_invert: bool = True,
  ) -> np.ndarray:
    if line.shape[0] == 0:
      return np.empty((0, 2), dtype=np.float32)

    points = line[: max_idx + 1]
    if 0 < max_idx < line.shape[0] - 1:
      p0, p1 = line[max_idx], line[max_idx + 1]
      x0, x1 = p0[0], p1[0]
      interp_y = np.interp(max_distance, [x0, x1], [p0[1], p1[1]])
      interp_z = np.interp(max_distance, [x0, x1], [p0[2], p1[2]])
      points = np.concatenate((points, np.array([[max_distance, interp_y, interp_z]], dtype=points.dtype)), axis=0)

    points = points[points[:, 0] >= 0]
    if points.shape[0] == 0:
      return np.empty((0, 2), dtype=np.float32)

    n = points.shape[0]
    offsets = np.array([[0, -y_off, z_off], [0, y_off, z_off]], dtype=np.float32)
    points_3d = (points[None, :, :] + offsets[:, None, :]).reshape(2 * n, 3)
    proj = self._car_space_transform @ points_3d.T
    proj = proj.reshape(3, 2, n)
    left_proj, right_proj = proj[:, 0, :], proj[:, 1, :]
    valid = (np.abs(left_proj[2]) >= 1e-6) & (np.abs(right_proj[2]) >= 1e-6)
    if not np.any(valid):
      return np.empty((0, 2), dtype=np.float32)

    left_screen = left_proj[:2, valid] / left_proj[2, valid][None, :]
    right_screen = right_proj[:2, valid] / right_proj[2, valid][None, :]
    cx, cy, cw, ch = self._clip_rect()
    x_min, x_max, y_min, y_max = cx, cx + cw, cy, cy + ch
    both = (
      (left_screen[0] >= x_min) & (left_screen[0] <= x_max) &
      (left_screen[1] >= y_min) & (left_screen[1] <= y_max) &
      (right_screen[0] >= x_min) & (right_screen[0] <= x_max) &
      (right_screen[1] >= y_min) & (right_screen[1] <= y_max)
    )
    if not np.any(both):
      return np.empty((0, 2), dtype=np.float32)
    left_screen = left_screen[:, both]
    right_screen = right_screen[:, both]
    if not allow_invert and left_screen.shape[1] > 1:
      y = left_screen[1, :]
      keep = y == np.minimum.accumulate(y)
      if not np.any(keep):
        return np.empty((0, 2), dtype=np.float32)
      left_screen = left_screen[:, keep]
      right_screen = right_screen[:, keep]
    return np.vstack((left_screen.T, right_screen[:, ::-1].T)).astype(np.float32)

  def _update_lead_vehicle(self, d_rel, v_rel, point, rect):
    speed_buff, lead_buff = 10.0, 40.0
    fill_alpha = 0
    if d_rel < lead_buff:
      fill_alpha = int(255 * (1.0 - (d_rel / lead_buff)))
      if v_rel < 0:
        fill_alpha += int(255 * (-1 * (v_rel / speed_buff)))
      fill_alpha = min(fill_alpha, 255)
    sz = float(np.clip((25 * 30) / (d_rel / 3 + 30), 15.0, 30.0) * 2.35)
    x = float(np.clip(point[0], 0.0, rect[2] - sz / 2))
    y = float(min(point[1], rect[3] - sz * 0.6))
    g_xo, g_yo = sz / 5, sz / 10
    glow = [(x + (sz * 1.35) + g_xo, y + sz + g_yo), (x, y - g_yo), (x - (sz * 1.35) - g_xo, y + sz + g_yo)]
    chevron = [(x + (sz * 1.25), y + sz), (x, y), (x - (sz * 1.25), y + sz)]
    return _LeadVehicle(glow=glow, chevron=chevron, fill_alpha=fill_alpha)
