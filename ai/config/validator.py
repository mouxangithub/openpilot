"""Schema payload validation with stable machine-readable diagnostics."""
from __future__ import annotations
from typing import Any
from ai.core.errors import ERR_CONFIG_INVALID


def validate_payload(schema: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]]:
  errors: list[dict[str, Any]] = []
  fields = schema.get("fields", {}) if isinstance(schema, dict) else {}
  if not isinstance(payload, dict):
    return [{"field": "", "code": ERR_CONFIG_INVALID, "message": "payload must be an object"}]
  for key in payload:
    if key not in fields:
      errors.append({"field": key, "code": ERR_CONFIG_INVALID, "message": f"unknown field: {key}"})
  for key, value in payload.items():
    field = fields.get(key)
    if not isinstance(field, dict):
      continue
    typ = str(field.get("type", "string"))
    valid_type = (
      (typ in ("string", "secret", "enum") and isinstance(value, str))
      or (typ == "number" and isinstance(value, (int, float)) and not isinstance(value, bool))
      or (typ == "boolean" and isinstance(value, bool))
      or (typ == "list" and isinstance(value, list))
      or (typ == "object" and isinstance(value, dict))
    )
    if not valid_type:
      errors.append({"field": key, "code": ERR_CONFIG_INVALID, "message": f"invalid type for {key}"})
      continue
    if field.get("enum") is not None and value not in field["enum"]:
      errors.append({"field": key, "code": ERR_CONFIG_INVALID, "message": f"invalid enum value for {key}"})
    for bound, op in (("min", lambda a, b: a < b), ("max", lambda a, b: a > b)):
      if field.get(bound) is not None and isinstance(value, (int, float)) and op(value, field[bound]):
        errors.append({"field": key, "code": ERR_CONFIG_INVALID, "message": f"{key} below min" if bound == "min" else f"{key} above max"})
  return errors


def collect_errors(schema: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
  errors = validate_payload(schema, payload)
  return {"ok": not errors, "errors": errors}
