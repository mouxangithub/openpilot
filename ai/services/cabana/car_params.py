"""Cabana car_params module."""
from ai.services.cabana.deps import *
_CAR_PARAM_KEYS = (
  "CarParams",
  "CarParamsCache",
  "CarParamsPersistent",
  "CarParamsPrevRoute",
)


def _car_params_from_bytes(raw: bytes) -> dict[str, Any] | None:
  try:
    from cereal import car
    with car.CarParams.from_bytes(raw) as cp:
      return {
        "brand": cp.brand,
        "carFingerprint": cp.carFingerprint,
        "openpilotLongitudinalControl": bool(cp.openpilotLongitudinalControl),
      }
  except Exception:
    return None


def _load_car_params_from_params() -> dict[str, Any] | None:
  params = Params()
  for key in _CAR_PARAM_KEYS:
    raw = params.get(key)
    if raw:
      cp = _car_params_from_bytes(raw)
      if cp:
        return cp
  return None


def _load_car_params_from_cereal() -> dict[str, Any] | None:
  if messaging is None:
    return None
  try:
    sm = messaging.SubMaster(["carParams"])
    sm.update(2000)
    cp = sm["carParams"]
    if cp and cp.carFingerprint:
      return {
        "brand": cp.brand,
        "carFingerprint": cp.carFingerprint,
        "openpilotLongitudinalControl": bool(cp.openpilotLongitudinalControl),
      }
  except Exception as e:
    cloudlog.warning(f"cabana: failed to read live carParams: {e}")
  return None


def _load_car_params() -> dict[str, Any] | None:
  return _load_car_params_from_params() or _load_car_params_from_cereal()


def _load_car_params_from_profile() -> dict[str, Any] | None:
  """Fallback: ai_vehicle_profile written by aid state sync."""
  try:
    raw = Params().get("ai_vehicle_profile")
    if not raw:
      return None
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="replace")
    profile = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(profile, dict):
      return None
    fingerprint = (
      profile.get("fingerprint")
      or profile.get("carFingerprint")
      or profile.get("car_fingerprint")
      or ""
    ).strip()
    if not fingerprint:
      return None
    return {
      "brand": (profile.get("brand") or "").strip(),
      "carFingerprint": fingerprint,
      "openpilotLongitudinalControl": bool(profile.get("openpilotLongitudinalControl")),
      "source": "profile",
    }
  except Exception:
    return None


def _load_car_params_from_route(route_name: str) -> dict[str, Any] | None:
  """Read carParams from a local route qlog/rlog (replay DBC auto-detect)."""
  if LogReader is None or not route_name:
    return None
  base = _route_dir(route_name)
  if base is None:
    return None
  log_paths = _find_qlogs(base) or _find_rlogs(base)
  if not log_paths:
    return None
  for log_path in log_paths:
    try:
      lr = LogReader(str(log_path))
      cp_msg = lr.first("carParams") if hasattr(lr, "first") else None
      if cp_msg is None:
        for msg in lr:
          if msg.which() == "carParams":
            cp_msg = msg
            break
      if cp_msg is None:
        continue
      cp = getattr(cp_msg, "carParams", cp_msg)
      fingerprint = getattr(cp, "carFingerprint", "") or ""
      if not fingerprint:
        continue
      return {
        "brand": getattr(cp, "brand", "") or "",
        "carFingerprint": fingerprint,
        "openpilotLongitudinalControl": bool(getattr(cp, "openpilotLongitudinalControl", False)),
        "source": "route",
        "route": route_name,
      }
    except Exception as e:
      cloudlog.warning(f"cabana: carParams from {log_path.name}: {e}")
  return None


def _resolve_car_params(route_name: str = "") -> dict[str, Any] | None:
  route_name = (route_name or "").strip()
  if route_name:
    cp = _load_car_params_from_route(route_name)
    if cp is not None:
      return cp
  cp = _load_car_params() or _load_car_params_from_profile()
  if cp is not None:
    cp = dict(cp)
    cp.setdefault("source", "device")
  return cp

