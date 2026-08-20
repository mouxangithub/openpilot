"""WebRTC / livestream health snapshot for WebUI diagnostics."""

from __future__ import annotations

import socket
from typing import Any


def _port_open(host: str, port: int, timeout: float = 0.3) -> bool:
  try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    ok = s.connect_ex((host, port)) == 0
    s.close()
    return ok
  except Exception:
    return False


def _stream_stack_status(livestreaming: bool, webrtcd: bool) -> str:
  if livestreaming and webrtcd:
    return "active"
  if livestreaming or webrtcd:
    return "partial"
  return "off"


def snapshot_stream_health() -> dict[str, Any]:
  """Read-only livestream metrics — does not affect driving stack."""
  out: dict[str, Any] = {
    "ok": True,
    "livestreaming": False,
    "encoder_bitrate": None,
    "active_camera": None,
    "webrtcd_port": 5001,
    "webrtcd_listening": False,
    "stream_stack": "off",
    "thermal": "ok",
    "cpu_temp": None,
    "memory_usage_percent": None,
    "gpu_usage_percent": None,
    "cpu_usage_percent": None,
    "free_space_percent": None,
    "power_draw_w": None,
    "encoder_lagging": False,
  }
  try:
    from openpilot.common.params import Params
    p = Params()
    out["livestreaming"] = p.get_bool("IsLiveStreaming")
    br = p.get("LivestreamEncoderBitrate")
    if br:
      out["encoder_bitrate"] = int(br)
    out["active_camera"] = p.get("LivestreamActiveCamera") or None
    out["encoder_lagging"] = p.get_bool("LivestreamEncoderLagging")
  except Exception as exc:
    out["ok"] = False
    out["error"] = str(exc)
    return out

  out["webrtcd_listening"] = _port_open("127.0.0.1", int(out["webrtcd_port"]))
  out["stream_stack"] = _stream_stack_status(out["livestreaming"], out["webrtcd_listening"])

  try:
    from webui.server.bridge.state_hub import get_state
    st = get_state()
    dev = st.get("device") or {}
    out["thermal"] = dev.get("thermal", "ok")
    out["cpu_temp"] = dev.get("cpu_temp")
    out["memory_usage_percent"] = dev.get("memory_usage_percent")
    out["gpu_usage_percent"] = dev.get("gpu_usage_percent")
    out["cpu_usage_percent"] = dev.get("cpu_usage_percent")
    out["free_space_percent"] = dev.get("free_space_percent")
    out["power_draw_w"] = dev.get("power_draw_w")
  except Exception:
    pass

  return out
