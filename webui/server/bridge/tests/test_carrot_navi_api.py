"""Tests for carrot_navi_api.py."""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest

from webui.server.bridge.carrot_navi_api import (
  snapshot_carrot_crossroad,
  snapshot_carrot_navi_debug,
  CROSSROAD_PARAM,
  IMAGE_PARAM,
  DEBUG_PARAM,
  MEDIA_SERVICE,
)


class _FakeParams:
  def __init__(self, data: dict[str, Any]):
    self._data = data

  def get(self, key: str):
    val = self._data.get(key)
    if val is None:
      return None
    return val if isinstance(val, (bytes, bytearray)) else str(val).encode()


@pytest.fixture(autouse=True)
def _patch_params(monkeypatch):
  storage: dict[str, Any] = {}

  def factory():
    return _FakeParams(storage)

  monkeypatch.setattr("webui.server.bridge.carrot_navi_api._params", factory)
  monkeypatch.setattr("webui.server.bridge.carrot_navi_api._read_json_param", lambda key: _read(storage, key))
  monkeypatch.setattr("webui.server.bridge.carrot_navi_api.get_shared_sm", lambda: None)


def _read(storage: dict[str, Any], key: str) -> dict[str, Any] | None:
  val = storage.get(key)
  if val is None:
    return None
  if isinstance(val, bytes):
    val = val.decode("utf-8", errors="replace")
  try:
    return json.loads(val)
  except Exception:
    return None


def test_crossroad_empty():
  result = snapshot_carrot_crossroad()
  assert result["ok"] is True
  assert result["has_crossroad"] is False
  assert result["crossroad"] is None
  assert result["image"] is None


def test_crossroad_with_data(monkeypatch):
  storage = {
    CROSSROAD_PARAM: json.dumps({
      "distanceM": 320,
      "imageCode": 42,
      "imageUrl": "https://example.com/crossroad.png",
      "totalMeters": 1200.5,
      "remainRatio": 0.72,
      "ts": 1726000000,
    }),
    IMAGE_PARAM: json.dumps({
      "show": True,
      "imageBase64": "bW9jaw==",
      "imageMime": "image/png",
      "imageEncoding": "base64",
      "imageWidth": 640,
      "imageHeight": 360,
      "imageHash": "abc123",
      "imageUrl": "https://example.com/crossroad.png",
      "imageTooLarge": False,
      "totalMeters": 1200.5,
      "remainRatio": 0.72,
      "ts": 1726000000,
      "receivedMono": 1234.5,
    }),
  }
  monkeypatch.setattr("webui.server.bridge.carrot_navi_api._read_json_param", lambda key: _read(storage, key))
  result = snapshot_carrot_crossroad()
  assert result["ok"] is True
  assert result["has_crossroad"] is True
  assert result["crossroad"]["distanceM"] == 320
  assert result["crossroad"]["imageCode"] == 42
  assert result["image"]["show"] is True
  assert result["image"]["imageBase64"] == "bW9jaw=="
  assert result["image"]["imageWidth"] == 640


def test_navi_debug_empty():
  result = snapshot_carrot_navi_debug()
  assert result["ok"] is True
  assert result["has_debug"] is False


def test_navi_debug_with_data(monkeypatch):
  storage = {
    DEBUG_PARAM: json.dumps({
      "receivedAt": "2026-09-12T15:10:00",
      "eventTimeMs": 1234567890,
      "type": "complexCrossroad",
      "summary": {"type": "complexCrossroad", "keys": ["crossroad", "imageBase64"]},
    }),
  }
  monkeypatch.setattr("webui.server.bridge.carrot_navi_api._read_json_param", lambda key: _read(storage, key))
  result = snapshot_carrot_navi_debug()
  assert result["ok"] is True
  assert result["has_debug"] is True
  assert result["debug"]["type"] == "complexCrossroad"
  assert result["debug"]["summary"]["keys"] == ["crossroad", "imageBase64"]


class _FakeSM:
  """Minimal fake SubMaster for carrotNaviMediaSP tests."""

  def __init__(self, frame: Any | None = None, updated: bool = True, valid: bool = True):
    self._frame = frame
    self.updated = {MEDIA_SERVICE: updated}
    self.valid = {MEDIA_SERVICE: valid}
    self.logMonoTime = {MEDIA_SERVICE: 0}

  def __getitem__(self, key: str):
    if key != MEDIA_SERVICE:
      raise KeyError(key)
    return self._frame


def _make_frame(name: str = "crossroad_expanded", payload: bytes = b"mock", *,
                received_mono_ns: int | None = None, width: int = 640, height: int = 360) -> Any:
  if received_mono_ns is None:
    import time
    received_mono_ns = int(time.monotonic() * 1e9)

  class Frame:
    pass

  frame = Frame()
  frame.kind = "image"
  frame.name = name
  frame.width = width
  frame.height = height
  frame.payload = payload
  frame.receivedMonoTimeNanos = received_mono_ns
  return frame


def test_crossroad_prefers_media_frame(monkeypatch):
  storage = {
    CROSSROAD_PARAM: json.dumps({
      "distanceM": 320,
      "imageCode": 42,
      "imageUrl": "https://example.com/crossroad.png",
      "totalMeters": 1200.5,
      "remainRatio": 0.72,
      "ts": 1726000000,
    }),
    IMAGE_PARAM: json.dumps({
      "show": True,
      "imageBase64": "bW9jaw==",
      "imageMime": "image/png",
      "imageEncoding": "base64",
      "imageWidth": 640,
      "imageHeight": 360,
      "imageHash": "abc123",
      "imageUrl": "https://example.com/crossroad.png",
      "imageTooLarge": False,
      "totalMeters": 1200.5,
      "remainRatio": 0.72,
      "ts": 1726000000,
      "receivedMono": 1234.5,
    }),
  }
  payload = base64.b64encode(b"frame-payload")
  frame = _make_frame("crossroad_minimized", payload, width=800, height=480)
  sm = _FakeSM(frame)
  monkeypatch.setattr("webui.server.bridge.carrot_navi_api._read_json_param", lambda key: _read(storage, key))
  monkeypatch.setattr("webui.server.bridge.carrot_navi_api.get_shared_sm", lambda: sm)

  result = snapshot_carrot_crossroad()
  assert result["ok"] is True
  assert result["has_crossroad"] is True
  assert result["image"]["imageBase64"] == "bW9jaw=="
  assert result["frame"] is not None
  assert result["frame"]["imageBase64"] == payload.decode("ascii")
  assert result["frame"]["imageWidth"] == 800
  assert result["frame"]["imageHeight"] == 480
  assert result["frame"]["source"] == "carrotNaviMediaSP:crossroad_minimized"


def test_crossroad_media_frame_falls_back_to_param(monkeypatch):
  storage = {
    CROSSROAD_PARAM: json.dumps({
      "distanceM": 150,
      "imageCode": 7,
      "imageUrl": "",
      "totalMeters": 500.0,
      "remainRatio": 0.5,
      "ts": 1726000000,
    }),
    IMAGE_PARAM: json.dumps({
      "show": True,
      "imageBase64": "YmFjaw==",
      "imageMime": "image/png",
      "imageEncoding": "base64",
      "imageWidth": 640,
      "imageHeight": 360,
      "imageHash": "fallback",
      "imageUrl": "",
      "imageTooLarge": False,
      "totalMeters": 500.0,
      "remainRatio": 0.5,
      "ts": 1726000000,
      "receivedMono": 1234.5,
    }),
  }
  monkeypatch.setattr("webui.server.bridge.carrot_navi_api._read_json_param", lambda key: _read(storage, key))
  monkeypatch.setattr("webui.server.bridge.carrot_navi_api.get_shared_sm", lambda: None)

  result = snapshot_carrot_crossroad()
  assert result["ok"] is True
  assert result["frame"] is None
  assert result["image"]["imageBase64"] == "YmFjaw=="


def test_crossroad_ignores_empty_or_oversized_media_frame(monkeypatch):
  storage = {
    CROSSROAD_PARAM: json.dumps({
      "distanceM": 200,
      "imageCode": 1,
      "totalMeters": 800.0,
      "remainRatio": 0.6,
      "ts": 1726000000,
    }),
    IMAGE_PARAM: json.dumps({
      "show": True,
      "imageBase64": "YmFjaw==",
      "imageMime": "image/png",
      "imageWidth": 640,
      "imageHeight": 360,
      "imageHash": "fallback",
      "totalMeters": 800.0,
      "remainRatio": 0.6,
      "ts": 1726000000,
    }),
  }

  # Empty payload should be ignored.
  empty_frame = _make_frame("crossroad_expanded", b"")
  sm_empty = _FakeSM(empty_frame)
  monkeypatch.setattr("webui.server.bridge.carrot_navi_api._read_json_param", lambda key: _read(storage, key))
  monkeypatch.setattr("webui.server.bridge.carrot_navi_api.get_shared_sm", lambda: sm_empty)
  result = snapshot_carrot_crossroad()
  assert result["frame"] is None
  assert result["image"]["imageBase64"] == "YmFjaw=="

  # Non-crossroad name should be ignored.
  wrong_name_frame = _make_frame("map_main", b"payload")
  sm_wrong = _FakeSM(wrong_name_frame)
  monkeypatch.setattr("webui.server.bridge.carrot_navi_api.get_shared_sm", lambda: sm_wrong)
  result = snapshot_carrot_crossroad()
  assert result["frame"] is None

  # Stale frame should be ignored.
  import time
  stale_ns = int((time.monotonic() - 10.0) * 1e9)
  stale_frame = _make_frame("crossroad_expanded", b"payload", received_mono_ns=stale_ns)
  sm_stale = _FakeSM(stale_frame)
  monkeypatch.setattr("webui.server.bridge.carrot_navi_api.get_shared_sm", lambda: sm_stale)
  result = snapshot_carrot_crossroad()
  assert result["frame"] is None
