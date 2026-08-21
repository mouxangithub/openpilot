"""Driver monitoring arc for Web HUD (mirrors onroad/driver_state.py)."""

from __future__ import annotations

from typing import Any

import numpy as np

DEFAULT_FACE_KPTS_3D = np.array([
  [-5.98, -51.20, 8.00], [-17.64, -49.14, 8.00], [-23.81, -46.40, 8.00], [-29.98, -40.91, 8.00],
  [-32.04, -37.49, 8.00], [-34.10, -32.00, 8.00], [-36.16, -21.03, 8.00], [-36.16, 6.40, 8.00],
  [-35.47, 10.51, 8.00], [-32.73, 19.43, 8.00], [-29.30, 26.29, 8.00], [-24.50, 33.83, 8.00],
  [-19.01, 41.37, 8.00], [-14.21, 46.17, 8.00], [-12.16, 47.54, 8.00], [-4.61, 49.60, 8.00],
  [4.99, 49.60, 8.00], [12.53, 47.54, 8.00], [14.59, 46.17, 8.00], [19.39, 41.37, 8.00],
  [24.87, 33.83, 8.00], [29.67, 26.29, 8.00], [33.10, 19.43, 8.00], [35.84, 10.51, 8.00],
  [36.53, 6.40, 8.00], [36.53, -21.03, 8.00], [34.47, -32.00, 8.00], [32.42, -37.49, 8.00],
  [30.36, -40.91, 8.00], [24.19, -46.40, 8.00], [18.02, -49.14, 8.00], [6.36, -51.20, 8.00],
  [-5.98, -51.20, 8.00],
], dtype=np.float32)

SCALES_POS = np.array([0.9, 0.4, 0.4], dtype=np.float32)
SCALES_NEG = np.array([0.7, 0.4, 0.4], dtype=np.float32)
SVG_CENTER = 96.0
ARC_LENGTH = 133.0
ARC_THICKNESS_DEFAULT = 6.7
ARC_THICKNESS_EXTEND = 12.0
ARC_POINT_COUNT = 37
ARC_ANGLES = np.linspace(0.0, np.pi, ARC_POINT_COUNT, dtype=np.float32)

_pose_vals = np.zeros(3, dtype=np.float32)
_dm_fade_state = 0.0


def reset_dm_state() -> None:
  global _pose_vals, _dm_fade_state
  _pose_vals = np.zeros(3, dtype=np.float32)
  _dm_fade_state = 0.0


def _arc_spline_points(
  delta: float,
  size: float,
  x: float,
  y: float,
  sin_val: float,
  diff_val: float,
  *,
  is_horizontal: bool,
) -> dict[str, Any] | None:
  """Elliptical arc polyline (mirrors driver_state._calculate_arc_data)."""
  if size <= 0:
    return None

  thickness = ARC_THICKNESS_DEFAULT + ARC_THICKNESS_EXTEND * min(1.0, float(diff_val) * 5.0)
  start_angle = (90 if sin_val > 0 else -90) if is_horizontal else (0 if sin_val > 0 else 180)
  if is_horizontal:
    x = min(x + delta, x)
  else:
    y = min(y + delta, y)

  width = size if is_horizontal else ARC_LENGTH
  height = ARC_LENGTH if is_horizontal else size
  angles = ARC_ANGLES + np.deg2rad(start_angle)
  center_x = x + width / 2
  center_y = y + height / 2
  radius_x = width / 2
  radius_y = height / 2
  x_coords = center_x + np.cos(angles) * radius_x
  y_coords = center_y - np.sin(angles) * radius_y
  points = [[float(x_coords[i]), float(y_coords[i])] for i in range(len(x_coords))]
  return {"points": points, "thickness": round(thickness, 1)}


def snapshot_dm_arc(sm: Any, engaged: bool, started_frame: int = 0) -> dict[str, Any] | None:
  """Return DM arc payload in 192×192 SVG coordinates (center 96,96)."""
  global _pose_vals, _dm_fade_state

  try:
    from openpilot.cereal import log

    ss = sm["selfdriveState"]
    alert_size = str(ss.alertSize).split(".")[-1].lower() if ss.alertSize else "none"
    if alert_size not in ("none", ""):
      return None
    if not sm.valid.get("driverStateV2"):
      return None
    if sm.recv_frame.get("driverStateV2", 0) <= started_frame and started_frame > 0:
      return None

    dm_state = sm["driverMonitoringState"] if sm.valid.get("driverMonitoringState") else None
    active = False
    is_rhd = False
    if dm_state is not None:
      active = dm_state.activePolicy == log.DriverMonitoringState.MonitoringPolicy.vision
      is_rhd = bool(getattr(dm_state, "isRHD", False))

    driverstate = sm["driverStateV2"]
    driver_data = driverstate.rightDriverData if is_rhd else driverstate.leftDriverData
    driver_orient = np.array(getattr(driver_data, "faceOrientation", [0, 0, 0]), dtype=np.float32)
    if driver_orient.size < 3:
      driver_orient = np.zeros(3, dtype=np.float32)

    fade_target = 0.0 if active else 0.5
    _dm_fade_state = float(np.clip(_dm_fade_state + 0.2 * (fade_target - _dm_fade_state), 0.0, 1.0))

    scales = np.where(driver_orient < 0, SCALES_NEG, SCALES_POS)
    v_this = driver_orient * scales
    self_pose_diff = np.abs(_pose_vals - v_this)
    _pose_vals = 0.8 * v_this + 0.2 * _pose_vals
    driver_pose_diff = self_pose_diff

    rotation_amount = _pose_vals * (1.0 - _dm_fade_state)
    driver_pose_sins = np.sin(rotation_amount)

    sin_y, sin_x, sin_z = driver_pose_sins
    cos_y, cos_x, cos_z = np.cos(rotation_amount)
    r_xyz = np.array([
      [cos_x * cos_z, cos_x * sin_z, -sin_x],
      [-sin_y * sin_x * cos_z - cos_y * sin_z, -sin_y * sin_x * sin_z + cos_y * cos_z, -sin_y * cos_x],
      [cos_y * sin_x * cos_z - sin_y * sin_z, cos_y * sin_x * sin_z + sin_y * cos_z, cos_y * cos_x],
    ], dtype=np.float32)

    face_kpts = DEFAULT_FACE_KPTS_3D @ r_xyz.T
    face_kpts[:, 2] = face_kpts[:, 2] * (1.0 - _dm_fade_state) + 8 * _dm_fade_state
    kp_depth = (face_kpts[:, 2] - 8) / 120.0 + 1.0
    face_keypoints = face_kpts[:, :2] * kp_depth[:, None]

    outline = [
      [float(SVG_CENTER + face_keypoints[i, 0]), float(SVG_CENTER + face_keypoints[i, 1])]
      for i in range(len(face_keypoints))
    ]

    prob = float(getattr(dm_state, "awareProb", 0) or 0) if dm_state else 0.0
    pose = [float(driver_orient[0]), float(driver_orient[1]), float(driver_orient[2])]

    position_x = SVG_CENTER
    position_y = SVG_CENTER
    delta_x = -float(driver_pose_sins[1]) * ARC_LENGTH / 2.0
    delta_y = -float(driver_pose_sins[0]) * ARC_LENGTH / 2.0
    h_arc = _arc_spline_points(
      delta_x, abs(delta_x), position_x, position_y - ARC_LENGTH / 2,
      float(driver_pose_sins[1]), float(driver_pose_diff[1]), is_horizontal=True,
    )
    v_arc = _arc_spline_points(
      delta_y, abs(delta_y), position_x - ARC_LENGTH / 2, position_y,
      float(driver_pose_sins[0]), float(driver_pose_diff[0]), is_horizontal=False,
    )

    return {
      "visible": True,
      "prob": prob,
      "pose": pose,
      "engaged": engaged,
      "rhd": is_rhd,
      "active": active,
      "face_outline": outline,
      "pose_h": float(min(1.0, abs(driver_pose_sins[1]))),
      "pose_v": float(min(1.0, abs(driver_pose_sins[0]))),
      "arc_thickness_h": (h_arc or {}).get("thickness", ARC_THICKNESS_DEFAULT),
      "arc_thickness_v": (v_arc or {}).get("thickness", ARC_THICKNESS_DEFAULT),
      "h_arc": h_arc,
      "v_arc": v_arc,
      "fade": round(_dm_fade_state, 3),
    }
  except Exception:
    return None
