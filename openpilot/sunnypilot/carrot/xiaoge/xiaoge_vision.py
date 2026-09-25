"""Xiaoge vision payload validation and car-state integration helpers.

Ported from CarrotPilot (cp):
  selfdrive/carrot/xiaoge/xiaoge_vision.py

Integration:
  On real hardware: xiaoge_data.py reads VisionIPC NV12 buffers, runs ONNX inference,
  serializes results to JSON, and publishes via customReservedRawData0.
  On PC dev: camera source unavailable, inference returns error state.

Lane lines are written to carStateSP (custom.capnp CarStateSP.xiaogeLeftLaneLine /
xiaogeRightLaneLine) to keep opendbc CarState untouched. Blindspot hints are written
to carState.leftBlindspot / carState.rightBlindspot (already in opendbc car.capnp).
"""
from dataclasses import dataclass
import json
from typing import Protocol

XIAOGE_LANE_TIMEOUT_NS = 4_000_000_000
XIAOGE_BLINDSPOT_TIMEOUT_NS = 1_500_000_000
XIAOGE_LANE_TYPES = (-1, 0, 1)


@dataclass(frozen=True)
class XiaogeVisionResult:
  left_lane: int
  right_lane: int
  lane_valid: bool
  lane_received_nanos: int
  left_blindspot: bool
  right_blindspot: bool
  blindspot_valid: bool
  blindspot_received_nanos: int


class CarStateSP(Protocol):
  """carStateSP fields written by xiaoge vision."""
  xiaogeLeftLaneLine: int
  xiaogeRightLaneLine: int


class CarState(Protocol):
  """carState fields written by xiaoge vision."""
  leftBlindspot: bool
  rightBlindspot: bool


def _lane_type(value: object, field: str) -> int:
  if isinstance(value, bool) or not isinstance(value, int) or value not in XIAOGE_LANE_TYPES:
    raise ValueError(f"{field} must be -1, 0, or 1")
  return value


def _bool(value: object, field: str) -> bool:
  if not isinstance(value, bool):
    raise ValueError(f"{field} must be a boolean")
  return value


def _received_nanos(value: object, field: str) -> int:
  if isinstance(value, bool) or not isinstance(value, int) or value < 0:
    raise ValueError(f"{field} must be a non-negative integer")
  return value


def parse_xiaoge_vision_payload(payload: bytes) -> XiaogeVisionResult:
  data = json.loads(payload)
  if not isinstance(data, dict) or data.get("type") != "xiaogeVision" or data.get("version") != 1:
    raise ValueError("expected a version 1 xiaogeVision object")
  lane = data.get("lane")
  blindspot = data.get("blindspot")
  if not isinstance(lane, dict) or not isinstance(blindspot, dict):
    raise ValueError("lane and blindspot must be objects")
  return XiaogeVisionResult(
    _lane_type(lane.get("leftLine"), "lane.leftLine"),
    _lane_type(lane.get("rightLine"), "lane.rightLine"),
    _bool(lane.get("valid"), "lane.valid"),
    _received_nanos(lane.get("receivedMonoTimeNanos"), "lane.receivedMonoTimeNanos"),
    _bool(blindspot.get("left"), "blindspot.left"),
    _bool(blindspot.get("right"), "blindspot.right"),
    _bool(blindspot.get("valid"), "blindspot.valid"),
    _received_nanos(blindspot.get("receivedMonoTimeNanos"), "blindspot.receivedMonoTimeNanos"),
  )


def merge_xiaoge_lane_type(current: int, detected: int) -> int:
  """Replace only the lane-marking type while preserving a vehicle-provided color code."""
  if detected < 0:
    return current
  color = (current // 10) * 10 if current >= 10 else 0
  return color + detected


def _is_fresh(received_nanos: int, now_nanos: int, timeout_nanos: int) -> bool:
  age_nanos = now_nanos - received_nanos
  return received_nanos != 0 and 0 <= age_nanos <= timeout_nanos


def apply_xiaoge_vision_result_to_cs(
    CS: CarState, result: XiaogeVisionResult | None, now_nanos: int
) -> bool:
  """Merge xiaoge blind-spot results into carState.leftBlindspot / rightBlindspot.

  Returns True if any field was applied.
  """
  if result is None:
    return False
  if result.blindspot_valid and _is_fresh(
      result.blindspot_received_nanos, now_nanos, XIAOGE_BLINDSPOT_TIMEOUT_NS
  ):
    CS.leftBlindspot = CS.leftBlindspot or result.left_blindspot
    CS.rightBlindspot = CS.rightBlindspot or result.right_blindspot
    return result.left_blindspot or result.right_blindspot
  return False


def apply_xiaoge_vision_result_to_cs_sp(
    CS_SP: CarStateSP, result: XiaogeVisionResult | None, now_nanos: int
) -> bool:
  """Merge xiaoge lane-inference results into carStateSP.xiaogeLeftLaneLine / xiaogeRightLaneLine.

  Returns True if any field was applied.
  """
  if result is None:
    return False
  if result.lane_valid and _is_fresh(result.lane_received_nanos, now_nanos, XIAOGE_LANE_TIMEOUT_NS):
    if result.left_lane >= 0:
      CS_SP.xiaogeLeftLaneLine = merge_xiaoge_lane_type(
        int(CS_SP.xiaogeLeftLaneLine), result.left_lane
      )
    if result.right_lane >= 0:
      CS_SP.xiaogeRightLaneLine = merge_xiaoge_lane_type(
        int(CS_SP.xiaogeRightLaneLine), result.right_lane
      )
    return True
  return False


def apply_xiaoge_vision_result(
    CS: CarState, CS_SP: CarStateSP, result: XiaogeVisionResult | None, now_nanos: int
) -> bool:
  """Merge xiaoge vision results into both carState (blindspot) and carStateSP (lane lines).

  Returns True if any field was applied.
  """
  cs_applied = apply_xiaoge_vision_result_to_cs(CS, result, now_nanos)
  cs_sp_applied = apply_xiaoge_vision_result_to_cs_sp(CS_SP, result, now_nanos)
  return cs_applied or cs_sp_applied
