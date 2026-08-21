"""One-shot openpilot health / engage readiness checks."""

from __future__ import annotations

from typing import Any, Literal

Status = Literal["ok", "warn", "fail", "skip"]


def _item(
  name: str,
  status: Status,
  summary: str,
  *,
  details: dict[str, Any] | None = None,
  action: str | None = None,
) -> dict[str, Any]:
  return {
    "name": name,
    "status": status,
    "summary": summary,
    "details": details or {},
    "action": action,
  }


def _overall(checks: list[dict[str, Any]]) -> Status:
  if any(c["status"] == "fail" for c in checks):
    return "fail"
  if any(c["status"] == "warn" for c in checks):
    return "warn"
  return "ok"


def run_health_check(*, scope: str = "engage", get_state_reader=None) -> dict[str, Any]:
  """
  Read-only composite health check for openpilot.

  scope:
    - engage: focus on why OP may not engage
    - system: disk/thermal/panda/network
    - full: both
  """
  scope = (scope or "engage").strip().lower()
  checks: list[dict[str, Any]] = []

  reader = None
  state = None
  vehicle: dict[str, Any] = {}
  try:
    if get_state_reader is None:
      from ai.system.state_reader import get_state_reader as _gsr
      get_state_reader = _gsr
    reader = get_state_reader()
    state = reader.update(timeout=0)
    snap = reader.latest()
    vehicle = snap.get("vehicle", {}) if isinstance(snap, dict) else {}
    if not vehicle and hasattr(state, "to_dict"):
      vehicle = state.to_dict()
  except Exception as e:
    checks.append(_item("vehicle_state", "warn", f"无法读取车辆状态: {e}", action="确认 manager 已启动"))

  brand = (vehicle.get("brand") or vehicle.get("carBrand") or "").lower() if vehicle else ""

  if scope in ("engage", "full") and vehicle:
    enabled = bool(vehicle.get("enabled"))
    started = bool(vehicle.get("started"))
    v_ego = float(vehicle.get("vEgo") or 0)
    alerts = vehicle.get("alerts") or []
    events = vehicle.get("events") or vehicle.get("onroadEvents") or []
    if enabled:
      checks.append(_item("engage", "ok", "openpilot 已接合 (enabled)"))
    elif started and v_ego > 0.5:
      checks.append(_item("engage", "warn", f"车辆行驶中但未接合 (vEgo≈{v_ego:.1f} m/s)", action="查看 onroad 事件与告警"))
    else:
      checks.append(_item("engage", "ok", "车辆未接合（停车或未启动）— 可继续排查预置条件"))

    critical_events = []
    for ev in events if isinstance(events, list) else []:
      name = ev if isinstance(ev, str) else (ev.get("name") or ev.get("event") or "")
      if not name:
        continue
      low = str(name).lower()
      if any(k in low for k in ("secoc", "fingerprint", "unrecognized", "dashcam", "lkas", "steer", "camera", "panda", "controls")):
        critical_events.append(str(name))
    if critical_events:
      checks.append(_item(
        "onroad_events",
        "fail" if any("secoc" in e.lower() or "unrecognized" in e.lower() for e in critical_events) else "warn",
        f"发现 {len(critical_events)} 条可能影响接合的事件",
        details={"events": critical_events[:12]},
        action="按 engage-troubleshooting 技能逐项处理",
      ))
    elif events:
      checks.append(_item("onroad_events", "ok", f"onroad 事件 {len(events)} 条，无常见阻塞项"))
    else:
      checks.append(_item("onroad_events", "ok", "当前无 onroad 事件"))

    if alerts:
      checks.append(_item("alerts", "warn", f"活动告警 {len(alerts)} 条", details={"alerts": alerts[:8]}))
    else:
      checks.append(_item("alerts", "ok", "无活动告警"))

    brand = (vehicle.get("brand") or vehicle.get("carBrand") or "").lower()

    if brand in ("toyota", "lexus"):
      try:
        from ai.tools.domains.secoc.secoc_lookup import lookup_secoc_tier
        tier = lookup_secoc_tier(brand=brand)
        tier_name = (tier or {}).get("tier") or (tier or {}).get("label") or "unknown"
        if str(tier_name).lower() in ("red", "block", "secoc_required", "tsks"):
          checks.append(_item("secoc", "fail", "丰田/雷克萨斯可能需 SecOC 密钥", details=tier, action="启用 secoc-toyota 技能"))
        else:
          checks.append(_item("secoc", "ok", f"SecOC 分级: {tier_name}", details=tier))
      except Exception as e:
        checks.append(_item("secoc", "skip", f"SecOC 分级跳过: {e}"))

  if scope in ("system", "full", "engage"):
    try:
      from ai.tools.domains.platform.device_health_tools import device_health, panda_status
      dh = device_health()
      if dh.get("ok"):
        checks.append(_item("device_health", "ok", "设备健康检查通过", details={k: dh[k] for k in ("board", "Version", "AGNOSVersion", "disk") if k in dh}))
      else:
        checks.append(_item("device_health", "warn", "设备健康检查异常", details=dh))
      ps = panda_status(get_state_reader=get_state_reader)
      if ps.get("ok") and ps.get("connected"):
        checks.append(_item("panda", "ok", "Panda 已连接", details={"summary": ps.get("summary")}))
      elif ps.get("connected") is False:
        checks.append(_item("panda", "fail", "未检测到 Panda", details=ps, action="检查 USB / pandad / c3-dos-panda 技能"))
      else:
        checks.append(_item("panda", "warn", "Panda 状态不确定", details=ps))
    except Exception as e:
      checks.append(_item("device_health", "warn", f"设备/Panda 检查失败: {e}"))

  if scope in ("system", "full"):
    try:
      from ai.tools.domains.platform.network_tools import network_diagnostics
      net = network_diagnostics()
      if net.get("ok"):
        checks.append(_item("network", "ok", "网络诊断通过", details={k: net.get(k) for k in ("wifi", "internet", "comma_auth") if k in net}))
      else:
        checks.append(_item("network", "warn", "网络可能异常", details=net))
    except Exception as e:
      checks.append(_item("network", "skip", f"网络诊断跳过: {e}"))

  if scope in ("engage", "full"):
    try:
      from openpilot.common.params import Params
      p = Params()
      keys = ["IsOffroad", "IsOnroad", "CarParams", "SecOCKey", "OpenpilotEnabledToggle"]
      vals = {}
      for k in keys:
        try:
          raw = p.get(k)
          if raw is None:
            vals[k] = None
          elif isinstance(raw, bytes):
            vals[k] = raw.decode(errors="replace")[:80]
          else:
            vals[k] = str(raw)[:80]
        except Exception:
          vals[k] = None
      if vals.get("CarParams") in (None, "", b""):
        checks.append(_item("car_params", "fail", "CarParams 缺失 — 车辆未识别", action="检查指纹 / 车型平台 / SecOC"))
      else:
        checks.append(_item("car_params", "ok", "CarParams 已加载"))
      if brand in ("toyota", "lexus") and not vals.get("SecOCKey"):
        checks.append(_item("secoc_key", "warn", "未配置 SecOCKey", action="TSK 提取或手动安装密钥"))
      checks.append(_item("key_params", "ok", "关键 Param 已读取", details=vals))
    except Exception as e:
      checks.append(_item("key_params", "skip", f"Param 读取跳过: {e}"))

  ov = _overall(checks)
  fail_n = sum(1 for c in checks if c["status"] == "fail")
  warn_n = sum(1 for c in checks if c["status"] == "warn")
  if ov == "fail":
    headline = f"发现 {fail_n} 项阻塞问题，建议先处理后再尝试接合"
  elif ov == "warn":
    headline = f"有 {warn_n} 项需注意，未发现明确阻塞"
  else:
    headline = "健康检查通过，未发现常见阻塞项"

  return {
    "ok": True,
    "scope": scope,
    "overall": ov,
    "summary": headline,
    "checks": checks,
    "vehicle_snapshot": {
      "enabled": vehicle.get("enabled"),
      "started": vehicle.get("started"),
      "vEgo": vehicle.get("vEgo"),
      "brand": vehicle.get("brand") or vehicle.get("carBrand"),
    },
  }


def guide_ota_update(*, confirm: bool = False) -> dict[str, Any]:
  """Read-only OTA guide unless confirm=true for prebuilt checkout hints."""
  from ai.tools.domains.devops.branch_tools import ota_preflight_checklist
  pre = ota_preflight_checklist()
  steps = [
    "停车 offroad，电量充足，连接 WiFi",
    "运行 ota_preflight_checklist 查看磁盘/温度/Panda",
    "设置 → 软件 检查更新，或 checkout_prebuilt_branch（开发者）",
    "更新后执行 run_health_check(scope=full) 验证",
  ]
  out: dict[str, Any] = {
    "ok": True,
    "steps": steps,
    "preflight": pre,
    "note": "本工具不自动刷写 OTA；仅汇总预检与建议步骤。",
  }
  if confirm:
    out["hint"] = "若需切换 prebuilt 分支，使用 checkout_prebuilt_branch(confirm=true) 且保持 offroad"
  return out
