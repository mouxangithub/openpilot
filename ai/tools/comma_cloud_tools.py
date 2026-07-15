"""Comma API route listing for op助手."""

from __future__ import annotations

from typing import Any


def _api_call(func) -> dict[str, Any]:
  try:
    from openpilot.tools.lib.api import CommaApi, UnauthorizedError, APIError
    from openpilot.tools.lib.auth_config import get_token
    return {"ok": True, "data": func(CommaApi(get_token()))}
  except UnauthorizedError:
    return {"ok": False, "error": "unauthorized", "hint": "Run comma auth on device or PC."}
  except APIError as e:
    code = getattr(e, "status_code", 0)
    return {"ok": False, "error": "not_found" if code == 404 else str(e)}
  except Exception as e:
    return {"ok": False, "error": str(e)}


def list_comma_devices() -> dict[str, Any]:
  """List comma devices for authenticated user."""
  res = _api_call(lambda api: api.get("v1/me/devices/"))
  if not res.get("ok"):
    return res
  devices = res.get("data") or []
  slim = []
  for d in devices[:20]:
    if isinstance(d, dict):
      slim.append({
        "dongle_id": d.get("dongle_id") or d.get("device_id"),
        "alias": d.get("alias"),
        "hardware_version": d.get("hardware_version"),
        "last_athena_ping": d.get("last_athena_ping"),
      })
  return {"ok": True, "count": len(slim), "devices": slim}


def list_comma_routes(
  *,
  dongle_id: str = "",
  limit: int = 20,
  preserved: bool = False,
) -> dict[str, Any]:
  """List cloud routes for a dongle (from Params DongleId if omitted)."""
  did = (dongle_id or "").strip()
  if not did:
    try:
      from openpilot.common.params import Params
      raw = Params().get("DongleId")
      if raw:
        did = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw)
    except Exception:
      pass
  if not did:
    return {"ok": False, "error": "dongle_id required or set DongleId param"}

  lim = max(1, min(int(limit or 20), 100))

  def fetch(api):
    if preserved:
      return api.get(f"v1/devices/{did}/routes/preserved")
    return api.get(f"v1/devices/{did}/routes_segments", params={"start": 0, "end": lim})

  res = _api_call(fetch)
  if not res.get("ok"):
    return res
  data = res.get("data")
  if isinstance(data, list):
    routes = data[:lim]
  elif isinstance(data, dict):
    routes = (data.get("routes") or data.get("segments") or [])[:lim]
  else:
    routes = []
  return {"ok": True, "dongle_id": did, "count": len(routes), "routes": routes[:lim]}
