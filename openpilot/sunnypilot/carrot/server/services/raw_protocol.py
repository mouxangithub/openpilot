"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Wire format for the raw cereal relay on port 7000.

Identical to CarrotPilot's `realtime/raw_protocol.py`, because the companion app
(navipilot / CP 搭子) implements this exact handshake and framing:

    text frame  {"type": "hello", "services": [...], "protocolVersion": 1,
                 "mode": "raw-capnp-multiplex-relay",
                 "wireFormat": "service-name+capnp-frame"}
    binary frame  <len(service) as one byte> <service as utf-8> <capnp payload>

The payload is the untouched cereal event body, so the client decodes it with the same
capnp schema the device publishes.
"""

RAW_PROTOCOL_VERSION = 1
RAW_WIRE_FORMAT = "cereal-event-capnp"
RAW_MODE = "raw-capnp-relay"
RAW_MULTIPLEX_WIRE_FORMAT = "service-name+capnp-frame"
RAW_MULTIPLEX_MODE = "raw-capnp-multiplex-relay"


def build_raw_hello(*, service: str) -> dict:
  return {
    "type": "hello",
    "service": service,
    "protocolVersion": RAW_PROTOCOL_VERSION,
    "mode": RAW_MODE,
    "wireFormat": RAW_WIRE_FORMAT,
  }


def build_raw_multiplex_hello(*, services: list[str]) -> dict:
  return {
    "type": "hello",
    "services": services,
    "protocolVersion": RAW_PROTOCOL_VERSION,
    "mode": RAW_MULTIPLEX_MODE,
    "wireFormat": RAW_MULTIPLEX_WIRE_FORMAT,
  }


def encode_raw_multiplex_frame(*, service: str, payload: bytes) -> bytes:
  """Prefix a capnp payload with its (length-prefixed) service name."""
  service_bytes = service.encode("utf-8")
  if len(service_bytes) > 255:
    raise ValueError("service name too long for multiplex frame")
  return bytes([len(service_bytes)]) + service_bytes + payload
