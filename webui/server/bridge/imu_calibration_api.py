"""API for IMU auto-calibration status and control."""

from __future__ import annotations

import json
import math
import numpy as np
from typing import Any

from openpilot.common.params import Params


def _params() -> Params:
  return Params()


def _matrix_to_euler_angles(data: bytes | None) -> dict[str, float] | None:
  if data is None or len(data) != 36:
    return None
  try:
    R = np.frombuffer(data, dtype=np.float32).reshape(3, 3)
    # Extract Tait-Bryan angles Z-Y-X for display only
    pitch = math.asin(-float(R[2, 0]))
    yaw = math.atan2(float(R[1, 0]), float(R[0, 0]))
    roll = math.atan2(float(R[2, 1]), float(R[2, 2]))
    return {
      "roll_deg": math.degrees(roll),
      "pitch_deg": math.degrees(pitch),
      "yaw_deg": math.degrees(yaw),
    }
  except Exception:
    return None


def snapshot_imu_calibration() -> dict[str, Any]:
  """Return current IMU calibration status and settings."""
  try:
    p = _params()
    enabled = p.get_bool("ImuCalibrationEnabled")
    status_json = p.get("ImuCalibrationStatus") or "{}"
    try:
      status = json.loads(status_json)
    except Exception:
      status = {"state": "idle", "progress": 0, "error": None}

    matrix_data = p.get("ImuCalibrationMatrix")
    angles = _matrix_to_euler_angles(matrix_data)

    return {
      "ok": True,
      "enabled": enabled,
      "status": status,
      "calibrated": angles is not None and status.get("state") == "completed",
      "angles": angles,
    }
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def start_imu_calibration() -> dict[str, Any]:
  """Signal imu_calibrationd to start a new calibration."""
  try:
    p = _params()
    p.put_bool("ImuCalibrationEnabled", True)
    p.put_bool("ImuCalibrationRequested", True)
    return {"ok": True}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def cancel_imu_calibration() -> dict[str, Any]:
  """Signal imu_calibrationd to cancel an in-progress calibration."""
  try:
    p = _params()
    p.put_bool("ImuCalibrationRequested", False)
    return {"ok": True}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def reset_imu_calibration() -> dict[str, Any]:
  """Clear saved IMU calibration and disable the feature."""
  try:
    p = _params()
    for key in ("ImuCalibrationMatrix", "ImuCalibrationStatus"):
      try:
        p.remove(key)
      except Exception:
        pass
    p.put_bool("ImuCalibrationRequested", False)
    p.put_bool("ImuCalibrationEnabled", False)
    p.put_bool("OnroadCycleRequested", True)
    return {"ok": True}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def set_imu_calibration_enabled(enabled: bool) -> dict[str, Any]:
  """Enable or disable IMU calibration mode."""
  try:
    p = _params()
    p.put_bool("ImuCalibrationEnabled", enabled)
    p.put_bool("OnroadCycleRequested", True)
    return {"ok": True, "enabled": enabled}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}
