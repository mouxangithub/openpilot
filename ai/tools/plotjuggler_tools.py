"""PlotJuggler-style log summaries without launching GUI (tools/plotjuggler)."""

from __future__ import annotations

import math
from typing import Any

from ai.tools.op_run import resolve_route_ref, validate_route_ref

_PJ_SIGNALS = {
  "carState": ["vEgo", "steeringAngleDeg", "gas", "brake"],
  "controlsState": ["curvature", "lateralControlState/torqueState/desiredCurvature"],
  "carControl": ["actuators/accel", "actuators/torque"],
  "livePose": ["accelerationDevice/x", "velocityDevice/x"],
  "longitudinalPlan": ["aTarget"],
}


def _stats(vals: list[float]) -> dict[str, float | int | None]:
  clean = [float(v) for v in vals if v is not None and not (isinstance(v, float) and math.isnan(v))]
  if not clean:
    return {"count": 0, "min": None, "max": None, "mean": None}
  return {
    "count": len(clean),
    "min": round(min(clean), 4),
    "max": round(max(clean), 4),
    "mean": round(sum(clean) / len(clean), 4),
  }


def plotjuggler_data_summary(
  route: str,
  *,
  topics: list[str] | None = None,
  max_messages: int = 10000,
) -> dict[str, Any]:
  """Aggregate key signals from a route (no PlotJuggler binary)."""
  from ai.tools.route_tools import route_time_series

  topic_list = topics or list(_PJ_SIGNALS.keys())
  ts_res = route_time_series(route, topics=topic_list, max_messages=max_messages, max_points=2000)
  if not ts_res.get("ok"):
    return ts_res

  summary: dict[str, Any] = {}
  for topic, data in (ts_res.get("topics") or {}).items():
    topic_summary: dict[str, Any] = {}
    for sig in _PJ_SIGNALS.get(topic, []):
      vals = data.get(sig)
      if vals is None:
        continue
      topic_summary[sig] = _stats(list(vals))
    if topic_summary:
      summary[topic] = topic_summary

  return {
    "ok": True,
    "route": ts_res.get("route"),
    "signal_summary": summary,
    "messages_scanned": ts_res.get("messages_scanned"),
    "script": "tools/plotjuggler/juggle.py",
    "hint": "Full plots on PC: tools/plotjuggler/juggle.py <route> or --stream with replay.",
  }


def read_dbc_platform_map(*, limit: int = 80) -> dict[str, Any]:
  try:
    from openpilot.tools.cabana.dbc.generate_dbc_json import generate_dbc_dict
  except Exception as e:
    return {"ok": False, "error": str(e)}

  try:
    mapping = generate_dbc_dict()
  except Exception as e:
    return {"ok": False, "error": str(e)}

  items = [{"platform": k, "dbc": v} for k, v in sorted(mapping.items())]
  return {
    "ok": True,
    "count": len(items),
    "mapping": items[:limit],
    "script": "tools/cabana/dbc/generate_dbc_json.py",
    "hint": "Pair with read_dbc_file for signal details.",
  }
