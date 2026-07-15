"""Route comparison, CAN stats, message search, batch summaries."""

from __future__ import annotations

import os
from collections import Counter
from typing import Any

from ai.tools.op_run import ROUTES_DIR, resolve_route_ref, validate_route_ref


def _import_logreader():
  try:
    from openpilot.tools.lib.logreader import LogReader, ReadMode
    return LogReader, ReadMode
  except ImportError:
    from tools.lib.logreader import LogReader, ReadMode  # type: ignore
    return LogReader, ReadMode


def route_can_stats(route: str, *, max_batches: int = 2000) -> dict[str, Any]:
  """Read-only CAN stats from route logs (no hardware replay)."""
  err = validate_route_ref(route)
  if err:
    return {"ok": False, "error": err}
  route_arg = resolve_route_ref(route)

  try:
    from openpilot.selfdrive.pandad import can_capnp_to_list
    LogReader, ReadMode = _import_logreader()
  except Exception as e:
    return {"ok": False, "error": str(e)}

  try:
    lr = LogReader(route_arg, ReadMode.AUTO)
    mbytes = []
    for i, m in enumerate(lr):
      if m.which() != "can":
        continue
      mbytes.append(m.as_builder().to_bytes())
      if len(mbytes) >= max_batches:
        break
    if not mbytes:
      return {"ok": False, "error": "No can messages in route", "route": route_arg}

    frames = [item for batch in can_capnp_to_list(mbytes) for item in batch]
    id_counter: Counter[int] = Counter()
    bus_counter: Counter[int] = Counter()
    for _ts, _src, address, _dat, bus in frames:
      id_counter[address] += 1
      bus_counter[bus] += 1

    top_ids = [{"address": hex(a), "count": c} for a, c in id_counter.most_common(30)]
    return {
      "ok": True,
      "route": route_arg,
      "can_batches": len(mbytes),
      "can_frames": len(frames),
      "unique_ids": len(id_counter),
      "buses": dict(sorted(bus_counter.items())),
      "top_ids": top_ids,
      "script": "tools/replay/can_replay.py (read-only analysis)",
      "hint": "Hardware replay intentionally not exposed to AI.",
    }
  except Exception as e:
    return {"ok": False, "error": str(e), "route": route_arg}


def compare_route_signals(
  route_a: str,
  route_b: str,
  *,
  topics: list[str] | None = None,
) -> dict[str, Any]:
  from ai.tools.plotjuggler_tools import plotjuggler_data_summary

  for label, route in (("a", route_a), ("b", route_b)):
    err = validate_route_ref(route)
    if err:
      return {"ok": False, "error": f"route_{label}: {err}"}

  sum_a = plotjuggler_data_summary(route_a, topics=topics, max_messages=6000)
  sum_b = plotjuggler_data_summary(route_b, topics=topics, max_messages=6000)
  if not sum_a.get("ok"):
    return sum_a
  if not sum_b.get("ok"):
    return sum_b

  diffs: dict[str, Any] = {}
  sig_a = sum_a.get("signal_summary") or {}
  sig_b = sum_b.get("signal_summary") or {}
  all_topics = set(sig_a.keys()) | set(sig_b.keys())
  for topic in sorted(all_topics):
    topic_diff: dict[str, Any] = {}
    keys = set((sig_a.get(topic) or {}).keys()) | set((sig_b.get(topic) or {}).keys())
    for key in sorted(keys):
      ma = (sig_a.get(topic) or {}).get(key) or {}
      mb = (sig_b.get(topic) or {}).get(key) or {}
      if not ma or not mb:
        topic_diff[key] = {"only_in": "a" if ma else "b"}
        continue
      delta = {}
      for stat in ("mean", "min", "max"):
        va, vb = ma.get(stat), mb.get(stat)
        if va is not None and vb is not None:
          delta[stat] = round(float(vb) - float(va), 4)
      if delta:
        topic_diff[key] = {"a": ma, "b": mb, "delta_b_minus_a": delta}
    if topic_diff:
      diffs[topic] = topic_diff

  return {
    "ok": True,
    "route_a": sum_a.get("route"),
    "route_b": sum_b.get("route"),
    "signal_diff": diffs,
    "summary_a": sum_a.get("signal_summary"),
    "summary_b": sum_b.get("signal_summary"),
    "hint": "Positive delta = route_b higher than route_a (e.g. after tune).",
  }


_TUNE_SIGNAL_HINTS = {
  "carState": {
    "vEgo": "avg speed",
    "steeringAngleDeg": "steering activity",
    "aEgo": "longitudinal accel",
  },
  "controlsState": {
    "curvature": "path curvature command",
    "accel": "longitudinal command",
  },
}


def compare_tune_ab(
  route_a: str,
  route_b: str,
  *,
  label_a: str = "before",
  label_b: str = "after",
) -> dict[str, Any]:
  """A/B route comparison focused on tune-relevant signals + narrative summary."""
  base = compare_route_signals(route_a, route_b)
  if not base.get("ok"):
    return base

  highlights: list[dict[str, Any]] = []
  signal_diff = base.get("signal_diff") or {}
  for topic, topic_diff in signal_diff.items():
    hints = _TUNE_SIGNAL_HINTS.get(topic, {})
    for field, info in topic_diff.items():
      if not isinstance(info, dict) or "delta_b_minus_a" not in info:
        continue
      delta = info["delta_b_minus_a"]
      mean_d = delta.get("mean")
      if mean_d is None:
        continue
      if abs(mean_d) < 0.02 and topic != "controlsState":
        continue
      highlights.append({
        "topic": topic,
        "field": field,
        "label": hints.get(field, field),
        f"{label_a}": (info.get("a") or {}).get("mean"),
        f"{label_b}": (info.get("b") or {}).get("mean"),
        "delta_mean": mean_d,
      })

  highlights.sort(key=lambda x: abs(float(x.get("delta_mean") or 0)), reverse=True)
  recommendations: list[str] = []
  for h in highlights[:6]:
    field = h.get("field", "")
    d = float(h.get("delta_mean") or 0)
    if field == "steeringAngleDeg" and abs(d) > 2:
      recommendations.append(
        "横向活动变化明显：检查 dp_lat_alka / 横向增益，对比 lat_maneuver_report"
      )
    if field in ("aEgo", "accel") and abs(d) > 0.15:
      recommendations.append(
        "纵向加减速变化明显：检查 LongitudinalPersonality / dp_lon_acm / dp_lon_aem"
      )

  if not recommendations and highlights:
    recommendations.append("信号差异较小，当前调优可能已接近目标；可再跑一条同路段对比")
  if not highlights:
    recommendations.append("两路线信号统计接近，建议确认是否为同路段/相似速度")

  return {
    **base,
    "label_a": label_a,
    "label_b": label_b,
    "tune_highlights": highlights[:12],
    "tune_recommendations": recommendations[:5],
    "hint": "Use with snapshot_tune_state / list_tune_snapshots to correlate param changes.",
  }


def batch_route_summary(*, limit: int = 5) -> dict[str, Any]:
  from ai.tools.diagnostics_tools import analyze_route_summary
  from ai.tools.plotjuggler_tools import plotjuggler_data_summary

  if not os.path.isdir(ROUTES_DIR):
    return {"ok": False, "error": f"Routes dir not found: {ROUTES_DIR}"}

  names = []
  try:
    for name in os.listdir(ROUTES_DIR):
      p = os.path.join(ROUTES_DIR, name)
      if os.path.isdir(p) and "|" in name:
        names.append((name, os.path.getmtime(p)))
  except OSError as e:
    return {"ok": False, "error": str(e)}

  names.sort(key=lambda x: x[1], reverse=True)
  items: list[dict[str, Any]] = []
  for name, mtime in names[: max(1, min(limit, 20))]:
    folder = name.split("|")[-1] if "|" in name else name
    summary = analyze_route_summary(folder)
    signals = plotjuggler_data_summary(f"{name}/0", max_messages=3000)
    v_ego = None
    if signals.get("ok"):
      cs = (signals.get("signal_summary") or {}).get("carState", {})
      mean = (cs.get("vEgo") or {}).get("mean")
      if mean is not None:
        v_ego = mean
    items.append({
      "route": name,
      "mtime": mtime,
      "segment_count": summary.get("segment_count"),
      "has_qlog": summary.get("has_qlog"),
      "vEgo_mean": v_ego,
      "signal_ok": bool(signals.get("ok")),
    })

  return {"ok": True, "count": len(items), "routes": items, "routes_dir": ROUTES_DIR}


def search_route_messages(
  route: str,
  message_type: str,
  *,
  max_hits: int = 20,
) -> dict[str, Any]:
  err = validate_route_ref(route)
  if err:
    return {"ok": False, "error": err}
  msg_type = (message_type or "").strip()
  if not msg_type:
    return {"ok": False, "error": "message_type required (e.g. carParams, can, ubloxRaw)"}

  route_arg = resolve_route_ref(route)
  try:
    LogReader, ReadMode = _import_logreader()
  except Exception as e:
    return {"ok": False, "error": str(e)}

  try:
    lr = LogReader(route_arg, ReadMode.AUTO)
    hits: list[dict[str, Any]] = []
    total = 0
    for msg in lr:
      if msg.which() == msg_type:
        total += 1
        if len(hits) < max_hits:
          hits.append({
            "logMonoTime": msg.logMonoTime,
            "which": msg.which(),
          })
    return {
      "ok": True,
      "route": route_arg,
      "message_type": msg_type,
      "total_matches": total,
      "sample_hits": hits,
      "script": "tools/car_porting/examples/find_segments_with_message.ipynb",
    }
  except Exception as e:
    return {"ok": False, "error": str(e), "route": route_arg}
