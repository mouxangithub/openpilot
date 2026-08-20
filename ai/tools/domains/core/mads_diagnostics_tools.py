"""MADS lateral / LKAS fault triage for op助手."""

from __future__ import annotations

import os
import re
from typing import Any, Callable

from openpilot.common.params import Params

from ai.tools.domains.vehicle.mads_tools import get_mads_settings
from ai.system.paths import openpilot_root, rel_source, source_path

# Symptom → structured playbook (matches master-c3 fixes, 2026-07).
_EVENT_SYMPTOMS: dict[str, dict[str, str]] = {
  "controlsMismatchLateral": {
    "ui": "控制不匹配：横向",
    "layer": "python+pandad",
    "summary": "selfdrived 认为 MADS 在控横向，但 Panda health 报告 controlsAllowedLateral=false",
  },
  "steerTempUnavailable": {
    "ui": "LKAS故障（临时）",
    "layer": "vehicle_eps",
    "summary": "EPS LKA_STATE 临时故障，常因 STEERING_LKA 被 Panda 拦截或报文中断",
  },
  "steerUnavailable": {
    "ui": "LKAS故障（永久）",
    "layer": "vehicle_eps",
    "summary": "EPS LKA_STATE 永久故障，需熄火重启",
  },
  "madsSteeringPaused": {
    "ui": "MADS 横向暂停",
    "layer": "mads_state",
    "summary": "MADS paused（如踩刹车 Pause 模式）",
  },
  "madsSteeringDisengaged": {
    "ui": "MADS 横向退出",
    "layer": "mads_state",
    "summary": "MADS 横向已解除",
  },
}

_FIXES: list[dict[str, Any]] = [
  {
    "id": "disable_data_sample",
    "applies_to": ["controlsMismatchLateral"],
    "title": "禁用 mads.data_sample()",
    "files": [rel_source("sunnypilot", "mads", "mads.py")],
    "flash_panda": False,
    "rebuild": "scons selfdrived",
    "verify": "grep -n data_sample " + rel_source("sunnypilot", "mads", "mads.py") + " 应看到 early return 或注释调用",
  },
  {
    "id": "pandad_mads_heartbeat",
    "applies_to": ["controlsMismatchLateral", "steerTempUnavailable", "steerUnavailable"],
    "title": "恢复 pandad process_mads_heartbeat（active/enabled + carParams）",
    "files": [
      rel_source("selfdrive", "pandad", "pandad.cc"),
    ],
    "flash_panda": False,
    "rebuild": "scons pandad",
    "verify": "process_mads_heartbeat 含 alternativeExperience 与 getActive/getEnabled",
  },
  {
    "id": "mads_h_main_latch",
    "applies_to": ["steerTempUnavailable", "steerUnavailable", "controlsMismatchLateral"],
    "title": "opendbc mads.h MAIN 电平保持（mads_acc_main_lateral_latch）",
    "files": ["opendbc_repo/opendbc/safety/sunnypilot/mads.h"],
    "flash_panda": True,
    "rebuild": "scons && python " + rel_source("selfdrive", "pandad", "pandad.py"),
    "verify": "mads.h 含 mads_acc_main_lateral_latch 与 MAIN held 注释",
  },
]


def _read_onroad_event_names(get_state_reader: Callable | None) -> list[str]:
  if get_state_reader is None:
    return []
  try:
    from ai.tools.diagnostics_tools import read_onroad_events
    res = read_onroad_events(get_state_reader)
    return [str(e.get("name", "")) for e in (res.get("events") or []) if e.get("name")]
  except Exception:
    return []


def _dev_tree_has_main_latch() -> bool | None:
  """Return True if mads.h contains latch helper (dev checkout only)."""
  try:
    path = openpilot_root() / "opendbc_repo" / "opendbc" / "safety" / "sunnypilot" / "mads.h"
    if not path.is_file():
      return None
    text = path.read_text(encoding="utf-8", errors="replace")
    return "mads_acc_main_lateral_latch" in text
  except Exception:
    return None


def _dev_tree_data_sample_disabled() -> bool | None:
  try:
    path = source_path("sunnypilot", "mads", "mads.py")
    if not path.is_file():
      return None
    text = path.read_text(encoding="utf-8", errors="replace")
    if "def data_sample(self):" not in text:
      return None
    # early return or commented call counts as disabled
    if re.search(r"def data_sample\(self\):\s*\n\s*return", text):
      return True
    if "# self.data_sample()" in text:
      return True
    if "self.data_sample()" in text and "# self.data_sample()" not in text:
      return False
    return None
  except Exception:
    return None


def _scenario_hints(mads: dict[str, Any], event_names: set[str]) -> list[str]:
  hints: list[str] = []
  if not mads.get("Mads"):
    hints.append("MADS 总开关关闭：MAIN alone 不会让 openpilot 单独控横向（除非 ACC engage）。")
  if mads.get("Mads") and not mads.get("MadsMainCruiseAllowed"):
    hints.append("MadsMainCruiseAllowed 关闭：丰田依赖 MAIN 触发 lkasEnable，建议开启。")
  mode = mads.get("MadsSteeringMode")
  if mode == 2:
    hints.append("MadsSteeringMode=Disengage：踩刹车会解除横向；pandad heartbeat 使用 mads.active。")
  elif mode == 1:
    hints.append("MadsSteeringMode=Pause：踩刹车暂停横向；松刹车可恢复。")
  if {"steerTempUnavailable", "steerUnavailable"} & event_names and mads.get("Mads"):
    hints.append("MAIN+MADS 场景：优先确认已刷含 mads_acc_main_lateral_latch 的 Panda 固件。")
  if "controlsMismatchLateral" in event_names:
    hints.append("控制不匹配：优先 data_sample 禁用 + pandad heartbeat；不必先刷固件。")
  return hints


def diagnose_mads_lateral(
  params: Params | None = None,
  get_state_reader: Callable | None = None,
  *,
  brand: str = "",
  user_scenario: str = "",
) -> dict[str, Any]:
  """
  Structured triage for MADS lateral / LKAS issues (read-only).

  Use when user reports: 控制不匹配横向, LKAS故障, MAIN+MADS, MADS+MAIN 不控车.
  """
  params = params or Params()
  mads = get_mads_settings(params)
  event_names = set(_read_onroad_event_names(get_state_reader))

  symptoms: list[dict[str, str]] = []
  for name in sorted(event_names):
    if name in _EVENT_SYMPTOMS:
      row = {"event": name, **_EVENT_SYMPTOMS[name]}
      symptoms.append(row)

  # Infer from free-text scenario if no live events
  scenario_l = (user_scenario or "").lower()
  if not symptoms and user_scenario:
    if "不匹配" in user_scenario or "mismatch" in scenario_l:
      symptoms.append({"event": "(inferred)", "ui": "控制不匹配：横向", "layer": "python+pandad", "summary": "用户描述"})
    if "lkas" in scenario_l or "转向" in user_scenario:
      symptoms.append({"event": "(inferred)", "ui": "LKAS故障", "layer": "vehicle_eps", "summary": "用户描述"})

  symptom_events = {s["event"] for s in symptoms if s["event"] != "(inferred)"}
  ranked_fixes: list[dict[str, Any]] = []
  for fix in _FIXES:
    if symptom_events and not (set(fix["applies_to"]) & symptom_events):
      continue
    ranked_fixes.append(fix)
  if not ranked_fixes:
    ranked_fixes = list(_FIXES)

  dev_latch = _dev_tree_has_main_latch()
  dev_data_sample = _dev_tree_data_sample_disabled()

  checklist: list[str] = [
    "确认设置：Mads=开，MadsMainCruiseAllowed=开（丰田），用 MAIN 而非仅 LDA",
    "确认操作：MAIN 亮 → MADS active → 未开 ACC 也应能横控（MADS 目的）",
  ]
  if dev_data_sample is False:
    checklist.insert(0, "代码：mads.py 仍调用 data_sample() — 需禁用后重编")
  elif dev_data_sample is True:
    checklist.append("代码：data_sample 已禁用 ✓")
  if dev_latch is False:
    checklist.insert(0, "代码：mads.h 缺少 mads_acc_main_lateral_latch — 需更新 opendbc 并刷 Panda")
  elif dev_latch is True:
    checklist.append("代码：mads.h MAIN latch 已合入 ✓（仍须刷 Panda 才上车生效）")

  if any(f["flash_panda"] for f in ranked_fixes[:2]):
    checklist.append("固件：改 mads.h 后必须 python " + rel_source("selfdrive", "pandad", "pandad.py") + " 刷 Panda")

  recommendations: list[str] = []
  if "controlsMismatchLateral" in event_names:
    recommendations.append("先 trip_review + 确认 data_sample 与 pandad heartbeat（无需刷 Panda）")
  if {"steerTempUnavailable", "steerUnavailable"} & event_names:
    recommendations.append("LKAS 故障：查 Panda 是否已刷含 MAIN latch 的固件；grep_log steer|LKA|mads")
  if brand in ("toyota", "lexus") or "toyota" in scenario_l:
    recommendations.append("丰田：SecOC 车先排除 startupNoSecOcKey（secoc-toyota 技能）")
  if not recommendations:
    recommendations.append("调用 read_onroad_events 获取实时事件；静止时可 trip_review")

  return {
    "ok": True,
    "brand": brand or None,
    "user_scenario": user_scenario or None,
    "mads_settings": mads,
    "onroad_events": sorted(event_names),
    "symptoms": symptoms,
    "scenario_hints": _scenario_hints(mads, event_names),
    "likely_fault_chain": (
      "MADS active (Python) but Panda blocks STEERING_LKA "
      "(controls_allowed_lateral false) → Toyota EPS LKA_STATE fault"
    ),
    "fixes_ranked": ranked_fixes,
    "dev_source_checks": {
      "mads_h_main_latch_present": dev_latch,
      "data_sample_disabled": dev_data_sample,
    },
    "checklist": checklist,
    "recommendations": recommendations[:6],
    "skill": "mads-lateral-troubleshoot",
    "knowledge_doc_id": "builtin_mads_lateral_triage",
    "hint": "行车中只读；刷固件与改代码需在 PC/offroad 完成。",
  }
