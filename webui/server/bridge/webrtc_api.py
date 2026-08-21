"""WebRTC stream proxy to webrtcd."""

from __future__ import annotations

from typing import Any

WEBRTCD_PORT = 5001


def webrtc_schema() -> dict[str, Any]:
  try:
    import requests
    resp = requests.get(f"http://127.0.0.1:{WEBRTCD_PORT}/schema", timeout=2)
    if resp.ok:
      return {"ok": True, "schema": resp.json(), "port": WEBRTCD_PORT}
    return {"ok": False, "error": f"schema http {resp.status_code}"}
  except Exception as exc:
    return {"ok": False, "error": str(exc), "port": WEBRTCD_PORT}


def webrtc_offer(sdp: str, init_camera: str = "road") -> dict[str, Any]:
  camera = _normalize_camera(init_camera)
  try:
    from openpilot.system.webrtc.helpers import StreamRequestBody, post_stream_request, wait_for_webrtcd
    wait_for_webrtcd()
    body = StreamRequestBody(
      sdp=sdp,
      cameras=[camera],
      enabled=True,
      bridge_services_in=[],
      bridge_services_out=[],
    )
    result = post_stream_request(body)
    return {"ok": True, **result}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def _normalize_camera(init_camera: str) -> str:
  aliases = {
    "roadCameraState": "road",
    "narrowRoadCameraState": "road",
    "wideRoadCameraState": "wideRoad",
    "driverCameraState": "driver",
    "cabinCameraState": "driver",
  }
  cam = aliases.get(init_camera, init_camera)
  if cam not in ("road", "wideRoad", "driver"):
    return "road"
  return cam


def webrtc_notify(payload: dict[str, Any]) -> dict[str, Any]:
  try:
    import requests
    resp = requests.post(
      f"http://127.0.0.1:{WEBRTCD_PORT}/notify",
      json=payload,
      timeout=2,
    )
    if resp.ok:
      return {"ok": True}
    return {"ok": False, "error": f"notify http {resp.status_code}"}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}
