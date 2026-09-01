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
from openpilot.common.transformations.orientation import rot_from_euler
from opendbc.car.structs import car

# Calibration thresholds
STATIC_MIN_DURATION = 1.5  # seconds of stationary data required
STATIC_MAX_GYRO_STD = 0.05  # rad/s, must be nearly still
STATIC_MAX_SPEED = 0.2  # m/s
STATIC_MIN_SAMPLES = 100

DYNAMIC_MIN_DURATION = 3.0  # seconds of straight driving required
DYNAMIC_MIN_SPEED = 5.0  # m/s
DYNAMIC_MAX_YAW_RATE = 0.10  # rad/s, roughly straight
DYNAMIC_MIN_CAMERA_FRAMES = 20
DYNAMIC_MIN_SAMPLES = int(DYNAMIC_MIN_DURATION * 100.0)  # gyro samples at 100 Hz

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


@dataclass
class CalibrationStatus:
  state: CalibrationState = CalibrationState.IDLE
  progress: int = 0
  error: str | None = None
  static_samples: int = 0
  dynamic_samples: int = 0

  def to_json(self) -> str:
    return json.dumps({
      "state": self.state.value,
      "progress": self.progress,
      "error": self.error,
      "static_samples": self.static_samples,
      "dynamic_samples": self.dynamic_samples,
    })

  @classmethod
  def from_json(cls, data: str) -> CalibrationStatus:
    d = json.loads(data)
    return cls(
      state=CalibrationState(d.get("state", "idle")),
      progress=d.get("progress", 0),
      error=d.get("error"),
      static_samples=d.get("static_samples", 0),
      dynamic_samples=d.get("dynamic_samples", 0),
    )


@dataclass
class SampleBuffer:
  acc: deque[np.ndarray] = field(default_factory=lambda: deque(maxlen=20000))
  gyro: deque[np.ndarray] = field(default_factory=lambda: deque(maxlen=20000))
  ts: deque[float] = field(default_factory=lambda: deque(maxlen=20000))

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


def is_stationary(car_state: car.CarState) -> bool:
  return abs(car_state.vEgo) < STATIC_MAX_SPEED


def is_straight_drive(car_state: car.CarState, cam_odom: log.CameraOdometry | None) -> bool:
  if car_state.vEgo < DYNAMIC_MIN_SPEED:
    return False
  if cam_odom is None or len(cam_odom.rot) < 3:
    return False
  return abs(cam_odom.rot[2]) < DYNAMIC_MAX_YAW_RATE


def compute_static_rotation(acc_samples: list[np.ndarray], gyro_samples: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
  """
  Compute pitch/roll rotation from gravity and the gyro bias.

  Returns (R_device_from_vehicle_with_zero_yaw, gyro_bias).
  """
  gravity_device = np.mean(acc_samples, axis=0)
  norm = np.linalg.norm(gravity_device)
  if norm < 1e-6:
    raise ValueError("accelerometer samples are near zero")
  gravity_device = gravity_device / norm

  gyro_bias = np.mean(gyro_samples, axis=0)

  # Device z-down axis = gravity direction
  z_d = gravity_device.copy()
  # Device x-forward = projection of vehicle forward onto plane perpendicular to gravity
  x_d = VEHICLE_FORWARD - np.dot(VEHICLE_FORWARD, z_d) * z_d
  x_norm = np.linalg.norm(x_d)
  if x_norm < 1e-6:
    # Device z is aligned with vehicle forward; pick an arbitrary perpendicular
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


def integrate_gyro(gyro_ts: list[float], gyro_samples: list[np.ndarray], t0: float, t1: float) -> np.ndarray:
  """Integrate gyro readings between t0 and t1 using trapezoidal rule."""
  rot = np.zeros(3)
  prev_t = None
  prev_g = None
  for ts, g in zip(gyro_ts, gyro_samples, strict=False):
    if ts < t0 or ts > t1:
      continue
    if prev_t is not None and prev_g is not None:
      dt = ts - prev_t
      rot += 0.5 * (prev_g + g) * dt
    prev_t = ts
    prev_g = g
  return rot


def compute_yaw_correction(
  R_static: np.ndarray,
  gyro_bias: np.ndarray,
  gyro_ts: list[float],
  gyro_samples: list[np.ndarray],
  cam_rot_samples: list[np.ndarray],
  cam_ts: list[float],
) -> float:
  """
  Solve for the yaw rotation around gravity that aligns predicted device
  rotation (from camera odometry) with integrated gyro rotation.

  Returns yaw angle in radians.
  """
  z_axis = R_static @ VEHICLE_GRAVITY
  z_axis = z_axis / np.linalg.norm(z_axis)

  pred_angles = []
  meas_angles = []

  for i in range(1, len(cam_ts)):
    t0 = cam_ts[i - 1]
    t1 = cam_ts[i]
    dt = t1 - t0
    if dt <= 0 or dt > 1.0:
      continue

    # Camera rotation vector over this interval in vehicle frame
    cam_rot_vehicle = cam_rot_samples[i - 1]
    if len(cam_rot_vehicle) < 3:
      continue

    # Predicted device rotation = R_static * vehicle rotation
    pred_rot = R_static @ np.array(cam_rot_vehicle)

    # Measured device rotation = integrated gyro minus bias
    meas_rot = integrate_gyro(gyro_ts, gyro_samples, t0, t1)
    meas_rot -= gyro_bias * dt

    # Project onto x-y plane (perpendicular to gravity)
    pred_xy = pred_rot - np.dot(pred_rot, z_axis) * z_axis
    meas_xy = meas_rot - np.dot(meas_rot, z_axis) * z_axis

    p_norm = np.linalg.norm(pred_xy)
    m_norm = np.linalg.norm(meas_xy)
    if p_norm < 1e-6 or m_norm < 1e-6:
      continue

    pred_angles.append(np.arctan2(pred_xy[1], pred_xy[0]))
    meas_angles.append(np.arctan2(meas_xy[1], meas_xy[0]))

  if len(pred_angles) < DYNAMIC_MIN_CAMERA_FRAMES:
    raise ValueError(f"insufficient dynamic samples: {len(pred_angles)}")

  # Circular mean of angle differences
  diffs = np.array(meas_angles) - np.array(pred_angles)
  sin_sum = float(np.mean(np.sin(diffs)))
  cos_sum = float(np.mean(np.cos(diffs)))
  yaw = math.atan2(sin_sum, cos_sum)
  return yaw


class ImuCalibrator:
  def __init__(self, params: Params | None = None) -> None:
    self.params = params or Params()
    self.status = CalibrationStatus()
    self.state = CalibrationState.IDLE
    self.static_buffer = SampleBuffer()
    self.dynamic_gyro = SampleBuffer()
    self.dynamic_cam_rot: list[np.ndarray] = []
    self.dynamic_cam_ts: list[float] = []
    self.R_static: np.ndarray | None = None
    self.gyro_bias: np.ndarray | None = None
    self.last_cam_odom: log.CameraOdometry | None = None
    self.last_cam_ts: float | None = None

  def reset(self) -> None:
    self.state = CalibrationState.IDLE
    self.static_buffer.clear()
    self.dynamic_gyro.clear()
    self.dynamic_cam_rot.clear()
    self.dynamic_cam_ts.clear()
    self.R_static = None
    self.gyro_bias = None
    self.last_cam_odom = None
    self.last_cam_ts = None
    self.status = CalibrationStatus(state=CalibrationState.IDLE)

  def _set_state(self, state: CalibrationState, error: str | None = None) -> None:
    self.state = state
    self.status.state = state
    self.status.error = error
    cloudlog.info(f"IMU calibration state: {state.value}" + (f" error={error}" if error else ""))

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
    cloudlog.info("Saved ImuCalibrationMatrix")

  def _load_matrix(self) -> np.ndarray | None:
    data = self.params.get("ImuCalibrationMatrix")
    if data is None or len(data) != 36:
      return None
    try:
      return np.frombuffer(data, dtype=np.float32).reshape(3, 3)
    except Exception:
      cloudlog.exception("Failed to load ImuCalibrationMatrix")
      return None

  def _build_extrinsics_msg(
    self,
    R: np.ndarray | None = None,
    status: log.ExtrinsicsCalibration.Status = log.ExtrinsicsCalibration.Status.uncalibrated,
    progress: int = 0,
  ) -> log.Event:
    msg = messaging.new_message("extrinsicsCalibration")
    msg.valid = True
    ec = msg.extrinsicsCalibration
    ec.calStatus = status
    ec.calPerc = progress
    ec.validBlocks = 1 if status == log.ExtrinsicsCalibration.Status.calibrated else 0
    ec.rpyCalib = [0.0, 0.0, 0.0]
    ec.rpyCalibSpread = [0.0, 0.0, 0.0]
    ec.wideFromDeviceEuler = [0.0, 0.0, 0.0]
    ec.height = [1.22]
    if R is not None:
      ec.imuCalibMatrix = R.astype(np.float32).flatten().tolist()
    return msg

  def handle_accel(self, msg: log.SensorEventData) -> None:
    if self.state != CalibrationState.STATIC_COLLECTING:
      return
    ts = msg.timestamp * 1e-9
    self.static_buffer.append(np.array(msg.acceleration.v), np.zeros(3), ts)

  def handle_gyro(self, msg: log.SensorEventData) -> None:
    ts = msg.timestamp * 1e-9
    if self.state == CalibrationState.STATIC_COLLECTING:
      self.static_buffer.append(np.zeros(3), np.array(msg.gyroUncalibrated.v), ts)
    elif self.state == CalibrationState.DYNAMIC_COLLECTING:
      self.dynamic_gyro.append(np.zeros(3), np.array(msg.gyroUncalibrated.v), ts)

  def handle_camera_odometry(self, msg: log.CameraOdometry, ts: float) -> None:
    self.last_cam_odom = msg
    if self.state != CalibrationState.DYNAMIC_COLLECTING:
      return
    if len(msg.rot) < 3:
      return
    if self.last_cam_ts is not None and ts <= self.last_cam_ts:
      return
    self.last_cam_ts = ts
    self.dynamic_cam_rot.append(np.array(msg.rot))
    self.dynamic_cam_ts.append(ts)

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

  def fail(self, reason: str) -> None:
    self._set_state(CalibrationState.FAILED, reason)
    self.status.progress = 0
    self._save_status()
    self.params.put_bool("ImuCalibrationRequested", False)

  def finish_static(self) -> None:
    if len(self.static_buffer) < STATIC_MIN_SAMPLES:
      self.fail(f"not enough static samples: {len(self.static_buffer)}")
      return

    duration = self.static_buffer.ts[-1] - self.static_buffer.ts[0]
    if duration < STATIC_MIN_DURATION:
      self.fail(f"static phase too short: {duration:.2f}s")
      return

    gyro_stds = np.std(list(self.static_buffer.gyro), axis=0)
    if float(np.max(gyro_stds)) > STATIC_MAX_GYRO_STD:
      self.fail("vehicle not stationary enough")
      return

    try:
      self.R_static, self.gyro_bias = compute_static_rotation(
        list(self.static_buffer.acc), list(self.static_buffer.gyro)
      )
    except Exception as e:
      self.fail(f"static rotation computation failed: {e}")
      return

    self.static_buffer.clear()
    self._set_state(CalibrationState.DYNAMIC_COLLECTING)
    self.status.static_samples = STATIC_MIN_SAMPLES
    self.status.progress = 30
    self._save_status()

  def finish_dynamic(self) -> None:
    if len(self.dynamic_gyro) < DYNAMIC_MIN_SAMPLES or len(self.dynamic_cam_rot) < DYNAMIC_MIN_CAMERA_FRAMES:
      self.fail(f"not enough dynamic samples: gyro={len(self.dynamic_gyro)} cam={len(self.dynamic_cam_rot)}")
      return

    duration = self.dynamic_gyro.ts[-1] - self.dynamic_gyro.ts[0]
    if duration < DYNAMIC_MIN_DURATION:
      self.fail(f"dynamic phase too short: {duration:.2f}s")
      return

    assert self.R_static is not None and self.gyro_bias is not None
    try:
      yaw = compute_yaw_correction(
        self.R_static,
        self.gyro_bias,
        list(self.dynamic_gyro.ts),
        list(self.dynamic_gyro.gyro),
        self.dynamic_cam_rot,
        self.dynamic_cam_ts,
      )
    except Exception as e:
      self.fail(f"dynamic yaw computation failed: {e}")
      return

    # Apply yaw rotation around gravity
    z_axis = self.R_static @ VEHICLE_GRAVITY
    z_axis = z_axis / np.linalg.norm(z_axis)
    R_yaw = rot_from_euler(z_axis * yaw)
    R_final = R_yaw @ self.R_static

    # Enforce right-handed orthonormal
    U, _, Vt = np.linalg.svd(R_final)
    R_final = U @ Vt
    if np.linalg.det(R_final) < 0:
      U[:, -1] *= -1
      R_final = U @ Vt

    try:
      self._save_matrix(R_final)
    except Exception as e:
      self.fail(f"failed to save calibration matrix: {e}")
      return

    self._set_state(CalibrationState.COMPLETED)
    self.status.dynamic_samples = len(self.dynamic_gyro)
    self.status.progress = 100
    self._save_status()
    self.params.put_bool("ImuCalibrationRequested", False)

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
      if not is_straight_drive(car_state, self.last_cam_odom):
        self.dynamic_gyro.clear()
        self.dynamic_cam_rot.clear()
        self.dynamic_cam_ts.clear()
        self.status.dynamic_samples = 0
        self._save_status()
        return
      self.status.dynamic_samples = len(self.dynamic_gyro)
      progress = min(100, 30 + int(70 * len(self.dynamic_gyro) / (DYNAMIC_MIN_DURATION * 100)))
      self.status.progress = max(self.status.progress, progress)
      if len(self.dynamic_gyro) >= DYNAMIC_MIN_SAMPLES:
        duration = self.dynamic_gyro.ts[-1] - self.dynamic_gyro.ts[0]
        if duration >= DYNAMIC_MIN_DURATION:
          self.finish_dynamic()
      self._save_status()

  def check_request(self) -> bool:
    return self.params.get_bool("ImuCalibrationRequested")


class ImuCalibrationD:
  def __init__(self) -> None:
    self.params = Params()
    self.calibrator = ImuCalibrator(self.params)
    self.pm = messaging.PubMaster(["extrinsicsCalibration"])
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

    R = self.calibrator._load_matrix()
    if self.calibrator.state == CalibrationState.COMPLETED:
      status = log.ExtrinsicsCalibration.Status.calibrated
      progress = 100
    elif self.calibrator.state == CalibrationState.FAILED:
      status = log.ExtrinsicsCalibration.Status.invalid
      progress = 0
    elif self.calibrator.state in (CalibrationState.CANCELLED, CalibrationState.IDLE):
      status = log.ExtrinsicsCalibration.Status.uncalibrated
      progress = 0
      if R is not None:
        status = log.ExtrinsicsCalibration.Status.calibrated
        progress = 100
    else:
      status = log.ExtrinsicsCalibration.Status.uncalibrated
      progress = self.calibrator.status.progress

    msg = self.calibrator._build_extrinsics_msg(R, status, progress)
    self.pm.send("extrinsicsCalibration", msg)

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
