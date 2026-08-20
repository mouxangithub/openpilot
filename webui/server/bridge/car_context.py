"""CarParams / display prefs for WebUI without importing ui_state (no pyray/EGL)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WebuiCarContext:
  CP: Any = None
  CP_SP: Any = None
  started_frame: int = 0
  started_time: float = 0.0
  started: bool = False
  recording_audio: bool = False
  developer_ui: Any = 0
  torque_bar: bool = False
  turn_signals: bool = False
  blindspot: bool = False
  rocket_fuel_enabled: bool = False
  rainbow_path: bool = False
  enforce_torque_control: bool = False
  custom_torque_params: bool = False
  torque_override_enabled: bool = False
  torque_override_friction: float = 0.0
  torque_override_lat_accel_factor: float = 0.0
  has_longitudinal_control: bool = False
  has_icbm: bool = False
  icbm_available: bool = False
  is_sp_release: bool = False
  brand: str = ""
  platform: str = ""
  mads_limited: bool = False
  enable_bsm: bool = False
  sla_available: bool = False
  pcm_cruise: bool = False
  alpha_long_available: bool = False
  cp_loaded: bool = False
  torque_control_allowed: bool = True
  lateral_jerk_torque: bool = False
  disable_updates: bool = False
  is_release_branch: bool = False
  is_development_branch: bool = False
  custom_model_active: bool = False
  steer_actuator_delay: float | None = None
  tesla_has_vehicle_bus: bool = False
  subaru_sng_available: bool = True
  pcm_cruise_speed: bool | None = None
  max_lateral_accel: float = 3.0
  car_platform_bundle: dict[str, Any] = field(default_factory=dict)


_ctx = WebuiCarContext()
_prev_started = False
_driver_view_clear_scheduled = False
_driver_view_lock = threading.Lock()


def _clear_driver_view_async() -> None:
  global _driver_view_clear_scheduled
  try:
    from openpilot.common.params import Params
    p = Params()
    if p.get_bool("IsDriverViewEnabled"):
      p.put_bool("IsDriverViewEnabled", False, block=False)
  except Exception:
    pass
  finally:
    with _driver_view_lock:
      _driver_view_clear_scheduled = False


def get_car_context() -> WebuiCarContext:
  return _ctx


def refresh_car_context(sm: Any, started: bool) -> WebuiCarContext:
  """Refresh cached car context from Params (and started_frame from cereal)."""
  global _prev_started

  ctx = _ctx
  ctx.started = started

  if started and not _prev_started:
    try:
      ctx.started_frame = int(sm.recv_frame.get("deviceState", 0) or 0)
      ctx.started_time = time.monotonic()
    except Exception:
      pass
  if not started:
    ctx.started_frame = 0
    ctx.started_time = 0.0

  _prev_started = started

  try:
    from webui.server.bridge.headless_util import is_headless_mode
    if is_headless_mode() and sm.valid.get("pandaStates") and sm["pandaStates"]:
      from openpilot.cereal import log

      ignition = any(
        ps.ignitionLine or ps.ignitionCan
        for ps in sm["pandaStates"]
        if ps.pandaType != log.PandaState.PandaType.unknown
      )
      if ignition:
        with _driver_view_lock:
          if not _driver_view_clear_scheduled:
            _driver_view_clear_scheduled = True
            threading.Thread(target=_clear_driver_view_async, name="clear-driver-view", daemon=True).start()
  except Exception:
    pass

  try:
    from openpilot.cereal import messaging
    from opendbc.car.structs import car
    from openpilot.common.params import Params

    p = Params()
    CP_bytes = p.get("CarParamsPersistent")
    if CP_bytes is not None:
      ctx.CP = messaging.log_from_bytes(CP_bytes, car.CarParams)
      ctx.cp_loaded = True
      ctx.pcm_cruise = bool(getattr(ctx.CP, "pcmCruise", False))
      ctx.alpha_long_available = bool(getattr(ctx.CP, "alphaLongitudinalAvailable", False))
      ctx.enable_bsm = bool(getattr(ctx.CP, "enableBsm", False))
      ctx.steer_actuator_delay = float(getattr(ctx.CP, "steerActuatorDelay", 0) or 0)
      ctx.max_lateral_accel = float(getattr(ctx.CP, "maxLateralAccel", 3.0) or 3.0)
      ctx.brand = ctx.CP.brand or ""
      ctx.platform = ctx.CP.carFingerprint or ""
      ctx.torque_control_allowed = ctx.CP.steerControlType != car.CarParams.SteerControlType.angle
      if ctx.CP.alphaLongitudinalAvailable:
        ctx.has_longitudinal_control = p.get_bool("AlphaLongitudinalEnabled")
      else:
        ctx.has_longitudinal_control = bool(ctx.CP.openpilotLongitudinalControl)
    else:
      ctx.CP = None
      ctx.cp_loaded = False
      ctx.has_longitudinal_control = False
      ctx.brand = ""
      ctx.platform = ""

    CP_SP_bytes = p.get("CarParamsSPPersistent")
    if CP_SP_bytes is not None:
      from openpilot.cereal import custom
      ctx.CP_SP = messaging.log_from_bytes(CP_SP_bytes, custom.CarParamsSP)
      ctx.has_icbm = bool(
        ctx.CP_SP.intelligentCruiseButtonManagementAvailable
        and p.get_bool("IntelligentCruiseButtonManagement")
      )
      ctx.icbm_available = bool(
        ctx.CP_SP.intelligentCruiseButtonManagementAvailable
        and not ctx.has_longitudinal_control
      )
      ctx.pcm_cruise_speed = bool(ctx.CP_SP.pcmCruiseSpeed)
    else:
      ctx.CP_SP = None
      ctx.has_icbm = False
      ctx.icbm_available = False
      ctx.pcm_cruise_speed = None

    bundle = p.get("CarPlatformBundle")
    if isinstance(bundle, dict):
      ctx.car_platform_bundle = bundle
      if not ctx.brand:
        ctx.brand = bundle.get("brand", "") or ""
      if not ctx.platform:
        ctx.platform = bundle.get("platform", "") or ""
    else:
      ctx.car_platform_bundle = {}

    ctx.recording_audio = p.get_bool("RecordAudio") and started
    ctx.developer_ui = p.get("DevUIInfo")
    ctx.torque_bar = p.get_bool("TorqueBar")
    ctx.turn_signals = p.get_bool("ShowTurnSignals")
    ctx.blindspot = p.get_bool("BlindSpot")
    ctx.rocket_fuel_enabled = p.get_bool("RocketFuel")
    ctx.rainbow_path = p.get_bool("RainbowMode")
    ctx.enforce_torque_control = p.get_bool("EnforceTorqueControl")
    ctx.custom_torque_params = p.get_bool("CustomTorqueParams")
    ctx.torque_override_enabled = p.get_bool("TorqueParamsOverrideEnabled")
    ctx.torque_override_friction = float(p.get("TorqueParamsOverrideFriction", return_default=True) or 0.0)
    ctx.torque_override_lat_accel_factor = float(p.get("TorqueParamsOverrideLatAccelFactor", return_default=True) or 0.0)
    ctx.lateral_jerk_torque = p.get_bool("LateralJerkTorqueController")
    ctx.disable_updates = p.get_bool("DisableUpdates")
    ctx.is_release_branch = p.get_bool("IsReleaseSpBranch")
    ctx.is_development_branch = p.get_bool("IsTestedBranch") or p.get_bool("IsDevelopmentBranch")
    ctx.is_sp_release = ctx.is_release_branch
    ctx.custom_model_active = p.get("ModelManager_ActiveBundle") is not None

    ctx.mads_limited = False
    ctx.tesla_has_vehicle_bus = False
    ctx.subaru_sng_available = True
    brand = ctx.brand
    if brand == "rivian":
      ctx.mads_limited = True
    elif brand == "tesla":
      try:
        from opendbc.sunnypilot.car.tesla.values import MadsScreenButtonType, TeslaFlagsSP
        if ctx.CP_SP is None or not (ctx.CP_SP.flags & TeslaFlagsSP.HAS_VEHICLE_BUS):
          ctx.mads_limited = True
        else:
          ctx.tesla_has_vehicle_bus = True
          screen_button = int(p.get("TeslaMadsScreenButton", return_default=True))
          ctx.mads_limited = screen_button == MadsScreenButtonType.OFF
      except Exception:
        pass
    elif brand == "subaru":
      try:
        from opendbc.car.subaru.values import CAR, SubaruFlags
        platform = ctx.platform
        if platform and platform in CAR:
          flags = CAR[platform].flags
          ctx.subaru_sng_available = bool(flags & (SubaruFlags.STOP_AND_GO | SubaruFlags.HYBRID))
      except Exception:
        pass

    sla_disallow_in_release = brand == "tesla" and ctx.is_sp_release
    sla_always_disallow = brand == "rivian"
    ctx.sla_available = (ctx.has_longitudinal_control or ctx.has_icbm) and not sla_disallow_in_release and not sla_always_disallow
    if ctx.CP is None or ctx.CP_SP is None:
      ctx.sla_available = False
  except Exception:
    pass

  return ctx
