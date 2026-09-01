import math

import numpy as np

from openpilot.common.test import OpenpilotTestCase
from openpilot.common.transformations.orientation import rot_from_euler
import openpilot.cereal.messaging as messaging
from openpilot.selfdrive.locationd.imu_calibrationd import (
  ImuCalibrator,
  compute_static_rotation,
  compute_yaw_correction,
  integrate_gyro,
  CalibrationState,
)


def _valid_rotation(R: np.ndarray) -> bool:
  return R.shape == (3, 3) and np.allclose(R.T @ R, np.eye(3), atol=1e-6) and np.isclose(np.linalg.det(R), 1.0)


class TestImuCalibrationd(OpenpilotTestCase):

  def test_compute_static_rotation_aligned(self):
    """Device frame aligned with vehicle frame -> identity rotation."""
    acc_samples = [np.array([0.0, 0.0, 1.0]) for _ in range(100)]
    gyro_samples = [np.zeros(3) for _ in range(100)]
    R, bias = compute_static_rotation(acc_samples, gyro_samples)
    np.testing.assert_allclose(R, np.eye(3), atol=1e-6)
    np.testing.assert_allclose(bias, 0.0, atol=1e-6)

  def test_compute_static_rotation_pure_pitch(self):
    """Pure pitch mounting is recovered exactly."""
    pitch = np.deg2rad(15.0)
    R_true = rot_from_euler([0.0, pitch, 0.0])
    z_vehicle_in_device = R_true[:, 2]
    acc_samples = [z_vehicle_in_device for _ in range(100)]
    gyro_samples = [np.zeros(3) for _ in range(100)]
    R, _ = compute_static_rotation(acc_samples, gyro_samples)
    np.testing.assert_allclose(R, R_true, atol=1e-6)

  def test_compute_static_rotation_pure_roll(self):
    """Pure roll mounting is recovered exactly."""
    roll = np.deg2rad(-20.0)
    R_true = rot_from_euler([roll, 0.0, 0.0])
    z_vehicle_in_device = R_true[:, 2]
    acc_samples = [z_vehicle_in_device for _ in range(100)]
    gyro_samples = [np.zeros(3) for _ in range(100)]
    R, _ = compute_static_rotation(acc_samples, gyro_samples)
    np.testing.assert_allclose(R, R_true, atol=1e-6)

  def test_compute_static_rotation_gravity_axis(self):
    """For arbitrary mounting the gravity (vehicle up) axis is recovered."""
    roll = np.deg2rad(-10.0)
    pitch = np.deg2rad(25.0)
    yaw = np.deg2rad(45.0)
    R_true = rot_from_euler([roll, pitch, yaw])
    z_vehicle_in_device = R_true[:, 2]
    acc_samples = [z_vehicle_in_device for _ in range(100)]
    gyro_samples = [np.zeros(3) for _ in range(100)]
    R, _ = compute_static_rotation(acc_samples, gyro_samples)
    assert _valid_rotation(R)
    np.testing.assert_allclose(R[:, 2], z_vehicle_in_device, atol=1e-6)
    np.testing.assert_allclose(np.dot(R[:, 0], R[:, 2]), 0.0, atol=1e-6)

  def test_compute_static_rotation_gyro_bias(self):
    """Gyro bias is returned as the mean of static gyro samples."""
    bias_in = np.array([0.01, -0.02, 0.03])
    rng = np.random.default_rng(42)
    acc_samples = [np.array([0.0, 0.0, 1.0]) for _ in range(100)]
    gyro_samples = [bias_in + rng.normal(0, 0.001, 3) for _ in range(100)]
    _, bias_out = compute_static_rotation(acc_samples, gyro_samples)
    np.testing.assert_allclose(bias_out, bias_in, atol=1e-3)

  def test_integrate_gyro_constant_rate(self):
    """Integrate a constant rotation rate over a known interval."""
    rate = np.array([0.1, 0.2, 0.3])
    dt = 0.01
    ts = [i * dt for i in range(101)]
    samples = [rate for _ in ts]
    rot = integrate_gyro(ts, samples, ts[0], ts[-1])
    np.testing.assert_allclose(rot, rate * (ts[-1] - ts[0]), atol=1e-6)

  def test_compute_yaw_correction(self):
    """Recover a yaw offset from rotations that have horizontal components."""
    yaw_true = np.deg2rad(25.0)
    R_static = np.eye(3)
    R_yaw = rot_from_euler([0.0, 0.0, yaw_true])
    R_true = R_yaw @ R_static

    # Vehicle rotation rate with some pitch/roll excitation so projections are non-zero.
    omega_vehicle = np.array([0.02, 0.02, 0.05])
    dt_cam = 0.1
    cam_ts = [i * dt_cam for i in range(41)]
    cam_rot_samples = [omega_vehicle * dt_cam for _ in range(1, len(cam_ts))]

    dt_gyro = 0.01
    gyro_ts = [i * dt_gyro for i in range(int(cam_ts[-1] / dt_gyro) + 1)]
    omega_device = R_true @ omega_vehicle
    gyro_samples = [omega_device for _ in gyro_ts]

    yaw_est = compute_yaw_correction(R_static, np.zeros(3), gyro_ts, gyro_samples, cam_rot_samples, cam_ts)
    np.testing.assert_allclose(math.degrees(yaw_est), math.degrees(yaw_true), atol=1.0)

  def test_calibrator_static_phase_completes(self):
    """Feed stationary data and verify the calibrator moves to dynamic collecting."""
    cal = ImuCalibrator()
    cal.start()
    assert cal.state == CalibrationState.STATIC_COLLECTING

    z_device = np.array([0.0, 0.0, 1.0])
    t0 = 0.0
    for i in range(200):
      ts = int((t0 + i * 0.01) * 1e9)
      acc = messaging.new_message('accelerometer').accelerometer
      acc.timestamp = ts
      acc.acceleration.v = z_device.tolist()
      cal.handle_accel(acc)

      gyr = messaging.new_message('gyroscope').gyroscope
      gyr.timestamp = ts
      gyr.init('gyroUncalibrated')
      gyr.gyroUncalibrated.v = [0.0, 0.0, 0.0]
      cal.handle_gyro(gyr)

    car_state = messaging.new_message('carState').carState
    car_state.vEgo = 0.0
    cal.update(car_state)

    assert cal.state == CalibrationState.DYNAMIC_COLLECTING
    assert cal.R_static is not None
    np.testing.assert_allclose(cal.R_static, np.eye(3), atol=1e-3)

  def test_calibrator_matrix_roundtrip(self):
    """Saving and loading a rotation matrix via Params works."""
    cal = ImuCalibrator()
    R_in = rot_from_euler([0.1, 0.2, 0.3])
    cal._save_matrix(R_in)
    R_out = cal._load_matrix()
    assert R_out is not None
    np.testing.assert_allclose(R_in, R_out, atol=1e-6)

  def test_calibrator_reset_clears_state(self):
    """Reset returns the calibrator to idle and clears buffers."""
    cal = ImuCalibrator()
    cal.start()
    assert cal.state == CalibrationState.STATIC_COLLECTING
    cal.reset()
    assert cal.state == CalibrationState.IDLE
    assert len(cal.static_buffer) == 0
    assert len(cal.dynamic_gyro) == 0
