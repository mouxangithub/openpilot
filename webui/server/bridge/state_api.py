"""Lightweight UI state from cereal (mirrors ui_state.py)."""

from __future__ import annotations

import time
from typing import Any

from webui.server.bridge.ui_status import derive_engaged, derive_ui_status

NETWORK_TYPES = {
  0: "--",
  1: "Wi-Fi",
  2: "ETH",
  3: "2G",
  4: "3G",
  5: "LTE",
  6: "5G",
}


def _livestream_encoder_lagging() -> bool:
  try:
    from openpilot.common.params import Params
    return Params().get_bool("LivestreamEncoderLagging")
  except Exception:
    return False


def _cpu_temp_c(ds) -> int | None:
  if not hasattr(ds, "cpuTempC"):
    return None
  temp = ds.cpuTempC
  try:
    if hasattr(temp, "__len__") and not isinstance(temp, (str, bytes)):
      temp = temp[0] if len(temp) else None
  except TypeError:
    pass
  if temp is None:
    return None
  try:
    return round(float(temp))
  except (TypeError, ValueError):
    return None


PING_TIMEOUT_NS = 80_000_000_000


def _sunnylink_metric() -> dict[str, str]:
  try:
    from openpilot.common.params import Params
    from openpilot.sunnypilot.sunnylink.api import UNREGISTERED_SUNNYLINK_DONGLE_ID
    p = Params()
  except Exception:
    return {"status": "DISABLED", "tone": "disabled"}

  if not p.get_bool("SunnylinkEnabled"):
    return {"status": "DISABLED", "tone": "disabled"}

  last_ping = int(p.get("LastSunnylinkPingTime") or 0)
  dongle_id = p.get("SunnylinkDongleId")
  is_temp_fault = p.get_bool("SunnylinkTempFault")
  is_registering = not is_temp_fault and dongle_id in (None, "", UNREGISTERED_SUNNYLINK_DONGLE_ID)

  if last_ping:
    if time.monotonic_ns() - last_ping < PING_TIMEOUT_NS:
      return {"status": "ONLINE", "tone": "good"}
    return {"status": "ERROR", "tone": "danger"}
  if is_temp_fault:
    return {"status": "FAULT", "tone": "warn"}
  if is_registering:
    return {"status": "REGIST...", "tone": "progress"}
  return {"status": "OFFLINE", "tone": "danger"}


def _panda_state(sm) -> tuple[bool, bool]:
  """Return (panda_unknown, panda_online) matching native sidebar."""
  if not sm.valid["pandaStates"] or not sm["pandaStates"]:
    return True, False
  try:
    from openpilot.cereal import log
    panda_type = sm["pandaStates"][0].pandaType
    unknown = panda_type == log.PandaState.PandaType.unknown
    return unknown, not unknown
  except Exception:
    return True, False


def _athena_connection_status(ds) -> str:
  if not hasattr(ds, "lastAthenaPingTime"):
    return "OFFLINE"
  last_ping = int(ds.lastAthenaPingTime or 0)
  if last_ping == 0:
    return "OFFLINE"
  if time.monotonic_ns() - last_ping < 80_000_000_000:
    return "ONLINE"
  return "ERROR"


def _network_strength(ds) -> int:
  if not hasattr(ds, "networkStrength"):
    return 0
  raw = ds.networkStrength.raw if hasattr(ds.networkStrength, "raw") else int(ds.networkStrength)
  raw = int(raw)
  return max(0, min(5, raw + 1)) if raw > 0 else 0


def _derive_ui_status(sm) -> str:
  return derive_ui_status(sm)


KM_TO_MILE = 0.621371
SET_SPEED_NA = 255
_v_ego_cluster_seen = False


def _ui_params() -> dict[str, bool]:
  out = {
    "hide_v_ego_ui": False,
    "true_v_ego_ui": False,
    "road_name_toggle": False,
    "standstill_timer": False,
  }
  try:
    from openpilot.common.params import Params
    p = Params()
    out["hide_v_ego_ui"] = p.get_bool("HideVEgoUI")
    out["true_v_ego_ui"] = p.get_bool("TrueVEgoUI")
    out["road_name_toggle"] = p.get_bool("RoadNameToggle")
    out["standstill_timer"] = p.get_bool("StandstillTimer")
  except Exception:
    pass
  return out


def _estimate_alert_height(size: str, text1: str, text2: str, width: int = 1820) -> int:
  """Estimate alert banner height without pyray / gui_app (headless-safe)."""
  _ = width  # reserved for future wrap-width tuning
  pad = 40
  if size == "small":
    lines = max(1, (len(text1 or "") + 34) // 35)
    return pad * 2 + lines * 56
  if size == "mid":
    lines1 = max(1, (len(text1 or "") + 28) // 29)
    lines2 = max(0, (len(text2 or "") + 40) // 41) if text2 else 0
    h = pad * 2 + lines1 * 88
    if lines2:
      h += 15 + lines2 * 44
    return h
  if size == "full":
    return 1080
  return 0


def _cruise_speed_raw(cs, ctrl) -> float:
  """Match openpilot/selfdrive/ui/onroad/hud_renderer.py _update_state."""
  v_cruise_cluster = float(getattr(cs, "vCruiseCluster", 0.0) or 0.0)
  if v_cruise_cluster == 0.0:
    if hasattr(ctrl, "deprecated"):
      return float(getattr(ctrl.deprecated, "vCruise", 0) or 0)
    return 0.0
  return v_cruise_cluster


def build_state_from_sm(sm) -> dict[str, Any]:
  global _v_ego_cluster_seen
  from webui.server.bridge.car_context import get_car_context
  from webui.server.bridge.headless_util import is_headless_mode

  car_ctx = get_car_context()
  ds = sm["deviceState"]
  ss = sm["selfdriveState"]
  cs = sm["carState"]
  ctrl = sm["controlsState"]

  started = bool(ds.started)
  if not started:
    _v_ego_cluster_seen = False
    try:
      from webui.server.bridge.dm_snapshot import reset_dm_state
      reset_dm_state()
    except Exception:
      pass
  engaged = derive_engaged(sm, started)
  ui_params = _ui_params()
  is_metric = False
  try:
    from openpilot.common.params import Params
    is_metric = Params().get_bool("IsMetric")
  except Exception:
    pass

  v_ego_cluster = float(getattr(cs, "vEgoCluster", 0.0) or 0.0)
  if v_ego_cluster != 0.0:
    _v_ego_cluster_seen = True
  v_ego = float(cs.vEgo) if cs.vEgo == cs.vEgo else 0.0
  if _v_ego_cluster_seen and not ui_params["true_v_ego_ui"]:
    v_ego = v_ego_cluster
  speed_ms = max(0.0, v_ego)
  speed = round(speed_ms * (3.6 if is_metric else 2.23694))
  unit = "km/h" if is_metric else "mph"

  cruise_raw = _cruise_speed_raw(cs, ctrl)
  is_cruise_set = 0 < cruise_raw < SET_SPEED_NA
  is_cruise_available = cruise_raw != -1
  display_set_speed = cruise_raw
  if is_cruise_set and not is_metric:
    display_set_speed = cruise_raw * KM_TO_MILE

  speed_cluster = 0.0
  if hasattr(cs, "cruiseState"):
    speed_cluster = float(getattr(cs.cruiseState, "speedCluster", 0) or 0)
    if speed_cluster > 0:
      speed_cluster = speed_cluster * (3.6 if is_metric else 2.23694)

  car_control_enabled = False
  long_override = False
  try:
    if sm.valid.get("carControl"):
      cc = sm["carControl"]
      car_control_enabled = bool(getattr(cc, "enabled", False))
      long_override = bool(cc.cruiseControl.override)
  except Exception:
    pass

  ui_status = _derive_ui_status(sm)

  panda_unknown, panda_online = _panda_state(sm)

  net_raw = ds.networkType.raw if hasattr(ds, "networkType") else 0
  net_type = NETWORK_TYPES.get(int(net_raw), "--")
  thermal = str(ds.thermalStatus).split(".")[-1].lower() if hasattr(ds, "thermalStatus") else "ok"
  sunnylink = _sunnylink_metric()

  experimental = bool(ss.experimentalMode) if hasattr(ss, "experimentalMode") else False
  personality = str(ss.personality).split(".")[-1].lower() if hasattr(ss, "personality") else ""

  experimental_confirmed = False
  screensaver_enabled = False
  screensaver_timeout_sec = 300
  recording_audio = car_ctx.recording_audio
  developer_ui = int(car_ctx.developer_ui or 0)
  torque_bar = car_ctx.torque_bar
  speed_limit_mode = 0
  turn_signals = car_ctx.turn_signals
  blindspot = car_ctx.blindspot
  rocket_fuel_enabled = car_ctx.rocket_fuel_enabled
  try:
    from openpilot.common.params import Params
    p = Params()
    experimental_confirmed = p.get_bool("ExperimentalModeConfirmed")
    screensaver_enabled = p.get_bool("ScreenSaverEnabled")
    screensaver_timeout_sec = int(p.get("ScreenSaverTimeout", return_default=True) or 300)
    speed_limit_mode = int(p.get("SpeedLimitMode", return_default=True) or 0)
  except Exception:
    pass

  has_longitudinal = car_ctx.has_longitudinal_control
  alpha_long_available = car_ctx.alpha_long_available
  has_icbm = car_ctx.has_icbm
  icbm_available = car_ctx.icbm_available
  pcm_cruise = car_ctx.pcm_cruise
  torque_control_allowed = car_ctx.torque_control_allowed
  lateral_jerk_torque = car_ctx.lateral_jerk_torque
  mads_limited = car_ctx.mads_limited
  enable_bsm = car_ctx.enable_bsm
  sla_available = car_ctx.sla_available
  is_sp_release = car_ctx.is_sp_release
  disable_updates = car_ctx.disable_updates
  is_release_branch = car_ctx.is_release_branch
  is_development_branch = car_ctx.is_development_branch
  custom_model_active = car_ctx.custom_model_active
  live_lateral_delay = None
  steer_actuator_delay = car_ctx.steer_actuator_delay
  tesla_has_vehicle_bus = car_ctx.tesla_has_vehicle_bus
  subaru_sng_available = car_ctx.subaru_sng_available
  cp_loaded = car_ctx.cp_loaded
  standstill = bool(getattr(cs, "standstill", False))
  standstill_timer_enabled = ui_params["standstill_timer"]
  try:
    if sm.valid.get("lateralDelay"):
      live_lateral_delay = float(getattr(sm["lateralDelay"], "lateralDelay", 0) or 0)
  except Exception:
    pass

  sp_hud: dict[str, Any] = {
    "long_override": long_override,
    "cluster_speed": round(speed_cluster) if speed_cluster > 0 else None,
  }
  try:
    if sm.valid.get("selfdriveStateSP"):
      ssp = sm["selfdriveStateSP"]
      sp_hud.update({
        "speed_limit": getattr(ssp, "speedLimit", None),
        "speed_limit_assist": str(getattr(ssp, "speedLimitAssist", "")).split(".")[-1],
        "road_name": getattr(ssp, "roadName", "") or "",
        "blindspot_left": bool(getattr(ssp, "blindspotLeft", False)),
        "blindspot_right": bool(getattr(ssp, "blindspotRight", False)),
        "turn_signal_left": bool(getattr(ssp, "turnSignalLeft", False)),
        "turn_signal_right": bool(getattr(ssp, "turnSignalRight", False)),
        "rocket_fuel": getattr(ssp, "rocketFuel", None),
      })
    if sm.valid.get("longitudinalPlanSP"):
      lp_sp = sm["longitudinalPlanSP"]
      assist = getattr(lp_sp, "speedLimit", None)
      resolver = getattr(assist, "resolver", None) if assist else None
      if resolver is not None:
        conv = 3.6 if is_metric else 2.23694
        sp_hud["speed_limit_resolver"] = round(float(getattr(resolver, "speedLimit", 0) or 0) * conv)
        sp_hud["speed_limit"] = sp_hud["speed_limit_resolver"]
        sp_hud["speed_limit_last"] = round(float(getattr(resolver, "speedLimitLast", 0) or 0) * conv)
        sp_hud["speed_limit_final_last"] = round(float(getattr(resolver, "speedLimitFinalLast", 0) or 0) * conv)
        sp_hud["speed_limit_offset"] = round(float(getattr(resolver, "speedLimitOffset", 0) or 0) * conv)
        sp_hud["speed_limit_valid"] = bool(getattr(resolver, "speedLimitValid", False))
        sp_hud["speed_limit_last_valid"] = bool(getattr(resolver, "speedLimitLastValid", False))
        sp_hud["speed_limit_source"] = str(getattr(resolver, "source", "")).split(".")[-1]
        sp_hud["speed_limit_assist_state"] = str(getattr(getattr(assist, "assist", None), "state", "")).split(".")[-1]
      sp_hud["speed_limit_assist_active"] = bool(getattr(getattr(assist, "assist", None), "active", False))
      scc = getattr(lp_sp, "smartCruiseControl", None)
      if scc is not None:
        vision = getattr(scc, "vision", None)
        map_ = getattr(scc, "map", None)
        sp_hud["scc_vision_enabled"] = bool(getattr(vision, "enabled", False))
        sp_hud["scc_vision_active"] = bool(getattr(vision, "active", False))
        sp_hud["scc_map_enabled"] = bool(getattr(map_, "enabled", False))
        sp_hud["scc_map_active"] = bool(getattr(map_, "active", False))
      e2e = getattr(lp_sp, "e2eAlerts", None)
      if e2e is not None:
        sp_hud["e2e_green_light"] = bool(getattr(e2e, "greenLightAlert", False))
        sp_hud["e2e_lead_depart"] = bool(getattr(e2e, "leadDepartAlert", False))
    if not sp_hud.get("road_name") and sm.valid.get("liveMapDataSP"):
      lmd = sm["liveMapDataSP"]
      sp_hud["road_name"] = getattr(lmd, "roadName", "") or ""
    if sm.valid.get("liveMapDataSP"):
      lmd = sm["liveMapDataSP"]
      conv = 3.6 if is_metric else 2.23694
      sp_hud["speed_limit_ahead_valid"] = bool(getattr(lmd, "speedLimitAheadValid", False))
      if sp_hud["speed_limit_ahead_valid"]:
        sp_hud["speed_limit_ahead"] = round(float(getattr(lmd, "speedLimitAhead", 0) or 0) * conv)
        sp_hud["speed_limit_ahead_dist"] = float(getattr(lmd, "speedLimitAheadDistance", 0) or 0)
    try:
      if car_ctx.pcm_cruise_speed is not None:
        sp_hud["pcm_cruise_speed"] = bool(car_ctx.pcm_cruise_speed)
    except Exception:
      pass
    if sp_hud.get("speed_limit_assist_state") == "preActive":
      arrow = _speed_limit_pre_active_arrow(sm, is_metric, sp_hud, display_set_speed if is_cruise_set else 0)
      if arrow:
        sp_hud["pre_active_arrow"] = arrow
  except Exception:
    pass

  dm_arc = None
  try:
    from webui.server.bridge.dm_snapshot import snapshot_dm_arc
    dm_arc = snapshot_dm_arc(sm, engaged, int(car_ctx.started_frame or 0))
  except Exception:
    pass

  alert_resolved = None
  try:
    from webui.server.bridge.alert_resolve import resolve_onroad_alert
    alert_resolved = resolve_onroad_alert(sm, ss, started)
  except Exception:
    pass

  if alert_resolved:
    alert_size = alert_resolved["size"]
    alert_t1 = alert_resolved["text1"]
    alert_t2 = alert_resolved["text2"]
    alert_status = alert_resolved.get("status", "normal")
  else:
    alert_size = str(ss.alertSize).split(".")[-1].lower() if ss.alertSize else "none"
    alert_t1 = ss.alertText1 or ""
    alert_t2 = ss.alertText2 or ""
    alert_status = str(ss.alertStatus).split(".")[-1] if ss.alertStatus else "normal"

  alert_height = _estimate_alert_height(alert_size, alert_t1, alert_t2)
  if alert_height <= 0:
    alert_heights = {"none": 0, "small": 271, "mid": 420, "full": 1080}
    alert_height = alert_heights.get(alert_size, 271 if alert_t1 else 0)

  dev_ui = None
  circular_alert_allowed = False
  try:
    from webui.server.bridge.dev_ui_api import snapshot_dev_ui
    dev_ui = snapshot_dev_ui(sm, is_metric)
    circular_alert_allowed = (
      started
      and alert_size in ("none", "")
      and sm.valid.get("driverStateV2")
      and sm.recv_frame.get("driverStateV2", 0) > int(car_ctx.started_frame or 0)
    )
  except Exception:
    pass

  torque_utilization = 0.0
  if torque_bar:
    try:
      torque_utilization = _torque_utilization(sm, ctrl, cs)
    except Exception:
      torque_utilization = 0.0

  driver_face = _driver_face(sm)
  confidence_ball = _confidence_ball(sm, ui_status, started)

  try:
    from webui.server.bridge.startup_blockers import startup_blockers_from_sm
    gate = startup_blockers_from_sm(sm)
  except Exception:
    gate = {"blockers": [], "ignition": False, "can_start": True}

  try:
    from webui.server.bridge.alert_sound import derive_alert_sound, quiet_mode_enabled
    alert_sound = derive_alert_sound(sm, ss, started)
    quiet_mode = quiet_mode_enabled()
  except Exception:
    alert_sound = "none"
    quiet_mode = False

  return {
    "ok": True,
    "started": started,
    "engaged": engaged,
    "ui_status": ui_status,
    "is_metric": is_metric,
    "is_offroad": not started,
    "speed": round(speed) if not ui_params["hide_v_ego_ui"] else None,
    "speed_raw": speed_ms,
    "unit": unit,
    "hide_v_ego_ui": ui_params["hide_v_ego_ui"],
    "road_name_toggle": ui_params["road_name_toggle"],
    "set_speed": round(display_set_speed) if is_cruise_set else None,
    "is_cruise_set": is_cruise_set,
    "is_cruise_available": is_cruise_available,
    "car_control_enabled": car_control_enabled,
    "experimental_mode": experimental,
    "experimental_mode_confirmed": experimental_confirmed,
    "screensaver_enabled": screensaver_enabled,
    "screensaver_timeout_sec": screensaver_timeout_sec,
    "engageable": bool(getattr(ss, "engageable", False) or engaged),
    "personality": personality,
    "personality_index": _personality_index(personality),
    "has_longitudinal_control": has_longitudinal,
    "has_icbm": has_icbm,
    "icbm_available": icbm_available,
    "pcm_cruise": pcm_cruise,
    "alpha_longitudinal_available": alpha_long_available,
    "cp_loaded": cp_loaded,
    "torque_control_allowed": torque_control_allowed,
    "lateral_jerk_torque": lateral_jerk_torque,
    "mads_limited": mads_limited,
    "enable_bsm": enable_bsm,
    "sla_available": sla_available,
    "is_sp_release": is_sp_release,
    "disable_updates": disable_updates,
    "is_release_branch": is_release_branch,
    "is_development_branch": is_development_branch,
    "custom_model_active": custom_model_active,
    "live_lateral_delay": live_lateral_delay,
    "steer_actuator_delay": steer_actuator_delay,
    "tesla_has_vehicle_bus": tesla_has_vehicle_bus,
    "subaru_sng_available": subaru_sng_available,
    "standstill": standstill,
    "standstill_timer_enabled": standstill_timer_enabled,
    "alert": {
      "text1": alert_t1,
      "text2": alert_t2,
      "size": alert_size,
      "status": alert_status,
      "height_px": alert_height,
      "synthetic": bool((alert_resolved or {}).get("synthetic")),
    },
    "device": {
      "network_type": net_type,
      "network_strength": _network_strength(ds),
      "network_metered": bool(ds.networkMetered) if hasattr(ds, "networkMetered") else False,
      "thermal": thermal,
      "cpu_temp": _cpu_temp_c(ds),
      "memory_usage_percent": int(ds.memoryUsagePercent) if hasattr(ds, "memoryUsagePercent") else None,
      "gpu_usage_percent": int(ds.gpuUsagePercent) if hasattr(ds, "gpuUsagePercent") else None,
      "cpu_usage_percent": max(int(v) for v in ds.cpuUsagePercent) if hasattr(ds, "cpuUsagePercent") and len(ds.cpuUsagePercent) else None,
      "livestream_encoder_lagging": _livestream_encoder_lagging(),
      "free_space_percent": round(float(ds.freeSpacePercent)) if hasattr(ds, "freeSpacePercent") and ds.freeSpacePercent == ds.freeSpacePercent else None,
      "power_draw_w": round(float(ds.powerDrawW), 1) if hasattr(ds, "powerDrawW") and ds.powerDrawW == ds.powerDrawW else None,
      "athena_status": _athena_connection_status(ds),
      "panda_unknown": panda_unknown,
      "panda_online": panda_online,
      "sunnylink": sunnylink,
    },
    "controls": {
      "lat_active": bool(ctrl.latActive) if hasattr(ctrl, "latActive") else None,
      "long_active": bool(ctrl.longActive) if hasattr(ctrl, "longActive") else None,
    },
    "sp_hud": sp_hud,
    "dm_arc": dm_arc,
    "speed_limit_mode": speed_limit_mode,
    "turn_signals": turn_signals,
    "blindspot": blindspot,
    "rocket_fuel_enabled": rocket_fuel_enabled,
    "a_ego": float(cs.aEgo) if cs.aEgo == cs.aEgo else 0.0,
    "developer_ui": developer_ui,
    "dev_ui": dev_ui,
    "recording_audio": recording_audio,
    "torque_bar": torque_bar,
    "torque_utilization": torque_utilization,
    "circular_alert_allowed": circular_alert_allowed,
    "confidence_ball": confidence_ball,
    "driver_face": driver_face,
    "headless": is_headless_mode(),
    "startup_blockers": gate.get("blockers") or [],
    "ignition": bool(gate.get("ignition")),
    "can_start": bool(gate.get("can_start", True)),
    "alert_sound": alert_sound,
    "quiet_mode": quiet_mode,
  }


def _driver_face(sm: Any) -> dict[str, Any] | None:
  if not sm.valid.get("driverStateV2"):
    return None
  try:
    dsv2 = sm["driverStateV2"]
    is_rhd = float(getattr(dsv2, "wheelOnRightProb", 0) or 0) > 0.5
    dd = dsv2.rightDriverData if is_rhd else dsv2.leftDriverData
    face_prob = float(getattr(dd, "faceProb", 0) or 0)
    pos = getattr(dd, "facePosition", [0, 0])
    std = getattr(dd, "faceOrientationStd", [0, 0])
    face_x = float(pos[0]) if len(pos) > 0 else 0.0
    face_y = float(pos[1]) if len(pos) > 1 else 0.0
    face_std = max(
      float(std[0]) if len(std) > 0 else 0.0,
      float(std[1]) if len(std) > 1 else 0.0,
    )
    alpha = 0.7
    if face_std > 0.15:
      alpha = max(0.7 - (face_std - 0.15) * 3.5, 0.0)
    box_size = 220
    fbox_x = int(1080.0 - 1714.0 * face_x)
    fbox_y = int(-135.0 + (504.0 + abs(face_x) * 112.0) + (1205.0 - abs(face_x) * 724.0) * face_y)
    return {
      "visible": face_prob > 0.7,
      "alpha": alpha,
      "rhd": is_rhd,
      "prob": face_prob,
      "box": {
        "x": fbox_x - box_size // 2,
        "y": fbox_y - box_size // 2,
        "size": box_size,
      },
      "source_size": {"w": 1928, "h": 1208},
    }
  except Exception:
    return None


def _clamp(v: float, lo: float, hi: float) -> float:
  return max(lo, min(hi, v))


def _confidence_ball(sm: Any, ui_status: str, started: bool) -> dict[str, Any] | None:
  """Target for client FirstOrder filter (confidence_ball.py)."""
  if not started:
    return None
  target = -0.5
  try:
    if sm.valid.get("modelV2"):
      dp = sm["modelV2"].meta.disengagePredictions
      steer_probs = list(getattr(dp, "steerOverrideProbs", None) or [1.0])
      brake_probs = list(getattr(dp, "brakeDisengageProbs", None) or [1.0])
      steer = max(steer_probs) if steer_probs else 1.0
      brake = max(brake_probs) if brake_probs else 1.0
      if ui_status == "disengaged":
        target = -0.5
      elif ui_status == "lat_only":
        target = 1.0 - steer
      elif ui_status == "long_only":
        target = 1.0 - brake
      elif ui_status == "override":
        target = 0.0
      else:
        target = (1.0 - brake) * (1.0 - steer)
  except Exception:
    pass
  return {"target": round(float(target), 4), "ui_status": ui_status}


def _torque_utilization(sm: Any, ctrl: Any, cs: Any) -> float:
  try:
    lat_which = ctrl.lateralControlState.which()
    if lat_which in ("angleState", "curvatureState"):
      v_ego = float(cs.vEgo)
      actual_la = float(ctrl.curvature) * v_ego ** 2
      desired_la = float(ctrl.desiredCurvature) * v_ego ** 2
      accel_diff = desired_la - actual_la
      roll = 0.0
      if sm.valid.get("vehicleParameters"):
        roll = float(sm["vehicleParameters"].roll)
      roll_comp = roll * 9.81 * _clamp((v_ego - 5.0) / 10.0, 0.0, 1.0)
      lateral_acceleration = actual_la - roll_comp
      max_la = 3.0
      try:
        from webui.server.bridge.car_context import get_car_context
        max_la = float(get_car_context().max_lateral_accel or max_la)
      except Exception:
        pass
      if not bool(sm["carControl"].latActive):
        return 0.0
      return _clamp((lateral_acceleration + accel_diff) / max_la, -1.0, 1.0)
    if sm.valid.get("carOutput"):
      return float(-sm["carOutput"].actuatorsOutput.torque)
  except Exception:
    pass
  return 0.0


def _personality_index(name: str) -> int | None:
  mapping = {"aggressive": 0, "standard": 1, "relaxed": 2}
  return mapping.get((name or "").lower())


def _speed_limit_pre_active_arrow(sm: Any, is_metric: bool, sp_hud: dict[str, Any], set_speed: float) -> str | None:
  """Return 'up' or 'down' for pre-active assist arrow (speed_limit.py)."""
  try:
    final_last = sp_hud.get("speed_limit_final_last")
    if final_last is None:
      return None
    set_round = round(float(set_speed))
    limit_round = round(float(final_last))
    if set_round < limit_round:
      return "up"
    if set_round > limit_round:
      return "down"
  except Exception:
    pass
  return None


def snapshot_ui_state() -> dict[str, Any]:
  import os
  if os.environ.get("WEBUI_DEV_PC") == "1":
    from webui.dev.mock_runtime import snapshot_dev_ui_state
    return snapshot_dev_ui_state()

  from webui.server.bridge.state_hub import get_state
  return get_state()
