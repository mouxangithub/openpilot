"""Lightweight UI state from cereal (mirrors ui_state.py)."""

from __future__ import annotations

import math
import time
from typing import Any

from webui.server.bridge.ui_status import derive_engaged, derive_ui_status

# Speed-limit display: keep km/h integers for the UI; m/s values are converted
# only when needed.
CV_KPH_TO_MS = 1 / 3.6

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


def _models_state(p) -> dict[str, bool]:
  """Mirror sunnypilot's source-aware active-bundle check, used by the Models panel visibility logic."""
  if p is None:
    return {"qcom_selected": False, "usbgpu_selected": False}
  try:
    return {
      "qcom_selected": bool(p.get("ModelManager_ActiveBundle")),
      "usbgpu_selected": bool(p.get("ModelManager_ActiveBundleChestnut")),
    }
  except Exception:
    return {"qcom_selected": False, "usbgpu_selected": False}


def _safe_kph(value: Any) -> int | None:
  try:
    ms = float(value)
  except (TypeError, ValueError):
    return None
  if ms != ms or ms <= 0.:
    return None
  return round(ms * 3.6)


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


def _egpu_state(ds, started: bool, sm=None) -> dict[str, Any] | None:
  """Mirror sunnypilot sidebarSP _get_home_icon eGPU logic."""
  try:
    from openpilot.common.params import Params
    p = Params()
    chestnut_present = bool(ds.chestnutPresent) if hasattr(ds, "chestnutPresent") else False
    if not chestnut_present:
      return None
    usbgpu_compiled = False
    try:
      from openpilot.selfdrive.modeld.helpers import usbgpu_compiled as _usbgpu_compiled
      usbgpu_compiled = _usbgpu_compiled()
    except Exception:
      pass
    usbgpu_active = p.get("UsbGpuActive")
    usbgpu_loading = p.get_bool("UsbGpuLoading")
    model_runner_tinygrad = False
    try:
      for source in ("usbgpu", "tici"):
        key = f"ActiveBundle{source.capitalize()}"
        bundle = p.get(key)
        if bundle:
          model_runner_tinygrad = bundle.get("runner") == "tinygrad" if isinstance(bundle, dict) else False
          break
    except Exception:
      pass
    big_model_selected = usbgpu_compiled or model_runner_tinygrad
    big_model_failed = False
    if started and chestnut_present:
      big_model_failed = (
        usbgpu_active is False
        or not chestnut_present
        or (usbgpu_active is True and sm is not None and sm.valid.get("modelV2") and not sm["modelV2"].alive)
      )
    loading = usbgpu_loading or (big_model_selected and started and usbgpu_active is None)
    if loading:
      return {"state": "loading"}
    if big_model_selected and big_model_failed:
      return {"state": "failed"}
    if big_model_selected:
      return {"state": "green"}
    return {"state": "gray"}
  except Exception:
    return None


def _carrot_lane_blocked(sm: Any) -> tuple[bool, bool]:
  """Carrot 7714 lane-blocked flags for the lines bracketing the ego lane.

  ``carrot_man._apply_carrot_navi_sp`` derives
  ``carStateSP.carrotLeftLineBlocked / carrotRightLineBlocked`` from
  ``carrotNaviSP.laneCurrent.available`` and sets ``carrotLaneValid`` True only
  while the Carrot 7714 v2 sender is feeding lane data.  When no v2 source is
  present the merge is a strict no-op and the flag stays False, so gating on it
  is enough — no extra Params read is needed here.  Returns (left, right) where
  True means the adjacent lane is blocked and a lane change toward that side
  should not be initiated from nav data alone.
  """
  try:
    if not sm.valid.get("carStateSP"):
      return False, False
    cssp = sm["carStateSP"]
    if not bool(getattr(cssp, "carrotLaneValid", False)):
      return False, False
    left = bool(getattr(cssp, "carrotLeftLineBlocked", False))
    right = bool(getattr(cssp, "carrotRightLineBlocked", False))
    return left, right
  except Exception:
    return False, False


def _road_model(sm: Any) -> dict[str, Any] | None:
  """Sample modelV2 lane geometry at fixed distances for the road-lite scene.

  Returns lateral offsets (model frame, +right) of road edges / lane lines at
  fixed longitudinal distances, plus laneLineProbs, the planned trajectory
  (model.path, same frame) with its lateral std, and leadsV3 tracks so the
  frontend can render a curved road with a dynamic lane count, a rainbow
  planning path and adjacent vehicles. None when no model data — the
  frontend falls back to a straight road.
  """
  if not sm.valid.get("modelV2"):
    return None
  try:
    model = sm["modelV2"]
    dists = (5.0, 15.0, 30.0, 50.0, 80.0, 120.0, 160.0)

    def _sample_y(line: Any) -> list[float] | None:
      xs, ys = line.x, line.y
      n = min(len(xs), len(ys))
      if n < 2:
        return None
      xs_f = [float(xs[i]) for i in range(n)]
      ys_f = [float(ys[i]) for i in range(n)]
      if xs_f[-1] <= xs_f[0]:
        return None
      out = []
      for d in dists:
        if d <= xs_f[0]:
          out.append(round(ys_f[0], 2))
          continue
        if d >= xs_f[-1]:
          out.append(round(ys_f[-1], 2))
          continue
        for i in range(n - 1):
          if xs_f[i] <= d <= xs_f[i + 1]:
            t = (d - xs_f[i]) / max(xs_f[i + 1] - xs_f[i], 1e-6)
            out.append(round(ys_f[i] + t * (ys_f[i + 1] - ys_f[i]), 2))
            break
      return out

    edges = [_sample_y(e) if e is not None else None for e in model.roadEdges]
    lines = [_sample_y(l) for l in model.laneLines]

    # Lane-line style. ``line_types`` keeps its original 0/1 meaning (0 dashed,
    # 1 solid); ``line_kinds`` carries the richer Carrot 7714 v2 lane codes for
    # the two lines bracketing the ego lane (see CarrotNaviSP.laneCurrent):
    #   0 unknown · 1 solid white · 2 dashed white · 3 solid yellow
    #   4 double yellow · 5 botts dots · 6 road edge
    # Order matches model.laneLines: [outer left, inner left, inner right, outer right].
    carrot_l_blocked, carrot_r_blocked = _carrot_lane_blocked(sm)
    # Carrot 7714 v2 only exposes boolean "blocked" lane flags.  Treat blocked
    # as a solid white line and unblocked as dashed white for the road-lite
    # renderer; the outer edges fall back to road edge when missing.
    carrot_l_kind = 1 if carrot_l_blocked else 2
    carrot_r_kind = 1 if carrot_r_blocked else 2
    outer_l = 6 if (edges[0] is None and lines[0] is not None) else 0
    outer_r = 6 if (edges[1] is None and lines[3] is not None) else 0
    line_kinds = [outer_l, carrot_l_kind, carrot_r_kind, outer_r]
    solid_kinds = (1, 3, 4, 6)
    line_types = [1 if kind in solid_kinds else 0 for kind in line_kinds]

    probs: list[float] = []
    try:
      probs = [round(float(p), 2) for p in model.laneLineProbs][:4]
    except Exception:
      probs = []
    if all(e is None for e in edges) and all(l is None for l in lines):
      return None

    # Ego-lane centerline per sampled distance: midpoint of the innermost visible
    # pair bracketing the ego (lateral 0). The frontend uses this for the lane
    # sheen and the lane-change arch so both follow the real lane rather than the
    # road centre (which is only correct when the ego happens to sit in the
    # middle lane). 0.0 where the lane cannot be bracketed.
    lane_centers: list[float] = []
    for k in range(len(dists)):
      neg = [l[k] for l in lines if l is not None and l[k] < -0.2]
      pos = [l[k] for l in lines if l is not None and l[k] > 0.2]
      lane_centers.append(round((max(neg) + min(pos)) / 2.0, 2) if neg and pos else 0.0)

    def _first(series: Any, default: float = 0.0) -> float:
      try:
        return float(series[0])
      except Exception:
        return default

    leads = []
    try:
      for idx, lead in enumerate(model.leadsV3):
        prob = _first(lead.prob)
        if prob < 0.3 or len(lead.x) == 0 or len(lead.y) == 0:
          continue
        x0, y0 = float(lead.x[0]), float(lead.y[0])
        if not (2.0 < x0 < 150.0) or x0 != x0 or y0 != y0:
          continue
        # v / a and the lateral & longitudinal std feed the road-lite target
        # classification: small, slow, high-uncertainty blobs read as
        # two-wheelers or pedestrians rather than cars.
        #
        # heading is the target's motion direction in the ego frame, radians,
        # left-positive: 0 = receding straight ahead, ±pi/2 = crossing,
        # |heading| > pi/2 = oncoming. Derived from the first two samples of the
        # predicted trajectory (model frame is x forward, y +right → negated).
        heading = None
        try:
          if len(lead.x) >= 2 and len(lead.y) >= 2:
            dx = float(lead.x[1]) - float(lead.x[0])
            dy = float(lead.y[1]) - float(lead.y[0])
            if abs(dx) > 1e-3 or abs(dy) > 1e-3:
              heading = round(-math.atan2(dy, dx), 3)
        except Exception:
          heading = None
        leads.append({
          "d": round(x0, 1),
          "y": round(y0, 2),
          "prob": round(prob, 2),
          "v": round(_first(lead.v), 2),
          "a": round(_first(lead.a), 2),
          "y_std": round(_first(lead.yStd), 3),
          "x_std": round(_first(lead.xStd), 3),
          "heading": heading,
          "i": idx,
        })
    except Exception:
      leads = []
    leads = leads[:3]

    # planned trajectory: sample model.path (x forward, y lateral, +right,
    # same model frame as laneLines) at the same distances; path.std gives
    # the lateral uncertainty used by the frontend for the ribbon width.
    path: list[float] | None = None
    path_std: list[float] | None = None
    try:
      px = [float(v) for v in model.path.x]
      py = [float(v) for v in model.path.y]
      if len(px) >= 2 and len(py) == len(px) and px[-1] > px[0]:
        path = _interp_at(px, py, dists)
        try:
          pstd = [float(v) for v in model.path.std]
          if len(pstd) == len(px):
            path_std = _interp_at(px, pstd, dists)
        except Exception:
          path_std = None
    except Exception:
      path = None

    return {
      "dists": list(dists),
      "edges": edges,
      "lines": lines,
      "probs": probs,
      "line_types": line_types,
      "line_kinds": line_kinds,
      "lane_centers": lane_centers,
      "leads": leads,
      "path": path,
      "path_std": path_std,
    }
  except Exception:
    return None


def _interp_at(xs: list[float], ys: list[float], dists) -> list[float]:
  """Linear interp of ys over xs at the requested distances (clamped at ends)."""
  out: list[float] = []
  for d in dists:
    if d <= xs[0]:
      out.append(round(ys[0], 2))
      continue
    if d >= xs[-1]:
      out.append(round(ys[-1], 2))
      continue
    for i in range(len(xs) - 1):
      if xs[i] <= d <= xs[i + 1]:
        t = (d - xs[i]) / max(xs[i + 1] - xs[i], 1e-6)
        out.append(round(ys[i] + t * (ys[i + 1] - ys[i]), 2))
        break
  return out


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
  carrot_panel_side = 0
  carrot_panel_opacity = 100
  turn_signals = car_ctx.turn_signals
  blindspot = car_ctx.blindspot
  rocket_fuel_enabled = car_ctx.rocket_fuel_enabled
  p = None
  try:
    from openpilot.common.params import Params
    p = Params()
    experimental_confirmed = p.get_bool("ExperimentalModeConfirmed")
    screensaver_enabled = p.get_bool("ScreenSaverEnabled")
    screensaver_timeout_sec = int(p.get("ScreenSaverTimeout", return_default=True) or 300)
    speed_limit_mode = int(p.get("SpeedLimitMode", return_default=True) or 0)
    carrot_panel_side = int(p.get("CarrotPanelSide", return_default=True) or 0)
    carrot_panel_opacity = int(p.get("CarrotPanelOpacity", return_default=True) or 100)
    carrot_web_enabled = p.get_bool("CarrotWebEnabled")
    # Conditional experimental mode: 0 off, 1 curves, 2 lead, 3 signal, 4 manual.
    ce_status = int(p.get("CEStatus", return_default=True) or 0)
    # Visual speed-limit detector result lives in the memory params store.
    vision_limit_ms = 0.0
    vision_limit_enabled = False
    try:
      from openpilot.common.params import Params as _Params
      mem = _Params("/dev/shm/params")
      vision_limit_ms = float(mem.get_float("VisionSpeedLimit"))
      vision_limit_enabled = p.get_bool("VisionSpeedLimitEnabled")
    except Exception:
      pass
  except Exception:
    ce_status = 0
    vision_limit_ms = 0.0
    vision_limit_enabled = False

  has_longitudinal = car_ctx.has_longitudinal_control
  alpha_long_available = car_ctx.alpha_long_available
  has_icbm = car_ctx.has_icbm

  # Onroad navigation instruction card (BIG UI navigation_card.py). carrot_man
  # assembles NavInstructionState into a JSON param; the web card reads the same
  # state every payload. NavDestination is the route-existence gate.
  nav_card: dict[str, Any] = {
    "enabled": car_ctx.navigation_card_enabled,
    "valid": False,
    "collapsed": False,
    "instruction": None,
  }
  try:
    if p is not None:
      raw_instruction = p.get("NavInstructionState")
      if isinstance(raw_instruction, (bytes, str)):
        raw_instruction = raw_instruction.decode("utf-8", "replace") if isinstance(raw_instruction, bytes) else raw_instruction
        import json as _json
        parsed = _json.loads(raw_instruction) if raw_instruction else None
      else:
        parsed = raw_instruction
      if isinstance(parsed, dict) and parsed:
        nav_card["instruction"] = parsed
        nav_card["valid"] = True
      nav_card["valid"] = nav_card["valid"] and p.get("NavDestination") is not None
      nav_card["collapsed"] = p.get_bool("NavInstructionCollapsed")
  except Exception:
    pass

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
  # Big UI gates Lane Center Assist (Blendful) on the tinygrad runner being
  # active (models.py `blendful_allowed`); mirror that state for the webui.
  tinygrad_runner_active = False
  try:
    for _key in ("ActiveBundleUsbgpu", "ActiveBundleTici"):
      _bundle = p.get(_key)
      if _bundle:
        tinygrad_runner_active = _bundle.get("runner") == "tinygrad" if isinstance(_bundle, dict) else False
        break
  except Exception:
    pass
  is_body = car_ctx.is_body
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
    # Traffic-signal evidence observed by the planner: 0 unknown, 1 red, 2 green,
    # 3 mixed. This fork reports the observed colour, not a planner action.
    "signal_assist_action": 0,
    "signal_suspended": False,
    # Gear position, needed by the developer sidebar metrics.
    "gear_shifter": "",
    # Conditional experimental mode reason (see conditional_experimental_mode.py).
    "ce_status": ce_status,
    # Per-source speed-limit values for the source drawer.
    "speed_limit_dashboard": 0,
    "speed_limit_dashboard_valid": False,
    "speed_limit_map": 0,
    "speed_limit_map_valid": False,
    "speed_limit_vision": 0,
    "speed_limit_vision_valid": False,
  }
  try:
    # Live blind-spot / turn-signal state comes from carState. SelfdriveStateSP
    # only carries mads/icbm/buttonsPressed/buttonsReleaseToggle, so the old
    # getattr() calls on it always fell through to False and the road-lite BSM
    # and turn-signal indicators never lit.
    sp_hud.update({
      "blindspot_left": bool(getattr(cs, "leftBlindspot", False)),
      "blindspot_right": bool(getattr(cs, "rightBlindspot", False)),
      "turn_signal_left": bool(getattr(cs, "leftBlinker", False)),
      "turn_signal_right": bool(getattr(cs, "rightBlinker", False)),
      # gearShifter lives on carState in this fork (not on carStateSP).
      "gear_shifter": str(getattr(cs, "gearShifter", "") or ""),
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

        # The targets these two controllers are actually commanding, in m/s, and only
        # while active. V_CRUISE_UNSET (255) means "not constraining", so it is filtered
        # out rather than shown - a sentinel must never render as a speed.
        #
        # Why the HUD needs these: carrot also computes its own curve speed
        # (carrot_functions.vturn_speed) and publishes it as vTurnSpeed / desiredSpeed.
        # That computation is display-only and uses a different model - max orientation
        # rate against a fixed 1.9 m/s^2 target - from the controller that actually
        # executes, which is SCC-V at the 97th-percentile curvature against a tuned
        # a_lat ceiling. Showing only carrot's number let the HUD disagree with the car.
        for key, ctrl in (("scc_vision", vision), ("scc_map", map_)):
          v_raw = float(getattr(ctrl, "vTarget", 0.0) or 0.0)
          active = bool(getattr(ctrl, "active", False))
          sp_hud[f"{key}_v_target_ms"] = v_raw if active and 0.0 < v_raw < 255.0 else 0.0
      e2e = getattr(lp_sp, "e2eAlerts", None)
      if e2e is not None:
        sp_hud["e2e_green_light"] = bool(getattr(e2e, "greenLightAlert", False))
        sp_hud["e2e_lead_depart"] = bool(getattr(e2e, "leadDepartAlert", False))
      # Traffic-signal evidence for the signal HUD ring.
      sp_hud["signal_assist_action"] = int(getattr(lp_sp, "signalAssistAction", 0) or 0)
      sp_hud["signal_suspended"] = bool(getattr(lp_sp, "signalDetectionSuspended", False))
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
      # Map-side limit (OSM). The drawer's "Map Data" row reads this; the merged
      # resolver value may have come from carrot instead, so keep them separate.
      if not sp_hud.get("speed_limit_map_valid"):
        map_limit = float(getattr(lmd, "speedLimit", 0) or 0)
        sp_hud["speed_limit_map"] = round(map_limit * conv)
        sp_hud["speed_limit_map_valid"] = bool(getattr(lmd, "speedLimitValid", False)) and map_limit > 0
    # Visual detector limit: only meaningful when the detector is enabled.
    if vision_limit_enabled and vision_limit_ms > 0:
      sp_hud["speed_limit_vision"] = round(vision_limit_ms * (3.6 if is_metric else 2.23694))
      sp_hud["speed_limit_vision_valid"] = True
    # Carrot 7714 v2 lane-line edge bars (mirrors GUI CarrotLaneIndicators).
    if sm.valid.get("carStateSP"):
      cssp = sm["carStateSP"]
      sp_hud["amap_lines"] = {
        "valid": bool(getattr(cssp, "carrotLaneValid", False)),
        "left_blocked": bool(getattr(cssp, "carrotLeftLineBlocked", False)),
        "right_blocked": bool(getattr(cssp, "carrotRightLineBlocked", False)),
      }
      # Per-source speed-limit values for the source drawer. The resolver only
      # publishes the merged result, so each source has to be read at its origin:
      # CAN sign (carStateSP), OSM map (liveMapDataSP), visual detector (memory param).
      if not sp_hud.get("speed_limit_dashboard_valid"):
        dash = float(getattr(cssp, "speedLimit", 0) or 0)
        sp_hud["speed_limit_dashboard"] = round(dash * (3.6 if is_metric else 2.23694))
        sp_hud["speed_limit_dashboard_valid"] = dash > 0
    # Carrot navigation HUD panel (mirrors GUI CarrotNavigationPanel reading carrotManSP).
    if sm.valid.get("carrotManSP"):
      cmn = sm["carrotManSP"]
      def _txt(name: str) -> str:
        return str(getattr(cmn, name, "") or "")

      def _num(name: str, default: int = 0) -> int:
        try:
          return int(getattr(cmn, name, default) or 0)
        except (TypeError, ValueError):
          return default

      sp_hud["carrot_nav"] = {
        "active": _num("activeCarrot"),
        "road_limit_speed": _num("nRoadLimitSpeed"),
        "spd_type": _num("xSpdType", -1),
        "spd_limit": _num("xSpdLimit"),
        "spd_dist": _num("xSpdDist"),
        "spd_countdown": _num("xSpdCountDown"),
        "turn_info": _num("xTurnInfo", -1),
        "dist_to_turn": _num("xDistToTurn"),
        "turn_countdown": _num("xTurnCountDown"),
        "atc_type": _txt("atcType"),
        "v_turn_speed": _num("vTurnSpeed"),
        "road_name": _txt("szPosRoadName"),
        "tbt_main_text": _txt("szTBTMainText"),
        "tbt_main_text_next": _txt("szTBTMainTextNext"),
        "near_dir_name": _txt("szNearDirName"),
        "desired_speed": _num("desiredSpeed"),
        "desired_source": _txt("desiredSource"),
        # Pre-resolved by carrot_man: the driver-facing reason and its colour mode.
        # The raw token above stays for diagnostics; the UI shows these.
        "desired_source_label": _txt("desiredSourceLabel"),
        "desired_source_color": _num("desiredSourceColor"),
        "traffic_state": _num("trafficState"),
        "traffic_countdown": _num("trafficCountdown"),
        "left_sec": _num("leftSec"),
        "go_pos_dist": _num("nGoPosDist"),
        "go_pos_time": _num("nGoPosTime"),
        "goal_name": _txt("szGoalName"),
        "sdi_descr": _txt("szSdiDescr"),
        "road_cate": _num("roadCate"),
        # Service area / toll gate hint (App §2.3 SAPA_* group).
        "sapa_name": _txt("sapaName"),
        "sapa_dist": _num("sapaDist"),
        "sapa_type": _num("sapaType"),
        "sapa_cnt": _num("sapaCnt"),
        # TMC congestion summary (App §2.5). The per-segment arrays ride as JSON
        # strings on carrotManSP; expose them verbatim so the HUD can render the
        # congestion bar without a second schema change.
        "tmc_overall_status": _num("tmcOverallStatus"),
        "tmc_total_distance": _num("tmcTotalDistance"),
        "tmc_residual_distance": _num("tmcResidualDistance"),
        "tmc_segment_count": _num("tmcSegmentCount"),
        "tmc_segment_statuses": _txt("tmcSegmentStatuses"),
        "tmc_segment_distances": _txt("tmcSegmentDistances"),
        # Guided-lane arrow codes (App §2.2).
        "nav_lane_guide": _txt("navLaneGuide"),
        "nav_lane_guide_cnt": _num("navLaneGuideCnt"),
        "panel_side": carrot_panel_side,
        "panel_opacity": max(0, min(100, carrot_panel_opacity)),
      }

    # navInstructionCarrotSP - the fused stock-navd + 7714 guidance stream.
    #
    # carrot_man publishes this but nothing consumed it, so the webui HUD was missing
    # what only this service carries: the multi-step manoeuvre list and the per-lane
    # guidance arrows. Note carrot_man does NOT publish carStateSP, so this is the only
    # route for those two. Everything below is display-only; no control reads it.
    #
    # capnp List fields are not JSON-serialisable, so they are flattened by hand; a
    # malformed or absent service must leave the key out entirely rather than raise.
    if sm.valid.get("navInstructionCarrotSP"):
      try:
        ni = sm["navInstructionCarrotSP"]

        def _enum_int(value, default: int = 0) -> int:
          # capnp enums surface as either an int or an "Enum.name" string depending on
          # how they were built; normalise both to an int.
          if isinstance(value, int):
            return value
          text = str(value)
          return int(text.rsplit(".", 1)[-1]) if text.isdigit() else default

        def _enum_name(value) -> str:
          text = str(value)
          return text.rsplit(".", 1)[-1] if "." in text else text

        maneuvers = []
        for mv in getattr(ni, "allManeuvers", []):
          maneuvers.append({
            "distance": float(getattr(mv, "distance", 0.0) or 0.0),
            "type": str(getattr(mv, "type", "") or ""),
            "modifier": str(getattr(mv, "modifier", "") or ""),
          })

        lanes = []
        for ln in getattr(ni, "lanes", []):
          lanes.append({
            "directions": [_enum_int(d) for d in getattr(ln, "directions", [])],
            "active": bool(getattr(ln, "active", False)),
            "active_direction": _enum_int(getattr(ln, "activeDirection", 0)),
          })

        sp_hud["carrot_instruction"] = {
          "valid": True,
          "primary_text": str(getattr(ni, "maneuverPrimaryText", "") or ""),
          "secondary_text": str(getattr(ni, "maneuverSecondaryText", "") or ""),
          "maneuver_distance": float(getattr(ni, "maneuverDistance", 0.0) or 0.0),
          "maneuver_type": str(getattr(ni, "maneuverType", "") or ""),
          "maneuver_modifier": str(getattr(ni, "maneuverModifier", "") or ""),
          "distance_remaining": float(getattr(ni, "distanceRemaining", 0.0) or 0.0),
          "time_remaining": float(getattr(ni, "timeRemaining", 0.0) or 0.0),
          "time_remaining_typical": float(getattr(ni, "timeRemainingTypical", 0.0) or 0.0),
          "speed_limit": float(getattr(ni, "speedLimit", 0.0) or 0.0),
          "speed_limit_sign": _enum_name(getattr(ni, "speedLimitSign", "")),
          "show_full": bool(getattr(ni, "showFull", False)),
          "maneuvers": maneuvers,
          "lanes": lanes,
        }
      except Exception as e:
        sp_hud["carrot_instruction"] = {"valid": False, "error": f"{type(e).__name__}: {e}"}
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

  steering_angle_deg = None
  try:
    val = float(cs.steeringAngleDeg)
    if val == val:
      steering_angle_deg = round(val, 1)
  except Exception:
    pass

  lead_d_rel = None
  lead_v_rel = None
  lead_a_lead_k = None
  lead2_d_rel = None
  lead2_v_rel = None
  lead2_y_rel = None
  try:
    if sm.valid.get("radarState"):
      lead = sm["radarState"].leadOne
      if lead is not None and getattr(lead, "present", False):
        d_rel = float(lead.dRel)
        v_rel = float(lead.vRel)
        if d_rel == d_rel:
          lead_d_rel = round(d_rel, 1)
        if v_rel == v_rel:
          lead_v_rel = round(v_rel, 2)
        # kalman-filtered lead accel — drives the lead brake lights in road lite
        a_lead = float(getattr(lead, "aLeadK", 0.0) or 0.0)
        if a_lead == a_lead:
          lead_a_lead_k = round(a_lead, 2)
      # adjacent-lane lead (radar's secondary track; yRel is lateral offset, +left)
      lead2 = sm["radarState"].leadTwo
      if lead2 is not None and getattr(lead2, "present", False):
        d2 = float(lead2.dRel)
        v2 = float(lead2.vRel)
        y2 = float(lead2.yRel)
        if d2 == d2 and 0.0 < d2 < 140.0:
          lead2_d_rel = round(d2, 1)
        if v2 == v2:
          lead2_v_rel = round(v2, 2)
        if y2 == y2:
          lead2_y_rel = round(y2, 2)
  except Exception:
    pass

  # Full radar track list (Car.RadarData.points). radarState only carries
  # leadOne/leadTwo, so front-left / front-right and flanking objects are
  # invisible without this. The road-lite scene uses these to place adjacent-
  # lane and side vehicles on the synthesized road.
  radar_tracks: list[dict[str, Any]] = []
  try:
    if sm.valid.get("radarTracks"):
      for pt in sm["radarTracks"].points:
        d_rel = float(pt.dRel)
        y_rel = float(pt.yRel)
        v_rel = float(pt.vRel)
        # Drop NaN and anything outside the scene's draw frustum.
        if d_rel != d_rel or y_rel != y_rel or v_rel != v_rel:
          continue
        if not -5.0 < d_rel < 160.0 or not -8.0 < y_rel < 8.0:
          continue
        radar_tracks.append({
          "id": int(pt.trackId),
          "d": round(d_rel, 1),
          "y": round(y_rel, 2),
          "v": round(v_rel, 2),
        })
  except Exception:
    radar_tracks = []

  driver_face = _driver_face(sm)
  # Pearl eyes: replace face outline with pearl eyes style when enabled
  pearl_eyes = car_ctx.pearl_eyes if hasattr(car_ctx, "pearl_eyes") else False
  if pearl_eyes and driver_face:
    driver_face["pearl_eyes"] = True
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
    "tinygrad_runner_active": tinygrad_runner_active,
    "is_body": is_body,
    "models_state": _models_state(p),
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
      "egpu_state": _egpu_state(ds, started, sm),
    },
    "controls": {
      "lat_active": bool(ctrl.latActive) if hasattr(ctrl, "latActive") else None,
      "long_active": bool(ctrl.longActive) if hasattr(ctrl, "longActive") else None,
      "lat_control_state": str(ctrl.lateralControlState.which()) if hasattr(ctrl, "lateralControlState") and ctrl.lateralControlState else "",
      "curvature": float(ctrl.curvature) if hasattr(ctrl, "curvature") else 0.0,
      "desired_curvature": float(ctrl.desiredCurvature) if hasattr(ctrl, "desiredCurvature") else 0.0,
    },
    "sp_hud": sp_hud,
    "dm_arc": dm_arc,
    "speed_limit_mode": speed_limit_mode,
    "turn_signals": turn_signals,
    "blindspot": blindspot,
    "rocket_fuel_enabled": rocket_fuel_enabled,
    # StarPilot-era onroad widget gates, read once per frame by car_context.
    "show_stopping_point": car_ctx.show_stopping_point,
    "show_stopping_point_metrics": car_ctx.show_stopping_point_metrics,
    "show_torque_bar": car_ctx.show_torque_bar,
    "show_personality_button": car_ctx.show_personality_button,
    "show_speed_limit_sources": car_ctx.show_speed_limit_sources,
    "developer_sidebar": car_ctx.developer_sidebar,
    "developer_sidebar_metrics": list(car_ctx.developer_sidebar_metrics),
    "navigation_card_enabled": car_ctx.navigation_card_enabled,
    "nav_card": nav_card,
    "conditional_experimental": car_ctx.conditional_experimental,
    "speed_limit_changed_alert": car_ctx.speed_limit_changed_alert,
    "a_ego": float(cs.aEgo) if cs.aEgo == cs.aEgo else 0.0,
    "speed_ms": speed_ms,
    "roll": float(sm["vehicleParameters"].roll) if sm.valid.get("vehicleParameters") else 0.0,
    "max_lateral_accel": float(car_ctx.max_lateral_accel or 3.0),
    "developer_ui": developer_ui,
    "dev_ui": dev_ui,
    "recording_audio": recording_audio,
    "carrot_web_enabled": carrot_web_enabled,
    "torque_bar": torque_bar,
    "torque_utilization": torque_utilization,
    "steering_angle_deg": steering_angle_deg,
    "lead_d_rel": lead_d_rel,
    "lead_v_rel": lead_v_rel,
    "lead_a_lead_k": lead_a_lead_k,
    "lead2_d_rel": lead2_d_rel,
    "lead2_v_rel": lead2_v_rel,
    "lead2_y_rel": lead2_y_rel,
    "radar_tracks": radar_tracks,
    "road_model": _road_model(sm),
    "circular_alert_allowed": circular_alert_allowed,
    "confidence_ball": confidence_ball,
    "driver_face": driver_face,
    "headless": is_headless_mode(),
    "startup_blockers": gate.get("blockers") or [],
    "ignition": bool(gate.get("ignition")),
    "can_start": bool(gate.get("can_start", True)),
    "alert_sound": alert_sound,
    "quiet_mode": quiet_mode,
    "pearl_eyes": pearl_eyes,
    "dm_state": _dm_state_payload(sm),
    "driver_state": _driver_state_payload(sm),
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


def _dm_state_payload(sm: Any) -> dict[str, Any] | None:
  """DriverMonitoringState payload for pearl eyes rendering."""
  if not sm.valid.get("driverMonitoringState"):
    return None
  try:
    dm = sm["driverMonitoringState"]
    return {
      "valid": True,
      "faceDetected": bool(getattr(dm, "faceDetected", False)),
      "isDistracted": bool(getattr(dm, "isDistracted", False)),
      "lockout": bool(getattr(dm, "lockout", False)),
      "alwaysOnLockout": bool(getattr(dm, "alwaysOnLockout", False)),
      "isRHD": bool(getattr(dm, "isRHD", False)),
      "cameraUnavailable": bool(getattr(dm, "cameraUnavailable", False)),
      "activePolicy": str(getattr(dm, "activePolicy", "")),
    }
  except Exception:
    return None


def _driver_state_payload(sm: Any) -> dict[str, Any] | None:
  """DriverStateV2 payload for pearl eyes rendering."""
  if not sm.valid.get("driverStateV2"):
    return None
  try:
    ds = sm["driverStateV2"]
    left = getattr(ds, "leftDriverData", None)
    right = getattr(ds, "rightDriverData", None)

    def _driver_data(d):
      if d is None:
        return None
      return {
        "faceOrientation": list(getattr(d, "faceOrientation", [0, 0, 0])),
        "faceOrientationStd": list(getattr(d, "faceOrientationStd", [0, 0, 0])),
        "sunglassesProb": float(getattr(d, "sunglassesProb", 0) or 0),
        "leftEyeProb": float(getattr(d, "leftEyeProb", 0) or 0),
        "rightEyeProb": float(getattr(d, "rightEyeProb", 0) or 0),
        "leftBlinkProb": float(getattr(d, "leftBlinkProb", 0) or 0),
        "rightBlinkProb": float(getattr(d, "rightBlinkProb", 0) or 0),
      }

    return {
      "valid": True,
      "frameId": int(getattr(ds, "frameId", 0)),
      "leftDriverData": _driver_data(left),
      "rightDriverData": _driver_data(right),
    }
  except Exception:
    return None


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
