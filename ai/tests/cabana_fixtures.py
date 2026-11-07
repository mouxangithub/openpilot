"""Synthetic CAN / log fixtures shared by cabana truth/anchor/profile tests.

Physical model (all route-relative seconds unless noted):
- vehicle speed       speed(t)   = 10 + 5*sin(2π t / 10)           [m/s]
- longitudinal accel  accel(t)   = 5*(2π/10)*cos(2π t / 10)        [m/s^2]
- yaw rate            yaw(t)     = 0.3*sin(2π t / 7)               [rad/s]
- accel_vert          constant 9.81 in v[2] (gravity), fixture offset +0.02
"""
from __future__ import annotations

import math
import random
from typing import Any

T0_ABS = 1730000000.0  # absolute epoch seconds used by the fake logs
_GRAVITY = 9.81


def speed_at(t: float) -> float:
  return 10.0 + 5.0 * math.sin(2.0 * math.pi * t / 10.0)


def accel_long_at(t: float) -> float:
  return 5.0 * (2.0 * math.pi / 10.0) * math.cos(2.0 * math.pi * t / 10.0)


def yaw_at(t: float) -> float:
  return 0.3 * math.sin(2.0 * math.pi * t / 7.0)


# -----------------------------------------------------------------------------
# Duck-typed cereal log objects (capnp-compatible surface used by truth.py)
# -----------------------------------------------------------------------------

class _FakeVec:
  def __init__(self, v: list[float]):
    self.v = v


class _FakeSensorEvent:
  """SensorEventData union with exactly one active field."""

  def __init__(self, which: str, v: list[float]):
    self._which = which
    setattr(self, which, _FakeVec(v))

  def which(self) -> str:
    return self._which


class _FakeGpsLocation:
  def __init__(self, speed: float):
    self.speed = speed


class FakeLogMessage:
  """Duck-typed cereal Event: ``which()`` + union payload + logMonoTime (ns)."""

  def __init__(self, which: str, payload: Any, log_mono_time_ns: int):
    self._which = which
    self.logMonoTime = int(log_mono_time_ns)
    setattr(self, which, payload)

  def which(self) -> str:
    return self._which


class FakeLogReader:
  """Duck-typed LogReader over pre-built messages (path argument ignored)."""

  def __init__(self, messages: list[FakeLogMessage]):
    self._messages = list(messages)

  def __iter__(self):
    return iter(self._messages)


def make_truth_messages(
  duration_sec: float = 30.0,
  accel_hz: float = 100.0,
  gps_hz: float = 10.0,
  t0_abs: float = T0_ABS,
  style: str = "modern",
) -> list[FakeLogMessage]:
  """Synthetic IMU/GPS log messages.

  style="modern": accelerometer / gyroscope / gpsLocationExternal messages.
  style="legacy": sensorEventsDEPRECATED / gpsLocation only.
  style="none":   neither (truth unavailable).
  """
  msgs: list[FakeLogMessage] = []
  if style in ("modern", "legacy"):
    n_accel = int(duration_sec * accel_hz)
    for i in range(n_accel):
      t = i / accel_hz
      if style == "modern":
        msgs.append(FakeLogMessage(
          "accelerometer",
          _FakeSensorEvent("acceleration", [accel_long_at(t), 0.01, _GRAVITY + 0.02]),
          (t0_abs + t) * 1e9,
        ))
        msgs.append(FakeLogMessage(
          "gyroscope",
          _FakeSensorEvent("gyro", [0.0, 0.0, yaw_at(t)]),
          (t0_abs + t) * 1e9,
        ))
      else:
        msgs.append(FakeLogMessage(
          "sensorEventsDEPRECATED",
          [_FakeSensorEvent("acceleration", [accel_long_at(t), 0.01, _GRAVITY + 0.02])],
          (t0_abs + t) * 1e9,
        ))
        msgs.append(FakeLogMessage(
          "sensorEventsDEPRECATED",
          [_FakeSensorEvent("gyro", [0.0, 0.0, yaw_at(t)])],
          (t0_abs + t) * 1e9,
        ))
    n_gps = int(duration_sec * gps_hz)
    for i in range(n_gps):
      t = i / gps_hz
      gps_which = "gpsLocationExternal" if style == "modern" else "gpsLocation"
      msgs.append(FakeLogMessage(gps_which, _FakeGpsLocation(speed_at(t) + 0.05), (t0_abs + t) * 1e9))
  elif style == "none":
    msgs.append(FakeLogMessage("can", [], (t0_abs) * 1e9))
  msgs.sort(key=lambda m: m.logMonoTime)
  return msgs


# -----------------------------------------------------------------------------
# Truth series (route-relative) for anchor tests
# -----------------------------------------------------------------------------

def make_truth_series(duration_sec: float = 30.0, hz: float = 20.0, t0_rel: float = 0.0) -> dict[str, Any]:
  """Rel-time truth series matching the fixture physical model."""
  n = int(duration_sec * hz)
  ts = [t0_rel + i / hz for i in range(n)]
  return {
    "available": True,
    "note": "",
    "series": {
      "accel_long": {"t": ts, "v": [accel_long_at(t - t0_rel) for t in ts]},
      "accel_vert": {"t": ts, "v": [0.02] * n},
      "yaw_rate": {"t": ts, "v": [yaw_at(t - t0_rel) for t in ts]},
      "gps_speed": {"t": ts, "v": [speed_at(t - t0_rel) for t in ts]},
      "gps_accel": {"t": ts[1:-1], "v": [accel_long_at(t - t0_rel) for t in ts[1:-1]]},
    },
  }


# -----------------------------------------------------------------------------
# CAN frame builders (frames carry route-relative or absolute "time")
# -----------------------------------------------------------------------------

def _encode_raw(phys: float, factor: float, offset: float, max_raw: int) -> int:
  raw = int(round((phys - offset) / factor))
  return max(0, min(raw, max_raw))


def make_speed_frames(
  address: int,
  n: int = 1000,
  hz: float = 100.0,
  factor: float = 0.00016,
  offset: float = 5.0,
  t0_rel: float = 0.0,
  with_counter: bool = True,
) -> list[dict[str, Any]]:
  """Frames whose bytes 0-1 (LE) encode the fixture speed profile (16-bit).

  factor/offset are chosen so the 16-bit raw value spans its full range
  (speed 5..15 m/s → raw 0..62500), keeping all 16 bits statistically active.
  """
  frames: list[dict[str, Any]] = []
  for i in range(n):
    t = t0_rel + i / hz
    raw = _encode_raw(speed_at(t), factor, offset, 0xFFFF)
    data = bytearray(8)
    data[0] = raw & 0xFF
    data[1] = (raw >> 8) & 0xFF
    if with_counter:
      data[4] = i % 256  # counter kept in byte4 so bytes0-1 form a clean 16-bit run
    frames.append({"time": t, "bus": 0, "address": address, "data": bytes(data).hex()})
  return frames


def make_brake_frames(
  address: int,
  n: int = 1000,
  hz: float = 100.0,
  t0_rel: float = 0.0,
  threshold: float = -0.5,
) -> list[dict[str, Any]]:
  """Frames with a brake bool at bit 8 (byte1 bit0): set while decelerating."""
  frames: list[dict[str, Any]] = []
  for i in range(n):
    t = t0_rel + i / hz
    brake = accel_long_at(t) < threshold
    data = bytearray(8)
    if brake:
      data[1] |= 0x01
    frames.append({"time": t, "bus": 0, "address": address, "data": bytes(data).hex()})
  return frames


def make_xor_checksum_frames(
  address: int,
  n: int = 400,
  hz: float = 50.0,
  t0_rel: float = 0.0,
) -> list[dict[str, Any]]:
  """Frames with speed in bytes0-1, counter byte2, noise byte6 and byte7 =
  SUM(bytes0..6) & 0xFF (uniquely identifies byte7 as the checksum field)."""
  frames: list[dict[str, Any]] = []
  for i in range(n):
    t = t0_rel + i / hz
    raw = _encode_raw(speed_at(t), 0.00016, 5.0, 0xFFFF)
    data = bytearray(8)
    data[0] = raw & 0xFF
    data[1] = (raw >> 8) & 0xFF
    data[2] = i % 256
    data[6] = (i * 3) % 256
    data[7] = sum(data[:7]) & 0xFF
    frames.append({"time": t, "bus": 0, "address": address, "data": bytes(data).hex()})
  return frames


def make_noise_frames(
  address: int,
  n: int = 500,
  hz: float = 50.0,
  t0_rel: float = 0.0,
  seed: int = 7,
) -> list[dict[str, Any]]:
  """Random-payload frames (no physical structure, no checksum)."""
  rng = random.Random(seed)
  frames: list[dict[str, Any]] = []
  for i in range(n):
    data = bytes(rng.randrange(256) for _ in range(8))
    frames.append({"time": t0_rel + i / hz, "bus": 0, "address": address, "data": data.hex()})
  return frames


def make_mux_frames(
  address: int,
  n: int = 600,
  hz: float = 100.0,
  t0_rel: float = 0.0,
) -> list[dict[str, Any]]:
  """Frames with a 3-value mode byte (byte3) alongside an active speed signal."""
  frames: list[dict[str, Any]] = []
  for i in range(n):
    t = t0_rel + i / hz
    raw = _encode_raw(speed_at(t), 0.00016, 5.0, 0xFFFF)
    data = bytearray(8)
    data[0] = raw & 0xFF
    data[1] = (raw >> 8) & 0xFF
    if i < n * 0.62:
      data[3] = 0
    elif i < n * 0.93:
      data[3] = 2
    else:
      data[3] = 7
    frames.append({"time": t, "bus": 0, "address": address, "data": bytes(data).hex()})
  return frames
