#!/usr/bin/env python3
"""
IMU-to-vehicle auto-calibration daemon for devices mounted at arbitrary angles.

This daemon replaces calibrationd when the forward-facing camera is physically
separated from the device (C3) and the device may be mounted horizontally or at
any other large orientation.

Calibration procedure:
  1. Static phase: car parked on level ground. Average accelerometer and gyro
     readings to estimate gravity in the device frame and the gyro zero-rate
     bias. This fixes pitch and roll.
  2. Dynamic phase: drive straight. Compare integrated device-frame gyro
     rotation with camera-odometry rotation to solve the remaining yaw rotation
     around gravity.

The result is a full 3x3 rotation matrix R_device_from_vehicle stored in the
ImuCalibrationMatrix param and published via extrinsicsCalibration.imuCalibMatrix.
"""

from __future__ import annotations

import bisect
import json
import math
import time
from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum
from typing import NoReturn

import numpy as np

from openpilot.cereal import log, messaging
from openpilot.common.params import Params
from openpilot.common.realtime import config_realtime_process, Ratekeeper
from openpilot.common.swaglog import cloudlog
from openpilot.common.transformations.orientation import euler_from_rot, sensor_to_device_frame
from openpilot.common.transformations.transformations import axis_angle_to_rot
from opendbc.car.structs import car

# Calibration thresholds
STATIC_MIN_DURATION = 1.5  # seconds of stationary data required
STATIC_MAX_GYRO_STD = 0.05  # rad/s, must be nearly still
STATIC_MAX_SPEED = 0.2  # m/s
STATIC_MIN_SAMPLES = 100
STATIC_MAX_SLOPE_ANGLE = math.radians(5.0)  # reject static calibration on steep slopes

DYNAMIC_MIN_DURATION = 3.0  # seconds of straight driving required
DYNAMIC_MIN_SPEED = 5.0  # m/s
DYNAMIC_MAX_YAW_RATE = 0.10  # rad/s, roughly straight
DYNAMIC_MAX_STEERING_RATE = 10.0  # deg/s
DYNAMIC_MAX_LATERAL_ACCEL = 1.0  # m/s^2
DYNAMIC_MIN_CAMERA_FRAMES = 20
DYNAMIC_MIN_INCREMENTAL_CAMERA_FRAMES = 10  # start publishing an early yaw estimate while still collecting
DYNAMIC_MIN_SAMPLES = int(DYNAMIC_MIN_DURATION * 100.0)  # gyro samples at 100 Hz
DYNAMIC_MAX_INTERRUPTION = 2.0  # allow brief pauses (e.g. traffic lights) without losing the segment
DYNAMIC_TIMEOUT = 300.0  # fail dynamic phase if no successful calibration after this many seconds

CAMERA_ODOM_MAX_ROT_STD = 0.05  # rad/s
CAMERA_ODOM_MAX_TRANS_STD = 0.5  # m/s

YAW_CONVERGENCE_THRESHOLD = math.radians(2.0)  # stop early when yaw estimate is stable
OUTLIER_MAD_THRESHOLD = 3.0  # circular median absolute deviation multiplier
MATRIX_MAX_YAW_DIFF = math.radians(15.0)  # reject final matrix if yaw jumps too far from previous cal
MATRIX_MAX_ROLL_PITCH_DIFF = math.radians(5.0)

# Vehicle frame convention used internally:
#   X = forward, Y = left, Z = up (opposite of gravity)
VEHICLE_GRAVITY = np.array([0.0, 0.0, -1.0])
VEHICLE_FORWARD = np.array([1.0, 0.0, 0.0])


class CalibrationState(StrEnum):
  IDLE = "idle"
  STATIC_COLLECTING = "static_collecting"
  DYNAMIC_COLLECTING = "dynamic_collecting"
  COMPUTING = "computing"
  COMPLETED = "completed"
  FAILED = "failed"
  CANCELLED = "cancelled"


class CalibrationError(StrEnum):
  NONE = "none"
  NOT_STATIONARY = "not_stationary"
  SLOPE_TOO_STEEP = "slope_too_steep"
  NOT_ENOUGH_STATIC_SAMPLES = "not_enough_static_samples"
  NO_STRAIGHT_ROAD = "no_straight_road"
  TIMEOUT = "timeout"
  CAMERA_ODOMETRY_UNRELIABLE = "camera_odometry_unreliable"
  COMPUTATION_FAILED = "computation_failed"
  MATRIX_INVALID = "matrix_invalid"


class SlopeTooSteepError(ValueError):
  """Raised when the static phase detects a non-level ground plane."""


@dataclass
class CalibrationStatus:
  state: CalibrationState = CalibrationState.IDLE
  progress: int = 0
  error: str | None = None
  error_code: CalibrationError = CalibrationError.NONE
  static_samples: int = 0
  dynamic_samples: int = 0
  yaw_std: float = 0.0
  valid_ratio: float = 0.0

  def to_json(self) -> str:
    return json.dumps({
      "state": self.state.value,
      "progress": self.progress,
      "error": self.error,
      "errorCode": self.error_code.value,
      "static_samples": self.static_samples,
      "dynamic_samples": self.dynamic_samples,
      "yaw_std": self.yaw_std,
      "valid_ratio": self.valid_ratio,
    })

  @classmethod
  def from_json(cls, data: str) -> CalibrationStatus:
    d = json.loads(data)
    return cls(
      state=CalibrationState(d.get("state", "idle")),
      progress=d.get("progress", 0),
      error=d.get("error"),
      error_code=CalibrationError(d.get("errorCode", "none")),
      static_samples=d.get("static_samples", 0),
      dynamic_samples=d.get("dynamic_samples", 0),
      yaw_std=d.get("yaw_std", 0.0),
      valid_ratio=d.get("valid_ratio", 0.0),
    )


@dataclass
class StaticBuffer:
  acc: deque[np.ndarray] = field(default_factory=lambda: deque(maxlen=STATIC_MIN_SAMPLES * 2))
  gyro: deque[np.ndarray] = field(default_factory=lambda: deque(maxlen=STATIC_MIN_SAMPLES * 2))
  ts: deque[float] = field(default_factory=lambda: deque(maxlen=STATIC_MIN_SAMPLES * 2))

  def clear(self) -> None:
    self.acc.clear()
    self.gyro.clear()
    self.ts.clear()

  def append(self, acc: np.ndarray, gyro: np.ndarray, ts: float) -> None:
    self.acc.append(acc)
    self.gyro.append(gyro)
    self.ts.append(ts)

  def __len__(self) -> int:
    return len(self.acc)


@dataclass
class GyroBuffer:
  gyro: deque[np.ndarray] = field(default_factory=lambda: deque(maxlen=int(DYNAMIC_MIN_DURATION * 100.0 * 4)))
  ts: deque[float] = field(default_factory=lambda: deque(maxlen=int(DYNAMIC_MIN_DURATION * 100.0 * 4)))

  def clear(self) -> None:
    self.gyro.clear()
    self.ts.clear()

  def append(self, gyro: np.ndarray, ts: float) -> None:
    self.gyro.append(gyro)
    self.ts.append(ts)

  def __len__(self) -> int:
    return len(self.gyro)


@dataclass
class DynamicSegment:
  gyro_ts: list[float] = field(default_factory=list)
  gyro_samples: list[np.ndarray] = field(default_factory=list)
  cam_rot: list[np.ndarray] = field(default_factory=list)
  cam_ts: list[float] = field(default_factory=list)

  def clear(self) -> None:
    self.gyro_ts.clear()
    self.gyro_samples.clear()
    self.cam_rot.clear()
    self.cam_ts.clear()

  def __len__(self) -> int:
    return len(self.gyro_ts)

  def duration(self) -> float:
    if len(self) < 2:
      return 0.0
    return self.gyro_ts[-1] - self.gyro_ts[0]


def is_stationary(car_state: car.CarState) -> bool:
  return abs(car_state.vEgo) < STATIC_MAX_SPEED


def is_straight_drive(car_state: car.CarState, cam_odom: log.CameraOdometry | None) -> bool:
  if car_state.vEgo < DYNAMIC_MIN_SPEED:
    return False
  if cam_odom is None or len(cam_odom.rot) < 3:
    return False
  if abs(cam_odom.rot[2]) >= DYNAMIC_MAX_YAW_RATE:
    return False

  # Reject camera-odometry frames with low confidence.
  if len(cam_odom.rotStd) >= 3 and any(s >= CAMERA_ODOM_MAX_ROT_STD for s in cam_odom.rotStd):
    return False
  if len(cam_odom.transStd) >= 3 and any(s >= CAMERA_ODOM_MAX_TRANS_STD for s in cam_odom.transStd):
    return False

  # Reject aggressive steering or high lateral acceleration.
  if abs(car_state.steeringRateDeg) > DYNAMIC_MAX_STEERING_RATE:
    return False
  lateral_accel = abs(car_state.yawRate * car_state.vEgo)
  if lateral_accel > DYNAMIC_MAX_LATERAL_ACCEL:
    return False

  return True


def compute_static_rotation(acc_samples: list[np.ndarray], gyro_samples: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
  """
  Compute pitch/roll rotation from the accelerometer specific-force and the gyro bias.

  A stationary accelerometer measures the specific-force opposing gravity,
  i.e. the vehicle-up direction in the device frame. This fixes pitch and roll;
  yaw remains unknown and is set to zero.

  Returns (R_device_from_vehicle_with_zero_yaw, gyro_bias).
  """
  # Accelerometer specific-force points opposite to gravity (vehicle up).
  up_device = np.mean(acc_samples, axis=0)
  norm = np.linalg.norm(up_device)
  if norm < 1e-6:
    raise ValueError("accelerometer samples are near zero")
  up_device = up_device / norm

  # Check that the vehicle is on reasonably level ground.
  cos_angle = float(np.dot(up_device, VEHICLE_GRAVITY))
  slope = math.acos(max(-1.0, min(1.0, cos_angle)))
  if slope > STATIC_MAX_SLOPE_ANGLE:
    raise SlopeTooSteepError(f"ground slope too steep: {math.degrees(slope):.1f} deg")

  gyro_bias = np.mean(gyro_samples, axis=0)

  # Columns of R are vehicle axes expressed in device frame. The third column
  # is vehicle Z-up, which equals the accelerometer specific-force direction.
  z_d = up_device.copy()
  # Vehicle X-forward is the projection of an assumed forward vector onto the
  # plane perpendicular to up. Yaw is arbitrary here and refined dynamically.
  x_d = VEHICLE_FORWARD - np.dot(VEHICLE_FORWARD, z_d) * z_d
  x_norm = np.linalg.norm(x_d)
  if x_norm < 1e-6:
    # Device up axis is aligned with vehicle forward; pick an arbitrary perpendicular
    x_d = np.array([1.0, 0.0, 0.0]) if abs(z_d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    x_d = x_d - np.dot(x_d, z_d) * z_d
    x_norm = np.linalg.norm(x_d)
  x_d = x_d / x_norm

  y_d = np.cross(z_d, x_d)
  y_norm = np.linalg.norm(y_d)
  if y_norm < 1e-6:
    raise ValueError("cannot construct y axis from gravity and forward")
  y_d = y_d / y_norm

  # Columns of R are vehicle axes expressed in device frame
  R = np.column_stack([x_d, y_d, z_d])
  return R, gyro_bias


def _interpolate_gyro(gyro_ts: list[float], gyro_samples: list[np.ndarray], t: float, bias: np.ndarray) -> np.ndarray:
  """Return gyro reading (bias-subtracted) linearly interpolated to time t."""
  if not gyro_ts:
    return np.zeros(3)
  if t <= gyro_ts[0]:
    return np.array(gyro_samples[0]) - bias
  if t >= gyro_ts[-1]:
    return np.array(gyro_samples[-1]) - bias

  idx = bisect.bisect_right(gyro_ts, t)
  if idx == 0:
    return np.array(gyro_samples[0]) - bias
  t0, t1 = gyro_ts[idx - 1], gyro_ts[idx]
  if t1 == t0:
    return np.array(gyro_samples[idx - 1]) - bias
  alpha = (t - t0) / (t1 - t0)
  g0 = np.array(gyro_samples[idx - 1]) - bias
  g1 = np.array(gyro_samples[idx]) - bias
  return g0 + alpha * (g1 - g0)


def integrate_gyro(
  gyro_ts: list[float],
  gyro_samples: list[np.ndarray],
  t0: float,
  t1: float,
  bias: np.ndarray | None = None,
) -> np.ndarray:
  """Integrate gyro readings between t0 and t1 using trapezoidal rule with boundary interpolation."""
  if len(gyro_ts) < 2 or t1 <= t0:
    return np.zeros(3)

  bias = np.zeros(3) if bias is None else np.asarray(bias)

  start_idx = bisect.bisect_left(gyro_ts, t0)
  end_idx = bisect.bisect_right(gyro_ts, t1) - 1

  # If no samples fall inside the interval, approximate from the interpolated endpoints.
  if start_idx > end_idx:
    g0 = _interpolate_gyro(gyro_ts, gyro_samples, t0, bias)
    g1 = _interpolate_gyro(gyro_ts, gyro_samples, t1, bias)
    return 0.5 * (g0 + g1) * (t1 - t0)

  rot = np.zeros(3)
  prev_t = t0
  prev_g = _interpolate_gyro(gyro_ts, gyro_samples, t0, bias)

  for i in range(start_idx, end_idx + 1):
    ts_i = gyro_ts[i]
    if ts_i < t0 or ts_i > t1:
      continue
    g_i = np.array(gyro_samples[i]) - bias
    dt = ts_i - prev_t
    if dt > 0.0:
      rot += 0.5 * (prev_g + g_i) * dt
    prev_t = ts_i
    prev_g = g_i

  # Close the interval to t1.
  if t1 > prev_t:
    g1 = _interpolate_gyro(gyro_ts, gyro_samples, t1, bias)
    rot += 0.5 * (prev_g + g1) * (t1 - prev_t)

  return rot


def compute_yaw_correction(
  R_static: np.ndarray,
  gyro_bias: np.ndarray,
  gyro_ts: list[float],
  gyro_samples: list[np.ndarray],
  cam_rot_samples: list[np.ndarray],
  cam_ts: list[float],
  min_camera_frames: int = DYNAMIC_MIN_CAMERA_FRAMES,
) -> tuple[float, float, float]:
  """
  Solve for the yaw rotation around gravity that aligns predicted device
  rotation (from camera odometry) with integrated gyro rotation.

  Returns (yaw angle in radians, yaw standard deviation, inlier ratio).
  """
  # cameraOdometry.rot is expressed in the calibration frame. During IMU
  # calibration we publish rpyCalib so that the calibration frame coincides
  # with the temporary vehicle frame defined by R_static (yaw=0). Therefore
  # msg.rot can be treated as a vehicle-frame rotation. We predict the
  # corresponding device-frame rotation with R_static and compare it to the
  # integrated gyro rotation, both projected onto the plane perpendicular to
  # vehicle gravity.
  z_axis = R_static @ VEHICLE_GRAVITY
  z_axis = z_axis / np.linalg.norm(z_axis)

  diffs: list[float] = []
  weights: list[float] = []

  for i in range(1, len(cam_ts)):
    t0 = cam_ts[i - 1]
    t1 = cam_ts[i]
    dt = t1 - t0
    if dt <= 0 or dt > 1.0:
      continue

    # Camera rotation vector over this interval in the calibration/vehicle frame
    cam_rot_vehicle = cam_rot_samples[i - 1]
    if len(cam_rot_vehicle) < 3:
      continue

    # Predicted device rotation = R_static * vehicle rotation
    pred_rot = R_static @ np.array(cam_rot_vehicle)

    # Measured device rotation = integrated gyro minus bias
    meas_rot = integrate_gyro(gyro_ts, gyro_samples, t0, t1, gyro_bias)

    # Project onto x-y plane (perpendicular to gravity)
    pred_xy = pred_rot - np.dot(pred_rot, z_axis) * z_axis
    meas_xy = meas_rot - np.dot(meas_rot, z_axis) * z_axis

    p_norm = np.linalg.norm(pred_xy)
    m_norm = np.linalg.norm(meas_xy)
    if p_norm < 1e-6 or m_norm < 1e-6:
      continue

    pred_angle = math.atan2(pred_xy[1], pred_xy[0])
    meas_angle = math.atan2(meas_xy[1], meas_xy[0])
    diffs.append(meas_angle - pred_angle)
    weights.append(dt)

  if len(diffs) < min_camera_frames:
    raise ValueError(f"insufficient dynamic samples: {len(diffs)}")

  diffs_arr = np.array(diffs)
  weights_arr = np.array(weights)

  # Circular outlier rejection using median absolute deviation.
  median_sin = float(np.median(np.sin(diffs_arr)))
  median_cos = float(np.median(np.cos(diffs_arr)))
  median_diff = math.atan2(median_sin, median_cos)
  centered = np.arctan2(np.sin(diffs_arr - median_diff), np.cos(diffs_arr - median_diff))
  mad = max(float(np.median(np.abs(centered))), 1e-9)
  inlier_mask = np.abs(centered) < OUTLIER_MAD_THRESHOLD * mad

  if int(np.sum(inlier_mask)) < min_camera_frames:
    raise ValueError(f"too many outliers: {int(np.sum(inlier_mask))} inliers")

  # Circular weighted mean of inliers.
  sin_in = np.average(np.sin(diffs_arr[inlier_mask]), weights=weights_arr[inlier_mask])
  cos_in = np.average(np.cos(diffs_arr[inlier_mask]), weights=weights_arr[inlier_mask])
  resultant = math.hypot(sin_in, cos_in)
  yaw = math.atan2(sin_in, cos_in)
  yaw_std = math.sqrt(max(-2.0 * math.log(max(resultant, 1e-9)), 0.0))
  valid_ratio = float(np.sum(inlier_mask)) / len(diffs_arr)

  return yaw, yaw_std, valid_ratio


def _orthonormalize(R: np.ndarray) -> np.ndarray:
  """Project a 3x3 matrix onto SO(3)."""
  U, _, Vt = np.linalg.svd(R)
  R_out = U @ Vt
  if np.linalg.det(R_out) < 0:
    U[:, -1] *= -1
    R_out = U @ Vt
  return R_out


class ImuCalibrator:
  def __init__(self, params: Params | None = None) -> None:
    self.params = params or Params()
    self.status = CalibrationStatus()
    self.state = CalibrationState.IDLE
    self.static_buffer = StaticBuffer()
    self.dynamic_gyro = GyroBuffer()
    self.dynamic_segments: list[DynamicSegment] = []
    self.current_segment = DynamicSegment()
    self.R_static: np.ndarray | None = None
    self.gyro_bias: np.ndarray | None = None
    self.last_cam_odom: log.CameraOdometry | None = None
    self.last_cam_ts: float | None = None
    self.last_straight_ts: float | None = None
    self.dynamic_start_ts: float | None = None
    self._cached_incremental_rotation: np.ndarray | None = None
    self._cached_incremental_dirty = True
    self._last_loaded_matrix: np.ndarray | None = None
    self._last_loaded_matrix_ts: float = 0.0

  def reset(self) -> None:
    self.state = CalibrationState.IDLE
    self.static_buffer.clear()
    self.dynamic_gyro.clear()
    self.dynamic_segments.clear()
    self.current_segment.clear()
    self.R_static = None
    self.gyro_bias = None
    self.last_cam_odom = None
    self.last_cam_ts = None
    self.last_straight_ts = None
    self.dynamic_start_ts = None
    self._cached_incremental_rotation = None
    self._cached_incremental_dirty = True
    self._last_loaded_matrix = None
    self._last_loaded_matrix_ts = 0.0
    self.status = CalibrationStatus(state=CalibrationState.IDLE)

  def _set_state(self, state: CalibrationState, error: str | None = None) -> None:
    self.state = state
    self.status.state = state
    self.status.error = error
    cloudlog.info(f"IMU calibration state: {state.value}" + (f" error={error}" if error else ""))

  def _set_error(self, error_code: CalibrationError, message: str) -> None:
    self.status.error_code = error_code
    self._set_state(CalibrationState.FAILED, message)

  def _save_status(self) -> None:
    try:
      self.params.put("ImuCalibrationStatus", self.status.to_json())
    except Exception:
      cloudlog.exception("Failed to save ImuCalibrationStatus")

  def _save_matrix(self, R: np.ndarray) -> None:
    if R.shape != (3, 3):
      raise ValueError("rotation matrix must be 3x3")
    det = float(np.linalg.det(R))
    if not (0.99 < det < 1.01):
      raise ValueError(f"rotation matrix determinant invalid: {det}")
    self.params.put("ImuCalibrationMatrix", R.astype(np.float32).tobytes(), block=True)
    self._last_loaded_matrix = R.copy()
    self._last_loaded_matrix_ts = time.monotonic()
    cloudlog.info("Saved ImuCalibrationMatrix")

  def _load_matrix(self) -> np.ndarray | None:
    # Cache the param read for a few seconds to avoid disk/IPC pressure.
    if self._last_loaded_matrix is not None and time.monotonic() - self._last_loaded_matrix_ts < 5.0:
      return self._last_loaded_matrix

    data = self.params.get("ImuCalibrationMatrix")
    if data is None or len(data) != 36:
      self._last_loaded_matrix = None
      return None
    try:
      R = np.frombuffer(data, dtype=np.float32).reshape(3, 3)
      self._last_loaded_matrix = R
      self._last_loaded_matrix_ts = time.monotonic()
      return R
    except Exception:
      cloudlog.exception("Failed to load ImuCalibrationMatrix")
      self._last_loaded_matrix = None
      return None

  def _collect_dynamic_samples(self) -> tuple[list[float], list[np.ndarray], list[np.ndarray], list[float]]:
    """Flatten all dynamic segments + current segment into chronological lists."""
    gyro_ts: list[float] = []
    gyro_samples: list[np.ndarray] = []
    cam_ts: list[float] = []
    cam_rot: list[np.ndarray] = []

    all_segments = self.dynamic_segments + ([self.current_segment] if len(self.current_segment) > 0 else [])
    for segment in all_segments:
      gyro_ts.extend(segment.gyro_ts)
      gyro_samples.extend(segment.gyro_samples)
      cam_ts.extend(segment.cam_ts)
      cam_rot.extend(segment.cam_rot)

    return gyro_ts, gyro_samples, cam_rot, cam_ts

  def _total_dynamic_duration(self) -> float:
    duration = sum(s.duration() for s in self.dynamic_segments)
    if len(self.current_segment) > 1:
      duration += self.current_segment.duration()
    return duration

  def _total_dynamic_samples(self) -> int:
    return sum(len(s) for s in self.dynamic_segments) + len(self.current_segment)

  def get_incremental_rotation(self) -> np.ndarray | None:
    """Estimate yaw from data collected so far and return a full rotation matrix.

    Returns None if there is not enough straight-driving data yet to estimate
    yaw reliably.
    """
    if self.R_static is None or self.gyro_bias is None:
      return None
    if not self._cached_incremental_dirty and self._cached_incremental_rotation is not None:
      return self._cached_incremental_rotation

    gyro_ts, gyro_samples, cam_rot, cam_ts = self._collect_dynamic_samples()
    if len(cam_ts) < DYNAMIC_MIN_INCREMENTAL_CAMERA_FRAMES:
      return None

    try:
      yaw, yaw_std, valid_ratio = compute_yaw_correction(
        self.R_static,
        self.gyro_bias,
        gyro_ts,
        gyro_samples,
        cam_rot,
        cam_ts,
        min_camera_frames=DYNAMIC_MIN_INCREMENTAL_CAMERA_FRAMES,
      )
    except Exception:
      return None

    self.status.yaw_std = yaw_std
    self.status.valid_ratio = valid_ratio
    z_axis = self.R_static @ VEHICLE_GRAVITY
    z_axis = z_axis / np.linalg.norm(z_axis)
    R_yaw = axis_angle_to_rot(z_axis, yaw)
    R = _orthonormalize(R_yaw @ self.R_static)
    self._cached_incremental_rotation = R
    self._cached_incremental_dirty = False
    return R

  def _build_extrinsics_msg(
    self,
    R: np.ndarray | None = None,
    status: log.ExtrinsicsCalibration.Status = log.ExtrinsicsCalibration.Status.uncalibrated,
    progress: int = 0,
    include_matrix: bool = True,
  ) -> log.Event:
    msg = messaging.new_message("extrinsicsCalibration")
    msg.valid = True
    ec = msg.extrinsicsCalibration
    ec.calStatus = status
    ec.calPerc = progress
    ec.validBlocks = 1 if status == log.ExtrinsicsCalibration.Status.calibrated else 0
    ec.rpyCalibSpread = [0.0, 0.0, 0.0]
    ec.wideFromDeviceEuler = [0.0, 0.0, 0.0]
    ec.height = [1.22]
    if R is not None:
      ec.rpyCalib = euler_from_rot(R).tolist()
      if include_matrix:
        ec.imuCalibMatrix = R.astype(np.float32).flatten().tolist()
    else:
      ec.rpyCalib = [0.0, 0.0, 0.0]
    return msg

  def _build_imu_calibration_sp_msg(self, R: np.ndarray | None = None) -> log.Event:
    msg = messaging.new_message("imuCalibrationSP")
    msg.valid = True
    ic = msg.imuCalibrationSP
    ic.status = self._to_sp_status(self.state)
    ic.progress = self.status.progress
    ic.error = self._to_sp_error(self.status.error_code)
    if R is not None:
      ic.rpyCalib = euler_from_rot(R).tolist()
      ic.imuCalibMatrix = R.astype(np.float32).flatten().tolist()
    else:
      ic.rpyCalib = [0.0, 0.0, 0.0]
      ic.imuCalibMatrix = []
    ic.yawStd = self.status.yaw_std
    ic.validRatio = self.status.valid_ratio
    return msg

  @staticmethod
  def _to_sp_status(state: CalibrationState) -> log.ImuCalibrationSP.Status:
    mapping = {
      CalibrationState.IDLE: log.ImuCalibrationSP.Status.idle,
      CalibrationState.STATIC_COLLECTING: log.ImuCalibrationSP.Status.staticCollecting,
      CalibrationState.DYNAMIC_COLLECTING: log.ImuCalibrationSP.Status.dynamicCollecting,
      CalibrationState.COMPUTING: log.ImuCalibrationSP.Status.computing,
      CalibrationState.COMPLETED: log.ImuCalibrationSP.Status.completed,
      CalibrationState.FAILED: log.ImuCalibrationSP.Status.failed,
      CalibrationState.CANCELLED: log.ImuCalibrationSP.Status.cancelled,
    }
    return mapping.get(state, log.ImuCalibrationSP.Status.idle)

  @staticmethod
  def _to_sp_error(error_code: CalibrationError) -> log.ImuCalibrationSP.Error:
    mapping = {
      CalibrationError.NONE: log.ImuCalibrationSP.Error.none,
      CalibrationError.NOT_STATIONARY: log.ImuCalibrationSP.Error.notStationary,
      CalibrationError.SLOPE_TOO_STEEP: log.ImuCalibrationSP.Error.slopeTooSteep,
      CalibrationError.NOT_ENOUGH_STATIC_SAMPLES: log.ImuCalibrationSP.Error.notEnoughStaticSamples,
      CalibrationError.NO_STRAIGHT_ROAD: log.ImuCalibrationSP.Error.noStraightRoad,
      CalibrationError.TIMEOUT: log.ImuCalibrationSP.Error.timeout,
      CalibrationError.CAMERA_ODOMETRY_UNRELIABLE: log.ImuCalibrationSP.Error.cameraOdometryUnreliable,
      CalibrationError.COMPUTATION_FAILED: log.ImuCalibrationSP.Error.computationFailed,
      CalibrationError.MATRIX_INVALID: log.ImuCalibrationSP.Error.matrixInvalid,
    }
    return mapping.get(error_code, log.ImuCalibrationSP.Error.none)

  @staticmethod
  def _to_device_frame(v: list[float] | np.ndarray) -> np.ndarray:
    """Convert raw sensor-message axes to the locationd KF device frame.

    Kept for backwards compatibility; new code should import
    sensor_to_device_frame from openpilot.common.transformations.orientation.
    """
    return sensor_to_device_frame(v)

  def handle_accel(self, msg: log.SensorEventData) -> None:
    if self.state != CalibrationState.STATIC_COLLECTING:
      return
    ts = msg.timestamp * 1e-9
    acc = sensor_to_device_frame(msg.acceleration.v)
    self.static_buffer.append(acc, np.zeros(3), ts)

  def handle_gyro(self, msg: log.SensorEventData) -> None:
    ts = msg.timestamp * 1e-9
    gyro = sensor_to_device_frame(msg.gyroUncalibrated.v)
    if self.state == CalibrationState.STATIC_COLLECTING:
      # Update the gyro entry for the most recent accelerometer sample so that
      # bias and acc share a time series.
      if len(self.static_buffer) > 0:
        self.static_buffer.gyro[-1] = gyro
    elif self.state == CalibrationState.DYNAMIC_COLLECTING:
      self.dynamic_gyro.append(gyro, ts)
      self.current_segment.gyro_ts.append(ts)
      self.current_segment.gyro_samples.append(gyro)
      self._cached_incremental_dirty = True

  def handle_camera_odometry(self, msg: log.CameraOdometry, ts: float) -> None:
    self.last_cam_odom = msg
    if self.state != CalibrationState.DYNAMIC_COLLECTING:
      return
    if len(msg.rot) < 3:
      return
    if self.last_cam_ts is not None and ts <= self.last_cam_ts:
      return
    self.last_cam_ts = ts
    self.current_segment.cam_ts.append(ts)
    self.current_segment.cam_rot.append(np.array(msg.rot))
    self._cached_incremental_dirty = True

  def start(self) -> None:
    self.reset()
    self._set_state(CalibrationState.STATIC_COLLECTING)
    self.status.progress = 0
    self._save_status()

  def cancel(self) -> None:
    if self.state in (CalibrationState.COMPLETED, CalibrationState.FAILED, CalibrationState.CANCELLED):
      return
    self._set_state(CalibrationState.CANCELLED)
    self.status.progress = 0
    self._save_status()
    self.params.put_bool("ImuCalibrationRequested", False)

  def fail(self, reason: str, error_code: CalibrationError = CalibrationError.COMPUTATION_FAILED) -> None:
    self._set_error(error_code, reason)
    self.status.progress = 0
    self._save_status()
    self.params.put_bool("ImuCalibrationRequested", False)

  def finish_static(self) -> None:
    if len(self.static_buffer) < STATIC_MIN_SAMPLES:
      self.fail(f"not enough static samples: {len(self.static_buffer)}", CalibrationError.NOT_ENOUGH_STATIC_SAMPLES)
      return

    duration = self.static_buffer.ts[-1] - self.static_buffer.ts[0]
    if duration < STATIC_MIN_DURATION:
      self.fail(f"static phase too short: {duration:.2f}s", CalibrationError.NOT_ENOUGH_STATIC_SAMPLES)
      return

    gyro_stds = np.std(list(self.static_buffer.gyro), axis=0)
    if float(np.max(gyro_stds)) > STATIC_MAX_GYRO_STD:
      self.fail("vehicle not stationary enough", CalibrationError.NOT_STATIONARY)
      return

    try:
      self.R_static, self.gyro_bias = compute_static_rotation(
        list(self.static_buffer.acc), list(self.static_buffer.gyro)
      )
    except SlopeTooSteepError as e:
      self.fail(f"static rotation computation failed: {e}", CalibrationError.SLOPE_TOO_STEEP)
      return
    except Exception as e:
      self.fail(f"static rotation computation failed: {e}", CalibrationError.COMPUTATION_FAILED)
      return

    self.static_buffer.clear()
    self._set_state(CalibrationState.DYNAMIC_COLLECTING)
    self.status.static_samples = STATIC_MIN_SAMPLES
    self.status.progress = 30
    self.dynamic_start_ts = time.monotonic()
    self._save_status()

  def _validate_final_matrix(self, R_final: np.ndarray) -> None:
    det = float(np.linalg.det(R_final))
    if not (0.99 < det < 1.01):
      raise ValueError(f"rotation matrix determinant invalid: {det}")

    rpy = euler_from_rot(R_final)
    if not all(math.isfinite(x) for x in rpy):
      raise ValueError("rotation matrix euler angles are not finite")

    # Compare with a previous calibration if one exists.
    prev_R = self._load_matrix()
    if prev_R is not None:
      prev_rpy = euler_from_rot(prev_R)
      yaw_diff = abs(np.arctan2(np.sin(rpy[2] - prev_rpy[2]), np.cos(rpy[2] - prev_rpy[2])))
      if yaw_diff > MATRIX_MAX_YAW_DIFF:
        raise ValueError(f"yaw changed too much from previous calibration: {math.degrees(yaw_diff):.1f} deg")
      roll_diff = abs(np.arctan2(np.sin(rpy[0] - prev_rpy[0]), np.cos(rpy[0] - prev_rpy[0])))
      pitch_diff = abs(np.arctan2(np.sin(rpy[1] - prev_rpy[1]), np.cos(rpy[1] - prev_rpy[1])))
      if roll_diff > MATRIX_MAX_ROLL_PITCH_DIFF or pitch_diff > MATRIX_MAX_ROLL_PITCH_DIFF:
        raise ValueError("roll/pitch changed too much from previous calibration")

  def finish_dynamic(self) -> None:
    total_samples = self._total_dynamic_samples()
    total_duration = self._total_dynamic_duration()
    total_cam_frames = sum(len(s.cam_ts) for s in self.dynamic_segments) + len(self.current_segment.cam_ts)

    if total_samples < DYNAMIC_MIN_SAMPLES or total_cam_frames < DYNAMIC_MIN_CAMERA_FRAMES:
      self.fail(
        f"not enough dynamic samples: gyro={total_samples} cam={total_cam_frames}",
        CalibrationError.NO_STRAIGHT_ROAD,
      )
      return

    if total_duration < DYNAMIC_MIN_DURATION:
      self.fail(f"dynamic phase too short: {total_duration:.2f}s", CalibrationError.NO_STRAIGHT_ROAD)
      return

    assert self.R_static is not None and self.gyro_bias is not None
    gyro_ts, gyro_samples, cam_rot, cam_ts = self._collect_dynamic_samples()

    try:
      yaw, yaw_std, valid_ratio = compute_yaw_correction(
        self.R_static,
        self.gyro_bias,
        gyro_ts,
        gyro_samples,
        cam_rot,
        cam_ts,
      )
    except Exception as e:
      self.fail(f"dynamic yaw computation failed: {e}", CalibrationError.COMPUTATION_FAILED)
      return

    if valid_ratio < 0.5:
      self.fail(f"too many dynamic outliers: {valid_ratio:.1%} inliers", CalibrationError.CAMERA_ODOMETRY_UNRELIABLE)
      return

    # Apply yaw rotation around gravity
    z_axis = self.R_static @ VEHICLE_GRAVITY
    z_axis = z_axis / np.linalg.norm(z_axis)
    R_yaw = axis_angle_to_rot(z_axis, yaw)
    R_final = _orthonormalize(R_yaw @ self.R_static)

    try:
      self._validate_final_matrix(R_final)
    except Exception as e:
      self.fail(f"final calibration matrix invalid: {e}", CalibrationError.MATRIX_INVALID)
      return

    try:
      self._save_matrix(R_final)
    except Exception as e:
      self.fail(f"failed to save calibration matrix: {e}", CalibrationError.COMPUTATION_FAILED)
      return

    self.status.yaw_std = yaw_std
    self.status.valid_ratio = valid_ratio
    self._set_state(CalibrationState.COMPLETED)
    self.status.dynamic_samples = total_samples
    self.status.progress = 100
    self._save_status()
    self.params.put_bool("ImuCalibrationRequested", False)

  def _maybe_archive_segment(self) -> None:
    """Move the current segment into the archive if it has enough data."""
    if len(self.current_segment) >= DYNAMIC_MIN_SAMPLES // 4 and self.current_segment.duration() >= 0.5:
      self.dynamic_segments.append(self.current_segment)
    self.current_segment = DynamicSegment()

  def update(self, car_state: car.CarState) -> None:
    if self.state == CalibrationState.STATIC_COLLECTING:
      if not is_stationary(car_state):
        self.static_buffer.clear()
        self.status.static_samples = 0
        self._save_status()
        return
      self.status.static_samples = len(self.static_buffer)
      progress = min(30, int(30 * len(self.static_buffer) / (STATIC_MIN_DURATION * 100)))
      self.status.progress = max(self.status.progress, progress)
      if len(self.static_buffer) >= STATIC_MIN_SAMPLES:
        duration = self.static_buffer.ts[-1] - self.static_buffer.ts[0]
        if duration >= STATIC_MIN_DURATION:
          self.finish_static()
      self._save_status()

    elif self.state == CalibrationState.DYNAMIC_COLLECTING:
      now = time.monotonic()
      if self.dynamic_start_ts is not None and now - self.dynamic_start_ts > DYNAMIC_TIMEOUT:
        self.fail("dynamic calibration timed out", CalibrationError.TIMEOUT)
        return

      straight = is_straight_drive(car_state, self.last_cam_odom)
      if not straight:
        self._maybe_archive_segment()
        self.status.dynamic_samples = self._total_dynamic_samples()
        self.last_straight_ts = now
        self._save_status()
        return

      # Resume collecting after a brief interruption without clearing history.
      if self.last_straight_ts is not None and now - self.last_straight_ts > DYNAMIC_MAX_INTERRUPTION:
        self._maybe_archive_segment()

      self.status.dynamic_samples = self._total_dynamic_samples()
      progress = min(100, 30 + int(70 * self._total_dynamic_duration() / DYNAMIC_MIN_DURATION))
      self.status.progress = max(self.status.progress, progress)

      # Convergence check: if we already have enough data and yaw is stable, finish early.
      if (
        self._total_dynamic_duration() >= DYNAMIC_MIN_DURATION
        and self._total_dynamic_samples() >= DYNAMIC_MIN_SAMPLES
      ):
        R_inc = self.get_incremental_rotation()
        if R_inc is not None and self.status.yaw_std < YAW_CONVERGENCE_THRESHOLD:
          self.finish_dynamic()
          return

      if self._total_dynamic_samples() >= DYNAMIC_MIN_SAMPLES and self._total_dynamic_duration() >= DYNAMIC_MIN_DURATION:
        self.finish_dynamic()
        return

      self.last_straight_ts = now
      self._save_status()

  def check_request(self) -> bool:
    return self.params.get_bool("ImuCalibrationRequested")


class ImuCalibrationD:
  def __init__(self) -> None:
    self.params = Params()
    self.calibrator = ImuCalibrator(self.params)
    self.pm = messaging.PubMaster(["extrinsicsCalibration", "imuCalibrationSP"])
    self.sm = messaging.SubMaster(["carState", "cameraOdometry"], poll="cameraOdometry")
    self.sensor_socks = [messaging.sub_sock(which, timeout=20) for which in ["accelerometer", "gyroscope"]]
    self.rk = Ratekeeper(100.0, print_delay_threshold=None)
    self.last_status_publish = 0.0

  def _drain_sensors(self) -> None:
    for sock in self.sensor_socks:
      for msg in messaging.drain_sock(sock):
        if not msg.valid:
          continue
        which = msg.which()
        if which == "accelerometer":
          self.calibrator.handle_accel(msg.accelerometer)
        elif which == "gyroscope":
          self.calibrator.handle_gyro(msg.gyroscope)

  def _update_submaster(self) -> None:
    self.sm.update(0)
    if self.sm.updated["cameraOdometry"]:
      cam_odom = self.sm["cameraOdometry"]
      ts = self.sm.logMonoTime["cameraOdometry"] * 1e-9
      self.calibrator.handle_camera_odometry(cam_odom, ts)
    if self.sm.updated["carState"]:
      self.calibrator.update(self.sm["carState"])

  def _publish(self) -> None:
    now = time.monotonic()
    if now - self.last_status_publish < 0.25:
      return
    self.last_status_publish = now

    saved_R = self.calibrator._load_matrix()
    incremental_R: np.ndarray | None = None
    include_matrix = True

    if self.calibrator.state == CalibrationState.COMPLETED:
      status = log.ExtrinsicsCalibration.Status.calibrated
      progress = 100
      R = saved_R
    elif self.calibrator.state == CalibrationState.FAILED:
      status = log.ExtrinsicsCalibration.Status.invalid
      progress = 0
      R = None
    elif self.calibrator.state in (CalibrationState.CANCELLED, CalibrationState.IDLE):
      status = log.ExtrinsicsCalibration.Status.uncalibrated
      progress = 0
      R = saved_R
      if R is not None:
        status = log.ExtrinsicsCalibration.Status.calibrated
        progress = 100
    else:
      # Dynamic collecting: publish the incremental rpyCalib so modeld and
      # locationd can interpret cameraOdometry in the temporary vehicle frame.
      # Do not publish imuCalibMatrix yet; paramsd should only apply a
      # completed calibration to avoid feeding a half-converged matrix to the
      # vehicle parameter learner.
      status = log.ExtrinsicsCalibration.Status.uncalibrated
      progress = self.calibrator.status.progress
      incremental_R = self.calibrator.get_incremental_rotation()
      R = incremental_R
      include_matrix = False

    msg = self.calibrator._build_extrinsics_msg(R, status, progress, include_matrix=include_matrix)
    self.pm.send("extrinsicsCalibration", msg)

    # SP UI message may show an incremental preview while still collecting.
    ui_R = incremental_R if incremental_R is not None else saved_R
    sp_msg = self.calibrator._build_imu_calibration_sp_msg(ui_R)
    self.pm.send("imuCalibrationSP", sp_msg)

  def main(self) -> NoReturn:
    config_realtime_process([0, 1, 2, 3], 5)
    cloudlog.info("imu_calibrationd started")

    while True:
      self._drain_sensors()
      self._update_submaster()

      state = self.calibrator.state
      if state == CalibrationState.IDLE and self.calibrator.check_request():
        self.calibrator.start()
      elif state not in (CalibrationState.IDLE, CalibrationState.COMPLETED, CalibrationState.FAILED, CalibrationState.CANCELLED):
        if not self.calibrator.check_request():
          self.calibrator.cancel()

      self._publish()
      self.rk.keep_time()


def main() -> NoReturn:
  ImuCalibrationD().main()


if __name__ == "__main__":
  main()
