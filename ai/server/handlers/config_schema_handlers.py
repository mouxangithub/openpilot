"""Schema-driven config and startup diagnostics endpoints (G12)."""
from __future__ import annotations
from typing import Any
from aiohttp import web
from ai.server.handlers._api_common import _json_response, _PARAMS
from ai.config.registry import ConfigRegistry
from ai.config.validator import validate_payload
from ai.core.diagnostics import run_startup_diagnostics
from ai.core.errors import ERR_CONFIG_INVALID, ERR_CONFIG_STALE, ERR_NOT_FOUND
from ai.common.storage import write_param, write_param_bool

_REGISTRY = ConfigRegistry()
# In-memory revision increments for local PATCH writes; initial values come from schemas.
_REVISIONS: dict[str, int] = {}


def _get_registry() -> ConfigRegistry:
  _REGISTRY.load_defaults()
  return _REGISTRY


async def api_get_config_schema(request: web.Request) -> web.Response:
  try:
    namespace = str(request.query.get("namespace") or "").strip()
    data = _get_registry().get_schema(namespace) if namespace else _get_registry().all()
    return _json_response({"ok": True, "data": data})
  except KeyError:
    return _json_response({"ok": False, "error_code": ERR_NOT_FOUND, "message": "namespace not found"}, status=404)
  except Exception as e:
    return _json_response({"ok": False, "error_code": ERR_CONFIG_INVALID, "message": str(e)}, status=400)


async def api_config_diagnose(request: web.Request) -> web.Response:
  result = run_startup_diagnostics(_PARAMS)
  return _json_response({"ok": result.ok, "data": result.to_dict()})


async def api_patch_config(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    return _json_response({"ok": False, "error_code": ERR_CONFIG_INVALID, "message": "invalid JSON"}, status=400)
  namespace = str(body.get("namespace") or "").strip()
  payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
  try:
    schema = _get_registry().get_schema(namespace)
  except KeyError:
    return _json_response({"ok": False, "error_code": ERR_NOT_FOUND, "message": "namespace not found"}, status=404)
  errors = validate_payload(schema, payload)
  if errors:
    return _json_response({"ok": False, "error_code": ERR_CONFIG_INVALID, "errors": errors}, status=400)
  expected = body.get("revision")
  current = _REVISIONS.get(namespace, int(schema.get("revision", 1)))
  if expected is not None and int(expected) != current:
    return _json_response({"ok": False, "error_code": ERR_CONFIG_STALE, "message": "revision conflict", "revision": current}, status=409)
  for key, value in payload.items():
    if isinstance(value, bool):
      write_param_bool(_PARAMS, key, value)
    else:
      write_param(_PARAMS, key, str(value))
  current += 1
  _REVISIONS[namespace] = current
  return _json_response({"ok": True, "data": {"namespace": namespace, "revision": current}})
