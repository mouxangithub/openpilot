"""WebSocket sync protocol v2 — schemas, connect handshake, validation."""

from __future__ import annotations

from typing import Any

WS_PROTOCOL_VERSION = 2
WS_MIN_CLIENT_VERSION = 1

PROTOCOL_SCHEMA: dict[str, Any] = {
  "version": WS_PROTOCOL_VERSION,
  "minClientVersion": WS_MIN_CLIENT_VERSION,
  "handshake": {
    "clientFirstFrame": "connect",
    "serverFirstFrame": "hello",
  },
  "messages": {
    "connect": {
      "type": "object",
      "required": ["type", "protocolVersion"],
      "properties": {
        "type": {"const": "connect"},
        "protocolVersion": {"type": "integer"},
        "client": {"type": "string"},
        "capabilities": {"type": "array"},
      },
    },
    "connect_ack": {
      "type": "object",
      "required": ["type", "protocolVersion", "ok"],
      "properties": {
        "type": {"const": "connect_ack"},
        "protocolVersion": {"type": "integer"},
        "ok": {"type": "boolean"},
        "error": {"type": "string"},
      },
    },
    "hello": {
      "type": "object",
      "required": ["type", "sessions", "stateVersion", "config", "protocolVersion"],
      "properties": {
        "type": {"const": "hello"},
        "sessions": {"type": "array"},
        "stateVersion": {"type": "integer"},
        "protocolVersion": {"type": "integer"},
        "config": {"type": "object"},
        "activeJobs": {"type": "array"},
        "agents": {"type": "array"},
        "agentsConfig": {"type": "object"},
        "office": {"type": "object"},
      },
    },
    "chat_event": {
      "type": "object",
      "required": ["type", "jobId", "sessionId", "event"],
      "properties": {
        "type": {"const": "chat_event"},
        "jobId": {"type": "string"},
        "sessionId": {"type": "string"},
        "event": {"type": "object"},
        "status": {"type": "string"},
        "assistant": {"type": "object"},
        "seq": {"type": "integer"},
        "nextSince": {"type": "integer"},
      },
    },
    "chat_status": {
      "type": "object",
      "required": ["type", "jobId", "sessionId", "status"],
      "properties": {
        "type": {"const": "chat_status"},
        "jobId": {"type": "string"},
        "sessionId": {"type": "string"},
        "status": {"enum": ["running", "done", "error", "cancelled", "queued"]},
        "assistant": {"type": "object"},
        "error": {"type": "string"},
        "resolvedModel": {"type": "string"},
        "runId": {"type": "string"},
      },
    },
    "canvas": {
      "type": "object",
      "required": ["type", "sessionId", "artifact"],
      "properties": {
        "type": {"const": "canvas"},
        "sessionId": {"type": "string"},
        "artifact": {"type": "object"},
      },
    },
    "lifecycle": {
      "type": "object",
      "required": ["type", "phase", "runId"],
      "properties": {
        "type": {"const": "lifecycle"},
        "phase": {"enum": ["start", "end", "stuck"]},
        "runId": {"type": "string"},
        "sessionId": {"type": "string"},
        "jobId": {"type": "string"},
      },
    },
    "protocol_error": {
      "type": "object",
      "required": ["type", "error"],
      "properties": {
        "type": {"const": "protocol_error"},
        "error": {"type": "string"},
        "field": {"type": "string"},
      },
    },
    "ping": {"type": "object", "required": ["type"], "properties": {"type": {"const": "ping"}}},
    "pong": {"type": "object", "required": ["type"], "properties": {"type": {"const": "pong"}}},
    "resync": {"type": "object", "required": ["type"], "properties": {"type": {"const": "resync"}}},
  },
}

_INBOUND_TYPES = frozenset({
  "connect", "ping", "pong", "resync",
})


def _check_type(value: Any, expected: str) -> bool:
  if expected == "string":
    return isinstance(value, str)
  if expected == "integer":
    return isinstance(value, int) and not isinstance(value, bool)
  if expected == "boolean":
    return isinstance(value, bool)
  if expected == "array":
    return isinstance(value, list)
  if expected == "object":
    return isinstance(value, dict)
  return True


def validate_ws_message(
  data: dict[str, Any],
  *,
  direction: str = "outbound",
) -> tuple[bool, str | None]:
  if not isinstance(data, dict):
    return False, "message must be an object"
  msg_type = data.get("type")
  if not msg_type or not isinstance(msg_type, str):
    return False, "missing type"
  if direction == "inbound" and msg_type not in _INBOUND_TYPES and msg_type not in PROTOCOL_SCHEMA["messages"]:
    return False, f"inbound type not allowed: {msg_type}"
  schema = PROTOCOL_SCHEMA["messages"].get(msg_type)
  if not schema:
    return True, None
  for key in schema.get("required", []):
    if key not in data:
      return False, f"{msg_type}: missing required field {key}"
  props = schema.get("properties", {})
  for key, spec in props.items():
    if key not in data:
      continue
    val = data[key]
    if "const" in spec and val != spec["const"]:
      return False, f"{msg_type}.{key}: expected {spec['const']!r}"
    if "enum" in spec and val not in spec["enum"]:
      return False, f"{msg_type}.{key}: invalid enum value"
    if "type" in spec and not _check_type(val, spec["type"]):
      return False, f"{msg_type}.{key}: expected {spec['type']}"
  return True, None


def negotiate_client_version(client_version: int) -> tuple[bool, str | None]:
  if client_version < WS_MIN_CLIENT_VERSION:
    return False, f"client protocol {client_version} < min {WS_MIN_CLIENT_VERSION}"
  if client_version > WS_PROTOCOL_VERSION:
    return True, None
  return True, None


def get_protocol_schema() -> dict[str, Any]:
  return PROTOCOL_SCHEMA
