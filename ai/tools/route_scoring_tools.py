"""Quantitative route tune scoring for op助手."""

from __future__ import annotations

import math
from typing import Any

from ai.tools.op_run import validate_route_ref
from ai.tools.route_analysis_tools import compare_tune_ab


def _jerk_from_series(vals: list | None) -> float | None:
  if not vals or len(vals) < 3:
    return None
  clean = [float(v) for v in vals if v is not None and not (isinstance(v, float) and math.isnan(v))]
  if len(clean) < 3:
    return None
  diffs = [abs(clean[i] - clean[i - 1]) for i in range(1, len(clean))]
  return round(sum(diffs) / len(diffs), 4)


def _steering_rms(vals: list | None) -> float | None:
  if not vals:
    return None
  clean = [float(v) for v in vals if v is not None and not (isinstance(v, float) and math.isnan(v))]
  if not clean:
    return None
  mean = sum(clean) / len(clean)
  var = sum((x - mean) ** 2 for x in clean) / len(clean)
  return round(math.sqrt(var), 4)


def score_route_tune(route: str) -> dict[str, Any]:
  """Score a single route for tune quality (higher composite = better comfort)."""
  err = validate_route_ref(route)
  if err:
    return {"ok": False, "error": err}

  from ai.tools.route_tools import route_time_series

  ts = route_time_series(
    route,
    topics=["carState", "livePose", "controlsState"],
    max_messages=8000,
    max_points=1500,
  )
  if not ts.get("ok"):
    return ts

  topics = ts.get("topics") or {}
  cs = topics.get("carState") or {}
  lp = topics.get("livePose") or {}
  ctrl = topics.get("controlsState") or {}

  v_vals = cs.get("vEgo") or []
  steer = cs.get("steeringAngleDeg") or []
  accel = lp.get("accelerationDevice/x") or []

  v_clean = [float(v) for v in v_vals if v is not None]
  v_mean = round(sum(v_clean) / len(v_clean), 3) if v_clean else None
  steer_rms = _steering_rms(steer)
  long_jerk = _jerk_from_series(accel)

  enabled_ratio = None
  en = ctrl.get("enabled")
  if en:
    on = sum(1 for x in en if x)
    enabled_ratio = round(on / len(en), 3)

  metrics = {
    "vEgo_mean_mps": v_mean,
    "steering_rms_deg": steer_rms,
    "long_jerk": long_jerk,
    "engage_ratio": enabled_ratio,
  }

  score = 70.0
  if steer_rms is not None:
    score -= min(25, steer_rms * 0.8)
  if long_jerk is not None:
    score -= min(25, long_jerk * 40)
  if enabled_ratio is not None:
    score += (enabled_ratio - 0.85) * 30
  if v_mean is not None and v_mean < 2:
    score -= 10
  score = max(0, min(100, round(score, 1)))
  grade = "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D"

  return {
    "ok": True,
    "route": ts.get("route"),
    "metrics": metrics,
    "composite_score": score,
    "grade": grade,
    "hint": "Use score_tune_session to compare before/after routes.",
  }


def score_tune_session(
  route_before: str,
  route_after: str,
  *,
  min_score_delta: float = -5.0,
) -> dict[str, Any]:
  """Compare before/after route scores; pass if composite did not regress beyond threshold."""
  a = score_route_tune(route_before)
  b = score_route_tune(route_after)
  if not a.get("ok"):
    return a
  if not b.get("ok"):
    return b

  sa = float(a.get("composite_score") or 0)
  sb = float(b.get("composite_score") or 0)
  delta = round(sb - sa, 2)
  passed = delta >= min_score_delta

  ab = compare_tune_ab(route_before, route_after, label_a="before", label_b="after")

  return {
    "ok": True,
    "route_before": a.get("route"),
    "route_after": b.get("route"),
    "score_before": sa,
    "score_after": sb,
    "score_delta": delta,
    "passed": passed,
    "min_score_delta": min_score_delta,
    "grade_before": a.get("grade"),
    "grade_after": b.get("grade"),
    "metrics_before": a.get("metrics"),
    "metrics_after": b.get("metrics"),
    "tune_highlights": ab.get("tune_highlights", [])[:6] if ab.get("ok") else [],
    "recommendation": (
      "调参后评分未明显下降，可保留当前参数。"
      if passed
      else f"评分下降 {abs(delta)} 分，建议 restore_tune_snapshot 或回滚。"
    ),
  }


def batch_compare_routes_tune(
  routes: list[str],
  *,
  baseline: str = "",
  limit: int = 8,
) -> dict[str, Any]:
  """Score multiple routes; optional baseline for delta ranking."""
  if not routes:
    return {"ok": False, "error": "routes list required"}
  lim = max(1, min(int(limit or 8), 20))
  names = [str(r).strip() for r in routes if str(r).strip()][:lim]
  if not names:
    return {"ok": False, "error": "no valid route names"}

  scored: list[dict[str, Any]] = []
  errors: list[str] = []
  for name in names:
    res = score_route_tune(name)
    if res.get("ok"):
      scored.append({
        "route": res.get("route") or name,
        "composite_score": res.get("composite_score"),
        "grade": res.get("grade"),
        "metrics": res.get("metrics"),
      })
    else:
      errors.append(f"{name}: {res.get('error')}")

  scored.sort(key=lambda x: float(x.get("composite_score") or 0), reverse=True)
  base_score = None
  base_name = (baseline or "").strip()
  if base_name:
    base = score_route_tune(base_name)
    if base.get("ok"):
      base_score = float(base.get("composite_score") or 0)
      for row in scored:
        s = float(row.get("composite_score") or 0)
        row["delta_vs_baseline"] = round(s - base_score, 2)

  return {
    "ok": True,
    "baseline": base_name or None,
    "baseline_score": base_score,
    "ranked": scored,
    "best": scored[0] if scored else None,
    "worst": scored[-1] if scored else None,
    "errors": errors[:5],
    "hint": "Use compare_tune_ab on top-2 routes for signal-level diff.",
  }
