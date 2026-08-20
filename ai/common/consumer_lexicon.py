"""Plain-language labels for openpilot params — OP Agent consumer layer."""

from __future__ import annotations

from typing import Any

# Key overrides: technical param → {label, hint, unit?, value_map?}
_PARAM_LEXICON: dict[str, dict[str, Any]] = {
  "FollowDistanceGap": {"label": "跟车距离档位", "hint": "数值越大跟得越远，通常 1–4"},
  "FollowDistance": {"label": "跟车时间间隔", "hint": "秒，越大越保守"},
  "LongitudinalPersonality": {"label": "纵向驾驶风格", "hint": "跟车加减速性格", "value_map": {"0": "标准", "1": "保守", "2": "激进"}},
  "LateralPersonality": {"label": "横向驾驶风格", "hint": "变道与方向感", "value_map": {"0": "标准", "1": "柔和", "2": "灵敏"}},
  "LaneChangeSpeed": {"label": "变道速度", "hint": "变道快慢"},
  "LaneChangeBsd": {"label": "变道盲区提示", "hint": "开启后变道更谨慎"},
  "Mads": {"label": "MADS 辅助驾驶", "hint": "主开关式辅助模式"},
  "MadsSteeringMode": {"label": "方向盘接管模式", "hint": "MADS 下如何握方向盘"},
  "ExperimentalMode": {"label": "实验模式", "hint": "部分高级功能总开关"},
  "openpilotLongitudinalControl": {"label": "纵向控制", "hint": "是否由 openpilot 控制加减速"},
  "AlwaysOnDM": {"label": "驾驶员监测常开", "hint": "DM 摄像头监测"},
  "RecordFront": {"label": "录制前路视频", "hint": "路线是否含前路画面"},
  "RecordAudio": {"label": "录制车内音频", "hint": "隐私相关"},
  "QuietMode": {"label": "静音模式", "hint": "减少提示音"},
  "SpeedLimitOffset": {"label": "限速偏移", "hint": "相对识别限速的偏移 km/h"},
  "CustomAccIncrementsEnabled": {"label": "自定义巡航加减速步长", "hint": ""},
  "TorqueParamsOverrideEnabled": {"label": "扭矩参数覆盖", "hint": "高级横向扭矩调优"},
  "LiveTorqueParamsToggle": {"label": "实时扭矩学习", "hint": "路上自动微调横向"},
  "NeuralNetworkLateralControl": {"label": "神经网络横向", "hint": "NNLC 横向控制"},
  "BlindSpot": {"label": "盲区监测显示", "hint": ""},
  "LeadDepartAlert": {"label": "前车起步提醒", "hint": ""},
  "GreenLightAlert": {"label": "绿灯起步提醒", "hint": ""},
  "StandstillTimer": {"label": "停车等待计时", "hint": ""},
  "OffroadMode": {"label": "离路模式", "hint": "停车调试，禁止上路辅助"},
  "IsMetric": {"label": "公制单位", "hint": "km/h 与摄氏度"},
  "LanguageSetting": {"label": "界面语言", "hint": ""},
  "dp_lon_accel": {"label": "纵向加速度手感", "hint": "加速/减速强弱"},
  "dp_lon_jerk": {"label": "纵向加加速度", "hint": "加减速变化是否突兀"},
  "dp_lon_follow_gap": {"label": "跟车间距", "hint": "跟车距离偏好"},
  "dp_lat_steer": {"label": "方向盘灵敏度", "hint": "转向响应"},
  "dp_lat_lane": {"label": "车道保持力度", "hint": "压线回正强弱"},
  "dp_lc_speed": {"label": "变道快慢", "hint": "自动变道速度"},
  "dp_lc_delay": {"label": "变道等待", "hint": "打灯后多久变道"},
  "dp_alc_enabled": {"label": "自动变道", "hint": "是否允许 ALC"},
  "dp_speed_offset": {"label": "巡航速度偏移", "hint": "相对设定速度的偏移"},
}

# Natural language phrases → param keys (for NL tune hints)
_PHRASE_TO_PARAMS: dict[str, list[str]] = {
  "跟车": ["FollowDistanceGap", "FollowDistance", "dp_lon_follow_gap"],
  "跟车距离": ["FollowDistanceGap", "FollowDistance", "dp_lon_follow_gap"],
  "变道": ["LaneChangeSpeed", "dp_lc_speed", "dp_lc_delay", "dp_alc_enabled"],
  "画龙": ["dp_lat_steer", "dp_lat_lane", "TorqueParamsOverrideEnabled", "LiveTorqueParamsToggle"],
  "横向": ["dp_lat_steer", "dp_lat_lane", "LateralPersonality"],
  "纵向": ["dp_lon_accel", "dp_lon_jerk", "LongitudinalPersonality"],
  "加速": ["dp_lon_accel", "dp_lon_jerk"],
  "刹车": ["dp_lon_accel", "dp_lon_jerk"],
  "限速": ["SpeedLimitOffset", "dp_speed_offset"],
  "巡航": ["dp_speed_offset", "CustomAccIncrementsEnabled"],
}


def _catalog_title(key: str) -> str | None:
  try:
    from ai.tools.catalog_builder import build_merged_catalog
    entry = build_merged_catalog().get(key) or {}
    return entry.get("title") or entry.get("summary")
  except Exception:
    return None


def param_label(key: str) -> str:
  lex = _PARAM_LEXICON.get(key)
  if lex and lex.get("label"):
    return str(lex["label"])
  title = _catalog_title(key)
  if title:
    return str(title)
  return key


def param_hint(key: str) -> str:
  lex = _PARAM_LEXICON.get(key)
  if lex and lex.get("hint"):
    return str(lex["hint"])
  return ""


def format_param_value(key: str, value: Any) -> str:
  if value is None:
    return "（未设置）"
  text = str(value)
  lex = _PARAM_LEXICON.get(key) or {}
  value_map = lex.get("value_map") or {}
  if text in value_map:
    return f"{value_map[text]}（{text}）"
  if isinstance(value, bool) or text.lower() in ("true", "false"):
    return "开启" if str(value).lower() in ("true", "1", "yes") else "关闭"
  unit = lex.get("unit")
  if unit:
    return f"{text} {unit}"
  return text


def consumerize_diff(changes: dict[str, Any]) -> list[dict[str, Any]]:
  """Turn diff_params changes dict into consumer-friendly rows."""
  rows: list[dict[str, Any]] = []
  for key, delta in (changes or {}).items():
    if not isinstance(delta, dict):
      continue
    before = delta.get("before")
    after = delta.get("after")
    rows.append({
      "key": key,
      "label": param_label(key),
      "hint": param_hint(key),
      "before": format_param_value(key, before),
      "after": format_param_value(key, after),
      "before_raw": before,
      "after_raw": after,
    })
  return rows


def preview_param_writes(proposed: dict[str, Any], *, changes: dict[str, Any] | None = None) -> dict[str, Any]:
  """Build consumer preview from proposed writes or precomputed diff changes."""
  if changes is None:
    from openpilot.common.params import Params

    from ai.tools.diagnostics_tools import diff_params

    params = Params()
    diff = diff_params(params, proposed)
    if not diff.get("ok"):
      return diff
    changes = diff.get("changes") or {}
  rows = consumerize_diff(changes)
  return {
    "ok": True,
    "change_count": len(rows),
    "rows": rows,
    "summary": _summarize_rows(rows),
  }


def _summarize_rows(rows: list[dict[str, Any]]) -> str:
  if not rows:
    return "没有检测到参数变化。"
  parts = [f"「{r['label']}」：{r['before']} → {r['after']}" for r in rows[:6]]
  if len(rows) > 6:
    parts.append(f"等共 {len(rows)} 项")
  return "；".join(parts)


def lexicon_snapshot(*, limit: int = 80) -> dict[str, Any]:
  items = []
  for key, meta in list(_PARAM_LEXICON.items())[:limit]:
    items.append({"key": key, "label": meta.get("label", key), "hint": meta.get("hint", "")})
  return {"ok": True, "count": len(_PARAM_LEXICON), "items": items, "phrase_map": _PHRASE_TO_PARAMS}


def filter_consumer_language(text: str) -> str:
  """Strip overly technical tokens for owner-facing skill summaries."""
  import re
  if not text:
    return text
  replacements = [
    (r"\bParams\b", "设置"),
    (r"\bdp_[a-z0-9_]+\b", "驾驶参数"),
    (r"\bwrite_params\b", "改设置"),
    (r"\bdiff_params\b", "对比设置"),
    (r"\bconfirm=true\b", "经您确认"),
    (r"\btool_call\b", "操作"),
  ]
  out = text
  for pat, repl in replacements:
    out = re.sub(pat, repl, out, flags=re.IGNORECASE)
  return out
