"""Extended diagnostic tools for op助手."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from openpilot.common.params import Params

from ai.tools.dp_settings import list_dp_settings
from ai.tools.op_run import ROUTES_DIR
from ai.tools.params_policy import load_catalog

_ROUTES_DIR = ROUTES_DIR

_TUNE_KEY_PREFIXES = ("dp_lat_", "dp_lon_", "dp_ui_", "dp_toyota_", "dp_honda_", "dp_vag_")
_TUNE_EXTRA = frozenset({
  "LongitudinalPersonality", "ExperimentalMode", "IsLdwEnabled",
  "DisengageOnAccelerator", "dp_dev_model_selected",
})


async def fetch_dashy_settings(timeout: float = 3.0) -> dict[str, Any]:
  import aiohttp
  url = "http://127.0.0.1:5088/api/settings"
  try:
    async with aiohttp.ClientSession() as session:
      async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
        if resp.status != 200:
          return {"ok": False, "error": f"Dashy HTTP {resp.status}", "url": url}
        data = await resp.json()
        return {"ok": True, "source": "dashy", "url": url, "data": data}
  except Exception as e:
    return {"ok": False, "error": str(e), "hint": "Is Dashy running (dp_dev_dashy)? Use list_dp_settings as fallback."}


def read_manager_log(params: Params, *, lines: int = 80) -> dict[str, Any]:
  raw = params.get("dp_dev_last_log")
  text = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw or "")
  if not text.strip():
    from ai.system.shell import run_command
    tail = run_command("tail_params_log")
    text = tail.get("stdout", "") or text
  chunk = "\n".join(text.splitlines()[-lines:])
  return {"ok": True, "lines": lines, "log": chunk}


def grep_log(params: Params, pattern: str, *, lines: int = 200) -> dict[str, Any]:
  if not pattern or len(pattern) > 120:
    return {"ok": False, "error": "pattern required (max 120 chars)"}
  try:
    rx = re.compile(pattern, re.IGNORECASE)
  except re.error as e:
    return {"ok": False, "error": f"Invalid regex: {e}"}
  log = read_manager_log(params, lines=lines).get("log", "")
  matches = [ln for ln in log.splitlines() if rx.search(ln)]
  return {"ok": True, "pattern": pattern, "match_count": len(matches), "matches": matches[:50]}


def read_onroad_events(get_state_reader) -> dict[str, Any]:
  state = get_state_reader().update(timeout=0)
  events = getattr(state, "onroad_events", None) or []
  simplified = []
  for evt in events:
    if isinstance(evt, dict):
      simplified.append({
        "name": evt.get("name"),
        "no_entry": evt.get("no_entry"),
        "soft_disable": evt.get("soft_disable"),
        "immediate_disable": evt.get("immediate_disable"),
        "permanent": evt.get("permanent"),
      })
  return {
    "ok": True,
    "vEgo": round(state.v_ego, 3),
    "enabled": state.enabled,
    "event_count": len(simplified),
    "events": simplified,
  }


def snapshot_tune_state(params: Params, brand: str = "") -> dict[str, Any]:
  catalog = load_catalog()
  snapshot: dict[str, Any] = {}
  for key, meta in catalog.items():
    tier = meta.get("tier", "")
    if tier not in ("write_offroad_tune", "write_offroad_ui"):
      continue
    if key.startswith(_TUNE_KEY_PREFIXES) or key in _TUNE_EXTRA:
      try:
        val = params.get(key)
        if isinstance(val, bytes):
          val = val.decode(errors="replace")
        snapshot[key] = val
      except Exception:
        snapshot[key] = None
  dp = list_dp_settings(params, brand=brand)
  return {
    "ok": True,
    "brand": brand,
    "param_count": len(snapshot),
    "params": snapshot,
    "setting_count": dp.get("setting_count", 0),
  }


def diff_params(params: Params, proposed: dict[str, Any]) -> dict[str, Any]:
  if not isinstance(proposed, dict):
    return {"ok": False, "error": "proposed must be an object"}
  diff: dict[str, Any] = {}
  for key, new_val in proposed.items():
    try:
      old = params.get(key)
      if isinstance(old, bytes):
        old = old.decode(errors="replace")
    except Exception:
      old = None
    if str(old) != str(new_val):
      diff[key] = {"before": old, "after": new_val}
  return {"ok": True, "changes": diff, "change_count": len(diff)}


def _latest_route_name(limit: int = 20) -> str | None:
  if not os.path.isdir(_ROUTES_DIR):
    return None
  entries: list[tuple[float, str]] = []
  try:
    for name in os.listdir(_ROUTES_DIR):
      path = os.path.join(_ROUTES_DIR, name)
      if os.path.isdir(path):
        try:
          entries.append((os.path.getmtime(path), name))
        except OSError:
          continue
  except OSError:
    return None
  entries.sort(reverse=True)
  return entries[0][1] if entries else None


def _secoc_hints_from_params(params: Params) -> dict[str, Any]:
  hints: dict[str, Any] = {"secoc_key_configured": False, "notes": []}
  try:
    raw = params.get("SecOCKey")
    if raw:
      text = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw)
      hints["secoc_key_configured"] = len(text.strip()) >= 32
  except Exception:
    pass
  for key in ("CarParams", "CarParamsCache"):
    try:
      raw = params.get(key)
      if not raw:
        continue
      from cereal import car
      with car.CarParams.from_bytes(raw) as cp:
        if getattr(cp, "secOcRequired", False):
          hints["secOcRequired"] = True
          hints["secOcKeyAvailable"] = bool(getattr(cp, "secOcKeyAvailable", False))
          hints["carFingerprint"] = cp.carFingerprint
          hints["brand"] = cp.brand
          break
    except Exception:
      continue
  if hints.get("secOcRequired") and not hints.get("secOcKeyAvailable"):
    hints["notes"].append(
      "SecOC 车但未检测到可用密钥：查 startupNoSecOcKey，参考 optskug/docs 与 secoc-toyota 技能。"
    )
  return hints


def _event_triage(events: list[dict[str, Any]]) -> list[dict[str, str]]:
  mapping = {
    "startupNoSecOcKey": "SecOC：op 助手 → 设置 → SecOC，或 tsk_extract_key / tsk_run_pipeline",
    "carUnrecognized": "指纹未识别：先排除 SecOC，再考虑 DBC/指纹适配",
    "startupNoCar": "车型不在支持表：查 CARS.md 与 SecOC 列表",
    "startupNoControl": "无控制权限：查 dashcam 与支持级别",
    "dashcamMode": "行车记录仪模式：确认是否预期",
    "steerUnavailable": "转向不可用：SecOC / EPS 锁止 / LKAS 设置",
    "steerTempUnavailable": "转向暂时不可用：扭矩或锁止，查品牌技能",
    "invalidLkasSetting": "车内 LKAS 未开启或设置无效",
  }
  out: list[dict[str, str]] = []
  seen: set[str] = set()
  for evt in events:
    name = str(evt.get("name", ""))
    if not name or name in seen:
      continue
    seen.add(name)
    if name in mapping:
      out.append({"event": name, "action": mapping[name]})
    elif evt.get("no_entry") or evt.get("immediate_disable") or evt.get("permanent"):
      out.append({"event": name, "action": "优先排查：grep_log + read_manager_log"})
  return out[:12]


def trip_review(
  params: Params,
  get_state_reader,
  *,
  brand: str = "",
  route_name: str = "",
) -> dict[str, Any]:
  """Structured post-drive / engage-failure review (read-only)."""
  events_res = read_onroad_events(get_state_reader)
  events = events_res.get("events") or []
  tune = snapshot_tune_state(params, brand=brand)
  secoc = _secoc_hints_from_params(params)
  triage = _event_triage(events)

  route = (route_name or "").strip() or (_latest_route_name() or "")
  route_info: dict[str, Any] = {}
  if route:
    route_info = analyze_route_summary(route)

  log_hints = grep_log(params, "error|fault|secoc|unrecognized|steer", lines=120)
  matches = log_hints.get("matches") or []

  recommendations: list[str] = []
  event_names = {str(e.get("name", "")) for e in events}
  if "startupNoSecOcKey" in event_names:
    recommendations.append("安装 SecOC 密钥：op 助手 → 设置 → SecOC，或 tsk_run_pipeline(confirm=true)")
  if "carUnrecognized" in event_names:
    recommendations.append("收集 CAN 指纹或确认 SecOC 档位后再适配")
  if "steerUnavailable" in event_names or "steerTempUnavailable" in event_names:
    if brand in ("volkswagen", "audi", "skoda", "seat"):
      recommendations.append("VAG：尝试 dp_vag_avoid_eps_lockout，降低低速横向增益")
    else:
      recommendations.append("查 LKAS 开关与品牌锁止说明（vehicle-adaptation 指南）")
  if not recommendations and not events:
    recommendations.append("当前无 critical events；可对比 snapshot_tune_state 做舒适/运动调优")
  if tune.get("param_count", 0) > 0 and not recommendations:
    recommendations.append("调优项已快照，可向用户建议 1–3 项 dp_* 微调（静止时 diff_params 预览）")

  tune_suggestions = suggest_tune_from_review(events, tune, brand=brand or secoc.get("brand", ""))

  engage_rate = None
  if route:
    try:
      from ai.tools.route_scoring_tools import score_route_tune
      scored = score_route_tune(route)
      if scored.get("ok"):
        engage_rate = (scored.get("metrics") or {}).get("engage_ratio")
    except Exception:
      pass

  return {
    "ok": True,
    "route_name": route or None,
    "engage_rate": engage_rate,
    "vehicle": {
      "vEgo": events_res.get("vEgo"),
      "enabled": events_res.get("enabled"),
      "brand": brand or secoc.get("brand", ""),
      "fingerprint": secoc.get("carFingerprint", ""),
    },
    "secoc": secoc,
    "events": events,
    "event_triage": triage,
    "tune_snapshot_count": tune.get("param_count", 0),
    "tune_highlights": {
      k: v for k, v in (tune.get("params") or {}).items()
      if k in ("dp_lat_alka", "dp_vag_avoid_eps_lockout", "LongitudinalPersonality", "dp_dev_model_selected")
    },
    "route": route_info if route_info.get("ok") else {"ok": False, "route": route or None},
    "recent_log_matches": matches[:8],
    "recommendations": recommendations[:6],
    "tune_suggestions": tune_suggestions,
    "hint": "静止时可 write_params 应用建议；SecOCKey 须通过 TSK 工具或 /?settings=secoc 安装。",
  }


def suggest_tune_from_review(
  events: list[dict[str, Any]],
  tune_snap: dict[str, Any],
  *,
  brand: str = "",
) -> list[dict[str, Any]]:
  """Rule-based tune suggestions from events + current params."""
  params = tune_snap.get("params") or {}
  suggestions: list[dict[str, Any]] = []
  event_names = {str(e.get("name", "")) for e in events}

  if "steerTempUnavailable" in event_names or "steerUnavailable" in event_names:
    if brand in ("volkswagen", "audi", "skoda", "seat") and str(params.get("dp_vag_avoid_eps_lockout", "0")) != "1":
      suggestions.append({
        "reason": "转向暂时不可用 + VAG",
        "preset_id": "vag_eps_safe",
        "params": {"dp_vag_avoid_eps_lockout": "1"},
      })
    if str(params.get("dp_lat_alka", "0")) == "1":
      suggestions.append({
        "reason": "转向事件 + ALKA 开启",
        "action": "考虑暂时关闭 dp_lat_alka 排查",
        "params": {"dp_lat_alka": "0"},
      })

  personality = str(params.get("LongitudinalPersonality", "1"))
  if personality == "0":
    suggestions.append({
      "reason": "纵向人格为激进",
      "preset_id": "comfort_follow",
      "params": {"dp_lon_acm": "1", "LongitudinalPersonality": "2"},
    })

  if not suggestions and not event_names:
    if str(params.get("dp_lon_acm", "0")) != "1":
      suggestions.append({
        "reason": "无异常事件，可尝试舒适跟车",
        "preset_id": "comfort_follow",
      })

  return suggestions[:5]


def suggest_tune_from_route(
  params: Params,
  route_name: str = "",
  *,
  brand: str = "",
) -> dict[str, Any]:
  """Correlate route metadata with tune suggestions (read-only)."""
  route = (route_name or "").strip() or (_latest_route_name() or "")
  summary = analyze_route_summary(route) if route else {"ok": False}
  tune = snapshot_tune_state(params, brand=brand)
  suggestions = suggest_tune_from_review([], tune, brand=brand)

  return {
    "ok": True,
    "route": summary,
    "tune_snapshot_count": tune.get("param_count", 0),
    "tune_suggestions": suggestions,
    "hint": "Apply presets while stationary; save_tune_snapshot before writes.",
  }


def apply_tune_from_route(
  params,
  route_name: str = "",
  *,
  brand: str = "",
  confirm: bool = False,
  max_params: int = 5,
  route_before: str = "",
  route_after: str = "",
  skip_regression_check: bool = False,
  admin: bool = True,
) -> dict[str, Any]:
  """Analyze route, merge tune suggestions, optionally apply params (with auto snapshot)."""
  from ai.tools.params_policy import validate_write_batch

  review = suggest_tune_from_route(params, route_name, brand=brand)
  if not review.get("ok"):
    return review

  merged: dict[str, Any] = {}
  applied_preset: str | None = None
  for item in review.get("tune_suggestions") or []:
    if item.get("preset_id") and not item.get("params"):
      from ai.tools.presets import get_preset
      preset = get_preset(str(item["preset_id"]))
      if preset:
        merged.update(preset.get("params") or {})
        applied_preset = str(item["preset_id"])
    for k, v in (item.get("params") or {}).items():
      merged[k] = v

  if not merged:
    return {
      "ok": True,
      "applied": False,
      "reason": "No param changes suggested for this route",
      "review": review,
    }

  if len(merged) > max_params:
    keys = list(merged.keys())[:max_params]
    merged = {k: merged[k] for k in keys}

  preview = diff_params(params, merged)
  if not confirm:
    return {
      "ok": True,
      "needs_confirmation": True,
      "preview": preview.get("changes", {}),
      "params": merged,
      "preset": applied_preset,
      "review": review,
      "hint": "Call again with confirm=true to apply.",
    }

  ok, reason = validate_write_batch(merged, admin=admin)
  if not ok:
    return {"ok": False, "error": reason, "preview": preview}

  route = (route_name or "").strip() or (_latest_route_name() or "")
  ra = (route_after or "").strip() or route
  rb = (route_before or "").strip()

  from ai.tools.tune_write_pipeline import apply_param_writes
  out = apply_param_writes(
    params,
    merged,
    action="apply_tune_from_route",
    brand=brand,
    route_before=rb,
    route_after=ra,
    skip_regression_check=skip_regression_check,
    snapshot_label="auto_before_route_tune",
    preset_id=applied_preset,
    admin=admin,
  )
  if out.get("ok"):
    out["preset"] = applied_preset
    out["review"] = review
    out["route"] = review.get("route")
    out["change_count"] = len(out.get("applied") or {})
  return out


def _load_log_reader():
  try:
    from openpilot.tools.lib.logreader import LogReader
    return LogReader
  except Exception:
    try:
      from tools.lib.logreader import LogReader  # type: ignore
      return LogReader
    except Exception:
      return None


def _rel_log_time(msg, origin_mono: int | None) -> tuple[float, int]:
  mono = int(msg.logMonoTime)
  if origin_mono is None:
    return 0.0, mono
  return (mono - origin_mono) / 1e9, mono


def _sample_car_state(msg, t_rel: float) -> dict[str, Any]:
  cs = msg.carState
  return {
    "t": round(t_rel, 3),
    "vEgo": round(float(cs.vEgo), 3),
    "steeringAngleDeg": round(float(cs.steeringAngleDeg), 2),
    "gas": round(float(cs.gas), 3),
    "brake": round(float(cs.brake), 3),
    "standstill": bool(cs.standstill),
  }


def _sample_controls_state(msg, t_rel: float) -> dict[str, Any]:
  st = msg.controlsState
  return {
    "t": round(t_rel, 3),
    "enabled": bool(st.enabled),
    "active": bool(st.active),
    "state": str(st.state),
  }


def _sample_selfdrive_state(msg, t_rel: float) -> dict[str, Any]:
  sd = msg.selfdriveState
  return {
    "t": round(t_rel, 3),
    "enabled": bool(sd.enabled),
    "active": bool(sd.active),
    "state": str(sd.state),
  }


def _sample_onroad_events(msg, t_rel: float) -> dict[str, Any]:
  events = []
  for ev in msg.onroadEvents:
    name = str(ev.name) if hasattr(ev, "name") else str(ev)
    events.append(name)
  if not events:
    return {}
  return {"t": round(t_rel, 3), "events": events[:12]}


def read_qlog_segment(
  route_name: str,
  *,
  start_sec: float = 0.0,
  end_sec: float = 120.0,
  topics: list[str] | None = None,
  max_messages: int = 400,
) -> dict[str, Any]:
  """Read a time window from route qlog/rlog for AI analysis (read-only)."""
  if not route_name or ".." in route_name or "/" in route_name or "\\" in route_name:
    return {"ok": False, "error": "Invalid route name"}

  start_sec = max(0.0, float(start_sec))
  end_sec = max(start_sec, float(end_sec))
  max_messages = max(20, min(int(max_messages), 2000))
  wanted = {t.strip() for t in (topics or ["can", "carState", "controlsState", "selfdriveState"])}
  if not wanted:
    wanted = {"can"}

  from ai.cabana import _find_qlogs, _find_rlogs, _get_routes_dir, _pick_can_log_paths

  routes_dir = _get_routes_dir()
  if routes_dir is None:
    return {"ok": False, "error": "Routes directory not found"}

  route_path = routes_dir / route_name
  if not route_path.is_dir():
    return {"ok": False, "error": f"Route not found: {route_name}"}

  qlogs = _find_qlogs(route_path)
  rlogs = _find_rlogs(route_path)
  log_paths, source = _pick_can_log_paths(qlogs, rlogs)
  if not log_paths:
    return {"ok": False, "error": "No qlog/rlog in route"}

  LogReader = _load_log_reader()
  if LogReader is None:
    return {"ok": False, "error": "LogReader unavailable"}

  origin_mono: int | None = None
  duration_scanned = 0.0
  can_frames: list[dict[str, Any]] = []
  car_state: list[dict[str, Any]] = []
  controls_state: list[dict[str, Any]] = []
  selfdrive_state: list[dict[str, Any]] = []
  onroad_events: list[dict[str, Any]] = []
  unique_can_addrs: set[int] = set()
  total = 0

  def cap() -> bool:
    return total >= max_messages

  for log_path in log_paths:
    try:
      lr = LogReader(str(log_path))
    except Exception as e:
      return {"ok": False, "error": f"Failed to open log {log_path.name}: {e}"}
    for msg in lr:
      if origin_mono is None:
        origin_mono = int(msg.logMonoTime)
      which = msg.which()
      if which not in wanted:
        continue
      t_rel, _ = _rel_log_time(msg, origin_mono)
      duration_scanned = max(duration_scanned, t_rel)
      if t_rel < start_sec:
        continue
      if t_rel > end_sec:
        if duration_scanned > end_sec + 2.0:
          break
        continue
      if which == "can":
        for cf in msg.can:
          if cap():
            break
          addr = int(cf.address)
          unique_can_addrs.add(addr)
          can_frames.append({
            "t": round(t_rel, 3),
            "address": addr,
            "bus": int(cf.src),
            "hex": cf.dat.hex(),
          })
          total += 1
      elif which == "carState":
        car_state.append(_sample_car_state(msg, t_rel))
        total += 1
      elif which == "controlsState":
        controls_state.append(_sample_controls_state(msg, t_rel))
        total += 1
      elif which == "selfdriveState":
        selfdrive_state.append(_sample_selfdrive_state(msg, t_rel))
        total += 1
      elif which == "onroadEvents":
        sample = _sample_onroad_events(msg, t_rel)
        if sample:
          onroad_events.append(sample)
          total += 1
      if cap():
        break
    if cap() or duration_scanned > end_sec + 2.0:
      break

  return {
    "ok": True,
    "route": route_name,
    "log_source": source,
    "start_sec": start_sec,
    "end_sec": end_sec,
    "duration_scanned": round(duration_scanned, 2),
    "messages_returned": total,
    "unique_can_addresses": len(unique_can_addrs),
    "can_frames": can_frames[:max_messages],
    "car_state": car_state,
    "controls_state": controls_state,
    "selfdrive_state": selfdrive_state,
    "onroad_events": onroad_events,
    "hint": "Pair with cabana_explain_signal / extract_can_ids_from_route / trip_review.",
  }


def analyze_route_summary(route_name: str) -> dict[str, Any]:
  if not route_name or ".." in route_name or "/" in route_name or "\\" in route_name:
    return {"ok": False, "error": "Invalid route name"}
  base = os.path.join(_ROUTES_DIR, route_name)
  if not os.path.isdir(base):
    return {"ok": False, "error": f"Route not found: {route_name}"}
  try:
    mtime = os.path.getmtime(base)
  except OSError:
    mtime = 0
  files: list[str] = []
  segment_dirs: list[str] = []
  total_bytes = 0
  for root, dirs, names in os.walk(base):
    rel_root = os.path.relpath(root, base)
    if rel_root != "." and rel_root.isdigit():
      segment_dirs.append(rel_root)
    for n in names:
      fp = os.path.join(root, n)
      files.append(fp)
      try:
        total_bytes += os.path.getsize(fp)
      except OSError:
        pass
  segment_dirs = sorted(set(segment_dirs), key=lambda x: int(x) if x.isdigit() else 0)
  fcamera = any("fcamera" in f.lower() for f in files)
  has_qlog = False
  has_rlog = False
  date_label = ""
  qlog_count = 0
  rlog_count = 0
  qlog_paths: list[str] = []
  rlog_paths: list[str] = []
  try:
    from pathlib import Path

    from ai.cabana import _find_qlogs, _find_rlogs, _route_date_label

    route_path = Path(base)
    qlogs = _find_qlogs(route_path)
    rlogs = _find_rlogs(route_path)
    has_qlog = bool(qlogs)
    has_rlog = bool(rlogs)
    qlog_count = len(qlogs)
    rlog_count = len(rlogs)
    qlog_paths = [p.name for p in qlogs[:8]]
    rlog_paths = [p.name for p in rlogs[:8]]
    date_label = _route_date_label(route_path)
  except Exception:
    has_qlog = any("qlog" in f.lower() for f in files)
    has_rlog = any("rlog" in f.lower() for f in files)
  return {
    "ok": True,
    "route": route_name,
    "date": date_label,
    "mtime": mtime,
    "file_count": len(files),
    "segment_dirs": segment_dirs[:30],
    "segment_count": len(segment_dirs),
    "total_size_mb": round(total_bytes / (1024 * 1024), 2),
    "has_fcamera": fcamera,
    "has_qlog": has_qlog,
    "has_rlog": has_rlog,
    "qlog_segments": qlog_count,
    "rlog_segments": rlog_count,
    "qlog_files_preview": qlog_paths,
    "rlog_files_preview": rlog_paths,
    "hint": "route_time_series / read_qlog_segment / route_video_info / Cabana UI.",
  }
