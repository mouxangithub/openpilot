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

from openpilot.sunnypilot.carrot.xiaoge.yolo_inference import HIGH_RISK_CLASSES

XIAOGE_LANE_TIMEOUT_NS = 4_000_000_000
XIAOGE_BLINDSPOT_TIMEOUT_NS = 1_500_000_000
# Same value as the blind-spot window on purpose, not by copy-paste: both heads
# run at the same cadence (~250 ms), so 1.5 s is six missed frames for each.
XIAOGE_YOLO_TIMEOUT_NS = 1_500_000_000
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
  # Per-side freshness (cp c6566c65a): sides are inferred on alternating passes,
  # so a single shared timestamp would age the idle side even when fresh.
  # Older payloads without the by-side map fall back to the shared timestamp.
  left_blindspot_received_nanos: int = 0
  right_blindspot_received_nanos: int = 0
  # Optional YOLO section: None when the head is off or the payload predates it
  # (the section key is absent, not version-bumped, so v1 readers keep working).
  yolo: dict | None = None


class CarStateSP(Protocol):
  """carStateSP fields written by xiaoge vision."""
  xiaogeLeftLaneLine: int
  xiaogeRightLaneLine: int
  yoloVruPresent: bool
  yoloVruNearestDist: float
  yoloVruBlockLeft: bool
  yoloVruBlockRight: bool
  yoloVruMonoTimeNanos: int


class CarState(Protocol):
  """carState fields written by xiaoge vision."""
  leftBlindspot: bool
  rightBlindspot: bool


def lane_width_meters(meta, field: str) -> float:
  """Read a target lane width (metres) from ModelDataV2.meta.

  laneWidthLeft / laneWidthRight used to be CarrotPilot-only model extensions; they are
  now defined in this fork's ModelDataV2.MetaData (@10/@11) and filled by modeld
  (selfdrive/modeld/lane_width.py). The defensive getattr stays: the manager forks
  children from its boot-time memory, so a process restarted without a full
  ``systemctl restart comma`` still runs the pre-change schema and fails closed here.
  """
  try:
    return float(getattr(meta, field, 0.0))
  except (TypeError, ValueError):
    return 0.0


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
  blindspot_received_nanos = _received_nanos(blindspot.get("receivedMonoTimeNanos"), "blindspot.receivedMonoTimeNanos")
  by_side = blindspot.get("receivedMonoTimeNanosBySide", {})
  if not isinstance(by_side, dict):
    raise ValueError("blindspot.receivedMonoTimeNanosBySide must be an object")
  return XiaogeVisionResult(
    _lane_type(lane.get("leftLine"), "lane.leftLine"),
    _lane_type(lane.get("rightLine"), "lane.rightLine"),
    _bool(lane.get("valid"), "lane.valid"),
    _received_nanos(lane.get("receivedMonoTimeNanos"), "lane.receivedMonoTimeNanos"),
    _bool(blindspot.get("left"), "blindspot.left"),
    _bool(blindspot.get("right"), "blindspot.right"),
    _bool(blindspot.get("valid"), "blindspot.valid"),
    blindspot_received_nanos,
    _received_nanos(by_side.get("left", blindspot_received_nanos), "blindspot.receivedMonoTimeNanosBySide.left"),
    _received_nanos(by_side.get("right", blindspot_received_nanos), "blindspot.receivedMonoTimeNanosBySide.right"),
    yolo=_yolo_section(data.get("yolo")),
  )


def _yolo_section(section: object) -> dict | None:
  """Validate the optional YOLO section; absent/None passes through as None."""
  if section is None:
    return None
  if not isinstance(section, dict):
    raise ValueError("yolo section must be an object")
  _bool(section.get("valid"), "yolo.valid")
  _received_nanos(section.get("receivedMonoTimeNanos"), "yolo.receivedMonoTimeNanos")
  dets = section.get("dets")
  if not isinstance(dets, list):
    raise ValueError("yolo.dets must be a list")
  return section


def merge_xiaoge_lane_type(current: int, detected: int) -> int:
  """Replace only the lane-marking type while preserving a vehicle-provided color code."""
  if detected < 0:
    return current
  color = (current // 10) * 10 if current >= 10 else 0
  return color + detected


def _is_fresh(received_nanos: int, now_nanos: int, timeout_nanos: int) -> bool:
  age_nanos = now_nanos - received_nanos
  return received_nanos != 0 and 0 <= age_nanos <= timeout_nanos


def xiaoge_blindspot_vision(result: XiaogeVisionResult | None, now_nanos: int) -> tuple[bool, bool]:
  """Per-side fresh vision blind-spot states (cp c6566c65a).

  Falls back to the shared timestamp for payloads produced before the by-side
  map existed, so old packets keep their original semantics.
  """
  if result is None or not result.blindspot_valid or \
     not _is_fresh(result.blindspot_received_nanos, now_nanos, XIAOGE_BLINDSPOT_TIMEOUT_NS):
    return False, False
  left_received = result.left_blindspot_received_nanos or result.blindspot_received_nanos
  right_received = result.right_blindspot_received_nanos or result.blindspot_received_nanos
  return (
    result.left_blindspot and _is_fresh(left_received, now_nanos, XIAOGE_BLINDSPOT_TIMEOUT_NS),
    result.right_blindspot and _is_fresh(right_received, now_nanos, XIAOGE_BLINDSPOT_TIMEOUT_NS),
  )


def apply_xiaoge_vision_result_to_cs(
    CS: CarState, result: XiaogeVisionResult | None, now_nanos: int
) -> bool:
  """Merge xiaoge blind-spot results into carState.leftBlindspot / rightBlindspot.

  Returns True if any field was applied.
  """
  if result is None:
    return False
  left_vision, right_vision = xiaoge_blindspot_vision(result, now_nanos)
  if left_vision or right_vision:
    CS.leftBlindspot = bool(CS.leftBlindspot) or left_vision
    CS.rightBlindspot = bool(CS.rightBlindspot) or right_vision
    return True
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
    lane_applied = True
  else:
    lane_applied = False

  yolo_applied = apply_yolo_summary_to_cs_sp(CS_SP, result, now_nanos)
  return lane_applied or yolo_applied


def apply_yolo_summary_to_cs_sp(
    CS_SP: CarStateSP, result: XiaogeVisionResult | None, now_nanos: int
) -> bool:
  """Write the YOLO control-side digest into carStateSP.

  Block flags are always False here: the VRU gate (path projection) owns them
  and lands separately. Distance 0.0 means "no valid target".
  """
  if result is None or result.yolo is None:
    return False
  if not result.yolo.get("valid") or not _is_fresh(
      int(result.yolo.get("receivedMonoTimeNanos", 0)), now_nanos, XIAOGE_YOLO_TIMEOUT_NS
  ):
    return False

  nearest = None
  for det in result.yolo.get("dets", []):
    if not isinstance(det, dict):
      continue
    if det.get("cid") in HIGH_RISK_CLASSES and det.get("d") is not None:
      try:
        d = float(det["d"])
      except (TypeError, ValueError):
        continue
      if nearest is None or d < nearest:
        nearest = d
  CS_SP.yoloVruPresent = nearest is not None
  CS_SP.yoloVruNearestDist = nearest if nearest is not None else 0.0
  CS_SP.yoloVruBlockLeft = False
  CS_SP.yoloVruBlockRight = False
  CS_SP.yoloVruMonoTimeNanos = int(result.yolo.get("receivedMonoTimeNanos", 0))
  return True


def apply_xiaoge_vision_result(
    CS: CarState, CS_SP: CarStateSP, result: XiaogeVisionResult | None, now_nanos: int
) -> bool:
  """Merge xiaoge vision results into both carState (blindspot) and carStateSP (lane lines).

  Returns True if any field was applied.
  """
  cs_applied = apply_xiaoge_vision_result_to_cs(CS, result, now_nanos)
  cs_sp_applied = apply_xiaoge_vision_result_to_cs_sp(CS_SP, result, now_nanos)
  return cs_applied or cs_sp_applied
