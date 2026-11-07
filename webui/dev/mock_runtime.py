"""
PC dev mocks — in-memory Params + simulated cereal state for local UI preview.

Installed by webui/dev/run_pc.py before any webui server imports.
"""

from __future__ import annotations

import enum
import json
import os
import time
import types
from typing import Any


class ParamKeyType(enum.Enum):
  STRING = enum.auto()
  BOOL = enum.auto()
  INT = enum.auto()
  FLOAT = enum.auto()
  TIME = enum.auto()
  JSON = enum.auto()
  BYTES = enum.auto()

# Mutable simulation (toggled via /api/opui/dev/simulation)
SIM: dict[str, Any] = {
  "started": False,
  "engaged": False,
  "ui_status": "disengaged",
  "speed_kmh": 72,
  "set_speed_kmh": 80,
  "is_metric": True,
  "experimental_mode": True,
  "alert_text1": "",
  "alert_text2": "",
  "alert_status": "normal",
  "network_type": "Wi-Fi",
  "network_strength": 5,
  "thermal": "ok",
  "cpu_temp": 58,
  "athena_status": "ONLINE",
  "panda_unknown": False,
  "panda_online": True,
  "sunnylink": {"status": "ONLINE", "tone": "good"},
  "road_name": "Dev Preview Rd",
  "speed_limit": 60,
  "speed_limit_mode": 1,
  "speed_limit_assist": "preActive",
  "scc_vision_enabled": True,
  "scc_vision_active": True,
  "scc_map_enabled": True,
  "scc_map_active": True,
  "blindspot_left": False,
  "blindspot_right": False,
  "turn_signal_left": False,
  "turn_signal_right": False,
  "rocket_fuel": 0.35,
  "dm_prob": 0.82,
  "dm_pose": [0.05, -0.12, 0.02],
  "alert_size": "none",
  "car_fingerprint": "TOYOTA_WILDLANDER_PHEV",
  "car_brand": "toyota",
  "paired": False,
  "experimental_mode_confirmed": True,
  "recording_audio": False,
  "developer_ui": 3,
  "carrot_nav_demo": True,
  "amap_lines_demo": True,
  "standstill": False,
  "standstill_timer_enabled": True,
  "standstill_timer": 0,
  "e2e_green_light": False,
  "e2e_lead_depart": False,
  "confidence_target": 0.72,
  "engageable": True,
  "torque_bar": True,
  "torque_utilization": 0.42,
  "road_curve": True,
  "lead_d_rel": 38.0,
  "lead_v_rel": 1.5,
  "lead_a_lead_k": -0.2,
  "lead2_d_rel": 62.0,
  "lead2_v_rel": 0.8,
  "lead2_y_rel": -3.7,
  "edge_missing_demo": False,
  "lane_shift": 0.0,
  "lane_kinds_demo": True,
  "radar_tracks_demo": True,
  "target_classes_demo": True,
  "pcm_cruise_speed": False,
  "headless": False,
  "alert_sound": "none",
  "agnos_update_required": True,
  "agnos_current_version": "11.9.9",
  "agnos_target_version": "12.0.0",
  "agnos_ready_to_reboot": False,
  "agnos_sim_rebooting": False,
  "agnos_sim_reboot_until": 0.0,
  "is_body": False,
  "carrot_road_limit": 120,
  "speed_limit_source": "map",
  "carrot_crossroad_demo": True,
  "carrot_navi_debug_demo": True,
}


def _seed_params() -> dict[str, bytes | str]:
  """Default param values for panel preview."""
  bool_on = {
    "OpenpilotEnabledToggle", "IsLdwEnabled", "AlwaysOnDM", "IsMetric",
    "Mads", "BlindSpot", "SunnylinkEnabled", "DisengageOnAccelerator",
    "RecordFront", "RecordAudio", "CarrotWebEnabled",
  }
  data: dict[str, bytes | str] = {}
  for k in bool_on:
    data[k] = b"1"
  data.update({
    "DisableDM": b"0",
    "DongleId": b"dev-preview-0000",
    "HardwareSerial": b"PC-DEV-0001",
    "LongitudinalPersonality": b"1",
    "DistractionDetectionLevel": b"1",
    "UpdaterCurrentDescription": b"sunnypilot dev-preview",
    "ExperimentalMode": b"1",
    "GitBranch": b"master-c3",
    "UpdaterTargetBranch": b"master-c3",
    "UpdaterState": b"idle",
    "UpdaterAvailableBranches": b"master-c3,devel,nightly",
    "ModelManager_ActiveBundle": b'{"name":"default"}',
    "MapdVersion": b"0.0.0-dev",
    "ApiCache_FirehoseStats": b'{"status":"idle"}',
    "LocalDriveStats": b'{"all":{"distance":1234.5,"routes":42,"minutes":890}}',
    "LastSunnylinkPingTime": b"2026-08-11T12:00:00Z",
    "LanguageSetting": b"zh-CHS",
    "MaxTimeOffroad": b"1800",
    "DeviceBootMode": b"0",
    "QuietMode": b"0",
    "OnroadUploads": b"1",
    "OffroadMode": b"0",
    "HasAcceptedTerms": b"2",
    "HasAcceptedTermsSP": b"1.0",
    "CompletedSunnylinkConsentVersion": b"1.0",
    "CompletedTrainingVersion": b"0.2.0",
    "AutoLaneChangeTimer": b"0",
    "AutoLaneChangeBsmDelay": b"0",
    "RoadEdgeLaneChangeEnabled": b"0",
  })
  return data


class UnknownKeyName(Exception):
  pass


class MockParams:
  _store: dict[str, bytes | str] = {}

  def __init__(self) -> None:
    if not MockParams._store:
      MockParams._store = _seed_params()

  def check_key(self, key: str) -> bool:
    return True

  def get_type(self, key: str):
    if key not in MockParams._store and not key.endswith("Lock"):
      if os.environ.get("WEBUI_DEV_PC") == "1":
        return ParamKeyType.STRING
      return None
    val = MockParams._store.get(key, b"0")
    if isinstance(val, bytes):
      val = val.decode(errors="replace")
    if val in ("0", "1") and key not in (
      "LongitudinalPersonality", "DistractionDetectionLevel", "ChevronInfo",
      "DevUIInfo", "SpeedLimitMode", "MadsSteeringMode", "MaxTimeOffroad",
      "DeviceBootMode", "AutoLaneChangeTimer",
    ):
      return ParamKeyType.BOOL
    try:
      int(val)
      return ParamKeyType.INT
    except (TypeError, ValueError):
      return ParamKeyType.STRING

  def get(self, key: str, block: bool = False, default=None, return_default: bool = False):
    if key not in MockParams._store:
      if return_default:
        return 0 if "Level" in key or "Personality" in key else default
      return default
    val = MockParams._store[key]
    if isinstance(val, bytes):
      try:
        return val.decode()
      except Exception:
        return val
    return val

  def get_bool(self, key: str, block: bool = False) -> bool:
    raw = self.get(key, block=block)
    if raw is None:
      return False
    if isinstance(raw, bytes):
      raw = raw.decode(errors="replace")
    return str(raw).strip().lower() in ("1", "true", "yes", "on")

  def put(self, key: str, val, block: bool = False) -> None:
    MockParams._store[key] = val if isinstance(val, (bytes, bytearray)) else str(val).encode()

  def put_bool(self, key: str, val: bool, block: bool = False) -> None:
    self.put(key, b"1" if val else b"0", block=block)

  def remove(self, key: str) -> None:
    MockParams._store.pop(key, None)

  def clear_all(self) -> None:
    MockParams._store = _seed_params()


def _mock_road_model(s: dict[str, Any]) -> dict[str, Any]:
  """Sampled modelV2-style lane geometry for the road-lite scene.

  Lateral offsets are in model frame (+right). A gentle left-hand curve is
  simulated by drifting the road toward -y with distance when road_curve is on.

  MUST stay in sync with ``state_api._road_model()`` — this is a parallel
  implementation of the same wire contract, so a field added there but not here
  silently disables the feature on the PC preview (and vice versa: the frontend
  cannot tell the difference). Same for ``snapshot_dev_ui_state``'s top level.
  """
  dists = [5.0, 15.0, 30.0, 50.0, 80.0, 120.0, 160.0]
  curve = bool(s.get("road_curve", True))
  bend = [(d * d * 0.00028) if curve else 0.0 for d in dists]
  half = 5.55
  # lateral shift of the ego lane center relative to the car (+right) —
  # simulates lane departure for the LDW demo
  shift = float(s.get("lane_shift", 0.0))

  def off(y):
    return [round(y - b + shift, 2) for b in bend]

  lines = [off(-half), off(-1.85), off(1.85), off(half)]
  # planned trajectory: follows the ego lane center, same curve
  path = off(shift)
  path_std = [0.08 + d * 0.004 for d in dists]
  # demo for solid shoulder lines: drop the road edges so the outer lane
  # lines take over as solid lines
  edges = [off(-half), off(half)]
  if s.get("edge_missing_demo"):
    edges = [None, None]

  # Carrot 7714 v2 lane-line semantics: 0 unknown · 1 solid white ·
  # 2 dashed white · 3 solid yellow · 4 double yellow · 5 botts dots · 6 edge.
  line_kinds = [0, 0, 0, 0]
  if s.get("lane_kinds_demo", True):
    line_kinds[1] = 3   # median side: solid yellow
    line_kinds[2] = 2   # lane side: dashed white
  if edges[0] is None and lines[0] is not None:
    line_kinds[0] = 6
  if edges[1] is None and lines[3] is not None:
    line_kinds[3] = 6
  solid_kinds = (1, 3, 4, 6)
  line_types = [1 if k in solid_kinds else 0 for k in line_kinds]

  leads = [
    # ego-lane lead
    {"d": 55.0, "y": 0.25, "prob": 0.85, "v": 18.0, "a": -0.2, "y_std": 0.45, "x_std": 1.20, "heading": 0.01, "i": 0},
    # front-left vehicle
    {"d": 72.0, "y": -3.60, "prob": 0.80, "v": 22.0, "a": 0.1, "y_std": 0.40, "x_std": 1.10, "heading": -0.03, "i": 1},
  ]
  if s.get("target_classes_demo", True):
    leads += [
      # long trailer → truck branch (xStd > 1.6)
      {"d": 95.0, "y": -1.50, "prob": 0.60, "v": 19.0, "a": 0.0, "y_std": 0.60, "x_std": 2.10, "heading": 0.02, "i": 2},
      # wobbly, slow, short → e-bike branch
      {"d": 26.0, "y": 4.00, "prob": 0.55, "v": 7.5, "a": 0.2, "y_std": 0.82, "x_std": 0.85, "heading": 0.06, "i": 3},
      # nearly stationary at the kerb → pedestrian branch
      {"d": 18.0, "y": 4.50, "prob": 0.50, "v": 1.1, "a": 0.0, "y_std": 0.30, "x_std": 0.35, "heading": -1.20, "i": 4},
    ]

  return {
    "dists": dists,
    "edges": edges,
    "lines": lines,
    "probs": [0.92, 0.95, 0.95, 0.9],
    "line_types": line_types,
    "line_kinds": line_kinds,
    # ego-lane centre line = midpoint of the two inner lane lines
    "lane_centers": off(0),
    "leads": leads,
    "path": path,
    "path_std": [round(v, 2) for v in path_std],
  }


def _mock_radar_tracks(s: dict[str, Any]) -> list[dict[str, Any]]:
  """Car.RadarData.points equivalent — the only source for front-left /
  front-right / flanking objects (radarState exposes leadOne/leadTwo only)."""
  return [
    {"id": 11, "d": 9.5, "y": 2.35, "v": -0.8},
    {"id": 12, "d": 14.0, "y": -2.50, "v": -0.4},
    {"id": 13, "d": 26.0, "y": 4.10, "v": -0.2},
  ]


def _mock_dev_ui(s: dict[str, Any]) -> dict[str, Any]:
  mode = int(s.get("developer_ui", 0))
  unit = "km/h" if s.get("is_metric", True) else "mph"
  accel = "m/s^2"
  return {
    "mode": mode,
    "bottom": [
      {"label": "ACC.", "value": "-0.8", "unit": accel, "color": "#ffffff"},
      {"label": "L.S.", "value": "68", "unit": unit, "color": "#ffbc00"},
      {"label": "FRIC.", "value": "0.120", "unit": "", "color": "#00ff00"},
      {"label": "L.A.F.", "value": "1.850", "unit": "", "color": "#00ff00"},
    ],
    "right": [
      {"label": "REL DIST", "value": "42", "unit": "m", "color": "#ffbc00"},
      {"label": "REL SPEED", "value": "5", "unit": unit, "color": "#ffffff"},
      {"label": "REAL STEER", "value": "2.1°", "unit": "", "color": "#00ff00"},
      {"label": "DESIRED L.A.", "value": "0.15", "unit": accel, "color": "#00ff00"},
      {"label": "ACTUAL L.A.", "value": "0.12", "unit": accel, "color": "#00ff00"},
    ],
  }


def _mock_carrot_nav(s: dict[str, Any]) -> dict[str, Any]:
  """Sample carrotManSP payload mirroring GUI CarrotNavigationPanel fields."""
  return {
    "active": 1,
    "road_limit_speed": int(s.get("carrot_road_limit", 120)),
    "spd_type": 2,
    "spd_limit": 120,
    "spd_dist": 2000,
    "spd_countdown": 45,
    "turn_info": 2,
    "dist_to_turn": 350,
    "turn_countdown": 0,
    "atc_type": "atc",
    "v_turn_speed": 40,
    "road_name": "京沪高速",
    "tbt_main_text": "京沪高速",
    "tbt_main_text_next": "G2 济南方向",
    "near_dir_name": "G2",
    "desired_speed": 100,
    "desired_source": "地图",
    "traffic_state": 1,
    "traffic_countdown": 32,
    "left_sec": 0,
    "go_pos_dist": 125000,
    "go_pos_time": 5400,
    "goal_name": "上海",
    "sdi_descr": "",
    "road_cate": 1,
    # Service area / toll gate hint (App §2.3).
    "sapa_name": "阳澄湖服务区",
    "sapa_dist": 1800,
    "sapa_type": 0,
    "sapa_cnt": 2,
    # TMC congestion (App §2.5): mixed segments so the bar shows every colour.
    "tmc_overall_status": 3,
    "tmc_total_distance": 20000,
    "tmc_residual_distance": 12500,
    "tmc_segment_count": 5,
    "tmc_segment_statuses": "[1,2,3,4,5]",
    "tmc_segment_distances": "[3000,2500,4000,1500,6000]",
    # Guided-lane arrow codes (App §2.2).
    "nav_lane_guide": "L,SL",
    "nav_lane_guide_cnt": 2,
  }


def snapshot_dev_ui_state() -> dict[str, Any]:
  from webui.server.bridge.home_api import _mock_startup_blockers

  s = SIM
  unit = "km/h" if s["is_metric"] else "mph"
  speed = s["speed_kmh"] if s["is_metric"] else round(s["speed_kmh"] * 0.621371)
  set_speed = s["set_speed_kmh"] if s["is_metric"] else round(s["set_speed_kmh"] * 0.621371)

  alert = {"text1": s["alert_text1"], "text2": s["alert_text2"], "size": s.get("alert_size", "mid"), "status": s["alert_status"]}
  sizes = {"none": 0, "small": 271, "mid": 420, "full": 1080}
  alert["height_px"] = sizes.get(alert["size"], 0) if s["alert_text1"] else 0

  return {
    "ok": True,
    "dev_pc": True,
    "headless": bool(s.get("headless")),
    "started": s["started"],
    "engaged": s["engaged"],
    "ui_status": s["ui_status"] if s["started"] else "disengaged",
    "is_metric": s["is_metric"],
    "is_offroad": not s["started"],
    "speed": speed,
    "speed_raw": speed / 3.6,
    "unit": unit,
    "set_speed": set_speed if s["started"] else None,
    "experimental_mode": s["experimental_mode"],
    "experimental_mode_confirmed": s.get("experimental_mode_confirmed", True),
    "engageable": s.get("engageable", True),
    "alert": alert,
    "device": {
      "network_type": s["network_type"],
      "network_strength": s.get("network_strength", 5),
      "thermal": s["thermal"],
      "cpu_temp": s["cpu_temp"],
      "memory_usage_percent": s.get("memory_usage_percent", 63),
      "cpu_usage_percent": s.get("cpu_usage_percent", 41),
      "athena_status": s["athena_status"],
      "panda_unknown": s.get("panda_unknown", False),
      "panda_online": s["panda_online"],
      "sunnylink": s.get("sunnylink", {"status": "ONLINE", "tone": "good"}),
    },
    "controls": {"lat_active": True, "long_active": s["engaged"]},
    "personality": "standard",
    "personality_index": 1,
    "has_longitudinal_control": True,
    "alpha_longitudinal_available": False,
    "standstill": s.get("standstill", False),
    "standstill_timer_enabled": s.get("standstill_timer_enabled", False),
    "sp_hud": {
      "speed_limit": s.get("speed_limit"),
      "speed_limit_last": s.get("speed_limit"),
      "speed_limit_final_last": s.get("speed_limit"),
      "speed_limit_valid": True,
      "speed_limit_last_valid": True,
      "speed_limit_offset": 0,
      "speed_limit_source": "map",
      "speed_limit_resolver": s.get("speed_limit"),
      "speed_limit_assist_state": s.get("speed_limit_assist", ""),
      "speed_limit_assist": s.get("speed_limit_assist", ""),
      "speed_limit_assist_active": bool(s.get("speed_limit_assist")),
      "road_name": s.get("road_name", ""),
      "standstill_timer": s.get("standstill_timer"),
      "blindspot_left": s.get("blindspot_left", False),
      "blindspot_right": s.get("blindspot_right", False),
      "turn_signal_left": s.get("turn_signal_left", False),
      "turn_signal_right": s.get("turn_signal_right", False),
      "rocket_fuel": s.get("rocket_fuel"),
      "long_override": s.get("long_override", False),
      "cluster_speed": s.get("set_speed_kmh"),
      "pcm_cruise_speed": s.get("pcm_cruise_speed", False),
      "scc_vision_enabled": s.get("scc_vision_enabled", False),
      "scc_vision_active": s.get("scc_vision_active", False),
      "scc_map_enabled": s.get("scc_map_enabled", False),
      "speed_limit_scc_map_active": s.get("scc_map_active", False),
      "speed_limit_dashboard": s.get("speed_limit", 0),
      "speed_limit_dashboard_valid": bool(s.get("speed_limit")),
      "speed_limit_map": s.get("speed_limit", 0),
      "speed_limit_map_valid": bool(s.get("speed_limit")),
      "speed_limit_vision": 0,
      "speed_limit_vision_valid": False,
      "signal_assist_action": s.get("signal_assist_action", 0),
      "signal_suspended": s.get("signal_suspended", False),
      "gear_shifter": s.get("gear_shifter", ""),
      "ce_status": s.get("ce_status", 0),
      "e2e_green_light": s.get("e2e_green_light", False),
      "e2e_lead_depart": s.get("e2e_lead_depart", False),
      "carrot_nav": _mock_carrot_nav(s) if s["started"] and s.get("carrot_nav_demo", True) else None,
      "amap_lines": ({"valid": True, "left_blocked": False, "right_blocked": True}
                     if s["started"] and s.get("amap_lines_demo", True) else None),
    },
    "developer_ui": int(s.get("developer_ui", 0)),
    "recording_audio": bool(s.get("recording_audio", False)),
    "torque_bar": bool(s.get("torque_bar", False)),
    "torque_utilization": float(s.get("torque_utilization", 0.0)),
    "steering_angle_deg": float(s.get("steering_angle_deg", -2.4)),
    "lead_d_rel": float(s.get("lead_d_rel", 38.0)) if s["started"] else None,
    "lead_v_rel": float(s.get("lead_v_rel", 1.5)) if s["started"] else None,
    "lead_a_lead_k": float(s.get("lead_a_lead_k", -0.2)) if s["started"] else None,
    "lead2_d_rel": float(s.get("lead2_d_rel", 62.0)) if s["started"] else None,
    "lead2_v_rel": float(s.get("lead2_v_rel", 0.8)) if s["started"] else None,
    "lead2_y_rel": float(s.get("lead2_y_rel", -3.7)) if s["started"] else None,
    "radar_tracks": (_mock_radar_tracks(s)
                     if s["started"] and s.get("radar_tracks_demo", True) else []),
    "road_model": _mock_road_model(s) if s["started"] else None,
    "circular_alert_allowed": s["started"] and s.get("alert_size", "none") in ("none", ""),
    "confidence_ball": {"target": float(s.get("confidence_target", 0.72)), "ui_status": s.get("ui_status", "engaged")} if s["started"] else None,
    "dev_ui": _mock_dev_ui(s) if s["started"] and int(s.get("developer_ui", 0)) > 0 else None,
    "speed_limit_mode": int(s.get("speed_limit_mode", 1)),
    "car_control_enabled": False,
    "is_cruise_set": bool(s["started"]) and s["set_speed_kmh"] > 0,
    "is_cruise_available": True,
    "hide_v_ego_ui": s.get("hide_v_ego_ui", False),
    "road_name_toggle": s.get("road_name_toggle", True),
    "screensaver_enabled": s.get("screensaver_enabled", False),
    "screensaver_timeout_sec": s.get("screensaver_timeout_sec", 300),
    "has_icbm": False,
    "icbm_available": False,
    "enable_bsm": True,
    "sla_available": True,
    "custom_model_active": False,
    "tinygrad_runner_active": False,
    "speed_ms": 0.0,
    "roll": 0.0,
    "max_lateral_accel": 3.0,
    "is_sp_release": False,
    "disable_updates": False,
    "is_release_branch": False,
    "is_development_branch": True,
    "pcm_cruise": s.get("pcm_cruise_speed", False),
    "torque_control_allowed": True,
    "lateral_jerk_torque": 0.0,
    "mads_limited": False,
    "live_lateral_delay": None,
    "steer_actuator_delay": 0.1,
    "tesla_has_vehicle_bus": False,
    "subaru_sng_available": False,
    "cp_loaded": True,
    "models_state": {"qcom_selected": True, "usbgpu_selected": False},
    "driver_face": None,
    "turn_signals": True,
    "blindspot": True,
    "rocket_fuel_enabled": True,
    "show_stopping_point": False,
    "show_stopping_point_metrics": False,
    "show_torque_bar": False,
    "show_personality_button": True,
    "show_speed_limit_sources": False,
    "developer_sidebar": False,
    "developer_sidebar_metrics": [0, 0, 0, 0, 0, 0, 0],
    "navigation_card_enabled": True,
    "nav_card": {
      "enabled": True,
      "valid": True,
      "collapsed": False,
      "instruction": {
        "valid": True,
        "maneuverPrimaryText": "Mock Ave",
        "maneuverSecondaryText": "",
        "maneuverDistance": 320.0,
        "maneuverType": "turn",
        "maneuverModifier": "right",
        "nextManeuverType": "",
        "nextManeuverModifier": "",
      },
    },
    "conditional_experimental": False,
    "speed_limit_changed_alert": False,
    "a_ego": -0.8,
    "dm_arc": {
      "visible": True,
      "prob": s.get("dm_prob", 0.8),
      "pose": s.get("dm_pose", [0, 0, 0]),
      "engaged": s["engaged"],
      "rhd": False,
      "active": True,
      "pose_h": 0.35,
      "pose_v": 0.22,
      "face_outline": [
        [96, 70], [88, 72], [84, 78], [80, 86], [78, 92], [76, 100], [74, 112],
        [74, 128], [76, 134], [80, 142], [84, 148], [90, 154], [96, 158], [102, 154],
        [108, 148], [112, 142], [116, 134], [118, 128], [118, 112], [116, 100],
        [114, 92], [112, 86], [108, 78], [104, 72], [96, 70],
      ],
    } if s["started"] else None,
    "startup_blockers": _mock_startup_blockers(s),
    "ignition": False,
    "can_start": not _mock_startup_blockers(s),
    "alert_sound": str(s.get("alert_sound", "none") or "none"),
    "quiet_mode": _mock_quiet_mode(),
    "is_body": bool(s.get("is_body", False)),
    "carrot_web_enabled": bool(s.get("carrot_web_enabled", _mock_carrot_web_enabled())),
    "pearl_eyes": bool(s.get("pearl_eyes", False)),
    "dm_state": {
      "valid": True,
      "faceDetected": True,
      "isDistracted": False,
      "lockout": False,
      "alwaysOnLockout": False,
      "isRHD": False,
      "cameraUnavailable": False,
      "activePolicy": "vision",
    } if s["started"] else None,
    "driver_state": {
      "valid": True,
      "frameId": int(time.monotonic() * 20),
      "leftDriverData": {
        "faceOrientation": [0.1, 0.05, 0.0],
        "faceOrientationStd": [0.1, 0.1, 0.1],
        "sunglassesProb": 0.0,
        "leftEyeProb": 0.9,
        "rightEyeProb": 0.9,
        "leftBlinkProb": 0.0,
        "rightBlinkProb": 0.0,
      },
      "rightDriverData": {
        "faceOrientation": [0.1, 0.05, 0.0],
        "faceOrientationStd": [0.1, 0.1, 0.1],
        "sunglassesProb": 0.0,
        "leftEyeProb": 0.9,
        "rightEyeProb": 0.9,
        "leftBlinkProb": 0.0,
        "rightBlinkProb": 0.0,
      },
    } if s["started"] else None,
  }


def _mock_quiet_mode() -> bool:
  try:
    return MockParams().get_bool("QuietMode")
  except Exception:
    return False


def _mock_carrot_web_enabled() -> bool:
  try:
    return MockParams().get_bool("CarrotWebEnabled")
  except Exception:
    return False


def mock_wifi_networks() -> list[dict[str, Any]]:
  return [
    {"ssid": "Home-5G", "strength": 92, "security": 2, "connected": True, "saved": True},
    {"ssid": "Office", "strength": 67, "security": 2, "connected": False, "saved": True},
    {"ssid": "Guest", "strength": 45, "security": 0, "connected": False, "saved": False},
  ]


def _seed_carrot_navi_params() -> None:
  """Pre-populate CarrotNaviCrossroad / CarrotNaviImage / CarrotNaviDebug / CarrotNaviMediaMock for PC dev preview."""
  if not SIM.get("carrot_crossroad_demo"):
    return
  import base64
  # 1x1 transparent PNG placeholder so the UI can render an <img> without a real source.
  tiny_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
  b64 = base64.b64encode(tiny_png).decode("ascii")
  MockParams._store.update({
    "CarrotNaviCrossroad": json.dumps({
      "distanceM": 320,
      "imageCode": 42,
      "imageUrl": "https://example.com/crossroad.png",
      "totalMeters": 1200.5,
      "remainRatio": 0.72,
      "ts": 1726000000,
    }),
    "CarrotNaviImage": json.dumps({
      "show": True,
      "imageBase64": b64,
      "imageMime": "image/png",
      "imageEncoding": "base64",
      "imageWidth": 1,
      "imageHeight": 1,
      "imageHash": "mockhash0001",
      "imageUrl": "https://example.com/crossroad.png",
      "imageTooLarge": False,
      "totalMeters": 1200.5,
      "remainRatio": 0.72,
      "ts": 1726000000,
      "receivedMono": 1726000.0,
    }),
    "CarrotNaviDebug": json.dumps({
      "receivedAt": "2026-09-12T15:10:00",
      "eventTimeMs": 1234567890,
      "type": "complexCrossroad",
      "summary": {"type": "complexCrossroad", "keys": ["crossroad", "imageBase64"]},
    }),
    "CarrotNaviMediaMock": json.dumps({
      "tbt_current_full": {
        "show": True,
        "imageBase64": b64,
        "imageWidth": 1,
        "imageHeight": 1,
      },
      "lane_top": {
        "show": True,
        "imageBase64": b64,
        "imageWidth": 1,
        "imageHeight": 1,
      },
      "traffic_signal": {
        "show": True,
        "imageBase64": b64,
        "imageWidth": 1,
        "imageHeight": 1,
      },
      "center_tbt_icon": {
        "show": True,
        "imageBase64": b64,
        "imageWidth": 1,
        "imageHeight": 1,
      },
    }),
  })


def install_openpilot_mocks(root: str) -> None:
  """Call once before importing webui.server.*"""
  import logging
  import sys

  log = logging.getLogger("webuid")
  logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

  class _CloudLog:
    def info(self, msg: str, *a, **k) -> None:
      log.info(msg)

    def warning(self, msg: str, *a, **k) -> None:
      log.warning(msg)

    def error(self, msg: str, *a, **k) -> None:
      log.error(msg)

  op = types.ModuleType("openpilot")
  common = types.ModuleType("openpilot.common")
  params_mod = types.ModuleType("openpilot.common.params")

  class UnknownKeyName(Exception):
    pass

  params_mod.Params = MockParams
  params_mod.UnknownKeyName = UnknownKeyName
  params_mod.ParamKeyType = ParamKeyType
  swaglog_mod = types.ModuleType("openpilot.common.swaglog")
  swaglog_mod.cloudlog = _CloudLog()

  # jeepney is a Linux-only D-Bus binding and is not installable on the PC dev host.
  # openpilot.sunnypilot.carrot.bluetooth.bluez imports it at module load, so stub the
  # symbols it touches: the PC preview must still boot (bluetooth stays unavailable).
  jeepney = types.ModuleType("jeepney")
  jeepney_wrappers = types.ModuleType("jeepney.wrappers")
  jeepney_io = types.ModuleType("jeepney.io")
  jeepney_io_asyncio = types.ModuleType("jeepney.io.asyncio")

  class _DBusAddress:
    def __init__(self, object_path, bus_name=None):
      self.object_path = object_path
      self.bus_name = bus_name

  class _HeaderFields:
    member = "member"
    sender = "sender"
    interface = "interface"

  class _MatchRule:
    def __init__(self, **kwargs):
      self.kwargs = kwargs

  jeepney.DBusAddress = _DBusAddress
  jeepney.HeaderFields = _HeaderFields
  jeepney.MatchRule = _MatchRule
  jeepney.new_method_call = lambda *a, **k: None
  jeepney.new_method_return = lambda *a, **k: None
  jeepney.new_error = lambda *a, **k: None
  jeepney_wrappers.unwrap_msg = lambda msg: msg
  jeepney_io.__path__ = []
  jeepney_io_asyncio.open_dbus_router = lambda *a, **k: None
  jeepney_io.asyncio = jeepney_io_asyncio

  sys.modules["jeepney"] = jeepney
  sys.modules["jeepney.wrappers"] = jeepney_wrappers
  sys.modules["jeepney.io"] = jeepney_io
  sys.modules["jeepney.io.asyncio"] = jeepney_io_asyncio

  sys.modules["openpilot"] = op
  sys.modules["openpilot.common"] = common
  sys.modules["openpilot.common.params"] = params_mod
  sys.modules["openpilot.common.swaglog"] = swaglog_mod
  op.common = common
  common.params = params_mod
  common.swaglog = swaglog_mod

  # The fake "openpilot" package must still expose the real subpackages on disk
  # (openpilot.cereal.log, openpilot.selfdrive.locationd.calibrationd,
  # openpilot.sunnypilot.carrot.bluetooth, ...). Without __path__ Python refuses to
  # resolve any submodule and the server dies on import.
  real_openpilot = os.path.join(root, "openpilot")
  if os.path.isdir(real_openpilot):
    op.__path__ = [real_openpilot]
  common.__path__ = [os.path.join(real_openpilot, "common")] if os.path.isdir(os.path.join(real_openpilot, "common")) else []

  if root not in sys.path:
    sys.path.insert(0, root)

  os.environ["WEBUI_DEV_PC"] = "1"
  os.environ.setdefault("OPENPILOT_ROOT", root)
  MockParams()  # trigger full _seed_params() before carrot-navi overlay adds its keys
  _seed_carrot_navi_params()
