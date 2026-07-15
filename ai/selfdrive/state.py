"""
Read-only access to openpilot runtime state for the AI agent.

This module intentionally only exposes read-only snapshots. It never writes
Params or sends control commands.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any

from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog


try:
  from cereal import messaging
except ImportError:
  messaging = None  # type: ignore


@dataclass
class VehicleState:
  """Snapshot of vehicle/openpilot state used for safety checks and context."""

  # Motion / safety
  v_ego: float = 0.0
  a_ego: float = 0.0
  v_cruise: float = 0.0
  standstill: bool = False
  enabled: bool = False
  active: bool = False
  engageable: bool = False
  ignition: bool = False
  started: bool = False
  force_offroad: bool = False

  # Basic car info
  brand: str = ""
  car_fingerprint: str = ""
  car_vin: str = ""
  openpilot_longitudinal_control: bool = False
  pcm_cruise: bool = False
  dashcam_only: bool = False
  min_enable_speed: float = 0.0

  # Driver / chassis
  steering_angle_deg: float = 0.0
  steering_rate_deg: float = 0.0
  steering_pressed: bool = False
  steering_disengage: bool = False
  gas_pressed: bool = False
  brake_pressed: bool = False
  brake: float = 0.0
  gear_shifter: str = ""
  left_blinker: bool = False
  right_blinker: bool = False
  cruise_enabled: bool = False

  # Faults / stock ADAS
  can_valid: bool = True
  acc_faulted: bool = False
  steer_fault_temporary: bool = False
  steer_fault_permanent: bool = False
  invalid_lkas_setting: bool = False
  stock_lkas: bool = False
  esp_disabled: bool = False

  # Selfdrive UI / mode
  selfdrive_state: str = ""
  alert_text1: str = ""
  alert_text2: str = ""
  alert_status: str = ""
  alert_type: str = ""
  experimental_mode: bool = False

  # Device health (when deviceState available)
  thermal_status: str = ""
  max_temp_c: float = 0.0
  memory_usage_percent: int = 0
  free_space_percent: float = 0.0
  network_type: str = ""

  # Panda / safety
  controls_allowed: bool = False
  safety_model: str = ""

  # Recent events / faults
  onroad_events: list[dict[str, Any]] | None = None

  # True when cereal state could not be read; blocks write actions (fail-closed).
  reader_unavailable: bool = False

  @property
  def is_driving(self) -> bool:
    """True when the vehicle is likely in motion or under OP control."""
    if self.force_offroad:
      return False
    if self.enabled or self.active:
      return True
    if abs(self.v_ego) > 0.1:
      return True
    if self.started and self.ignition:
      return True
    return False

  def to_dict(self) -> dict[str, Any]:
    """Compact JSON-friendly snapshot for APIs and tools."""
    d = asdict(self)
    d["is_driving"] = self.is_driving
    d["vEgoKph"] = round(self.v_ego * 3.6, 1)
    d["vCruiseKph"] = round(self.v_cruise * 3.6, 1) if self.v_cruise else 0.0
    return d

  def summary_line(self) -> str:
    """Short natural-language line for LLM system context."""
    parts = [
      f"vEgo={self.v_ego:.2f} m/s ({self.v_ego * 3.6:.1f} km/h)",
      f"aEgo={self.a_ego:.2f} m/s²",
      f"standstill={self.standstill}",
      f"enabled={self.enabled}",
      f"active={self.active}",
      f"engageable={self.engageable}",
      f"started={self.started}",
      f"ignition={self.ignition}",
    ]
    if self.v_cruise > 0:
      parts.append(f"vCruise={self.v_cruise * 3.6:.1f} km/h")
    if self.cruise_enabled:
      parts.append("cruise=on")
    if self.brand or self.car_fingerprint:
      parts.append(f"vehicle={self.brand or '?'}:{self.car_fingerprint or '?'}")
    if self.gear_shifter:
      parts.append(f"gear={self.gear_shifter}")
    if self.left_blinker or self.right_blinker:
      blink = []
      if self.left_blinker:
        blink.append("L")
      if self.right_blinker:
        blink.append("R")
      parts.append(f"blinkers={''.join(blink)}")
    if self.steering_pressed:
      parts.append("steering_pressed=true")
    if self.brake_pressed:
      parts.append("brake_pressed=true")
    if self.gas_pressed:
      parts.append("gas_pressed=true")
    if self.selfdrive_state:
      parts.append(f"opState={self.selfdrive_state}")
    if self.experimental_mode:
      parts.append("experimental=true")
    if self.alert_text1:
      parts.append(f"alert={self.alert_text1}")
    if self.alert_text2:
      parts.append(f"alert2={self.alert_text2}")
    if not self.can_valid:
      parts.append("can_valid=false")
    if self.acc_faulted:
      parts.append("acc_faulted=true")
    if self.steer_fault_temporary:
      parts.append("steer_fault_temp=true")
    if self.steer_fault_permanent:
      parts.append("steer_fault_perm=true")
    if self.thermal_status:
      parts.append(f"thermal={self.thermal_status}")
    if self.max_temp_c > 0:
      parts.append(f"maxTempC={self.max_temp_c:.0f}")
    if self.memory_usage_percent:
      parts.append(f"mem={self.memory_usage_percent}%")
    if self.onroad_events:
      names = [e.get("name", "") for e in self.onroad_events if e.get("name")][:8]
      if names:
        parts.append(f"events={','.join(names)}")
    if self.reader_unavailable:
      parts.append("reader_unavailable=true")
    return "Current vehicle state: " + ", ".join(parts) + "."


def _safe_bool(obj: Any, attr: str, default: bool = False) -> bool:
  if obj is None:
    return default
  try:
    return bool(getattr(obj, attr, default))
  except Exception:
    return default


def _safe_float(obj: Any, attr: str, default: float = 0.0) -> float:
  if obj is None:
    return default
  try:
    return float(getattr(obj, attr, default))
  except Exception:
    return default


def _safe_int(obj: Any, attr: str, default: int = 0) -> int:
  if obj is None:
    return default
  try:
    return int(getattr(obj, attr, default))
  except Exception:
    return default


def _safe_str(obj: Any, attr: str, default: str = "") -> str:
  if obj is None:
    return default
  try:
    val = getattr(obj, attr, default)
    if val is None:
      return default
    if hasattr(val, "name"):
      return str(val.name)
    return str(val)
  except Exception:
    return default


def _parse_onroad_events(sm: Any, has_service: bool) -> list[dict[str, Any]]:
  events: list[dict[str, Any]] = []
  if not has_service:
    return events
  try:
    oe = sm["onroadEvents"]
    if not oe:
      return events
    for evt in oe:
      events.append({
        "name": _safe_str(evt, "name"),
        "no_entry": _safe_bool(evt, "noEntry"),
        "soft_disable": _safe_bool(evt, "softDisable"),
        "immediate_disable": _safe_bool(evt, "immediateDisable"),
        "permanent": _safe_bool(evt, "permanent"),
      })
  except Exception as e:
    cloudlog.warning(f"aid: failed to read onroadEvents: {e}")
  return events


class StateReader:
  """Lightweight wrapper around cereal SubMaster for the AI service."""

  _SERVICES = [
    "deviceState",
    "pandaStates",
    "carState",
    "controlsState",
    "carParams",
    "selfdriveState",
    "onroadEvents",
    "managerState",
  ]

  def __init__(self):
    self._params = Params()
    self._sm: Any = None
    self._healthy = False
    self._services: list[str] = []
    if messaging is None:
      cloudlog.error("aid: cereal.messaging not available")
      return
    try:
      self._sm = messaging.SubMaster(self._SERVICES)
      self._sm.update(1000)
      self._services = list(self._sm.sock.keys())
      self._healthy = True
    except Exception as e:
      cloudlog.error(f"aid: StateReader initialization failed: {e}")

  def update(self, timeout: int = 0) -> VehicleState:
    if not self._healthy or self._sm is None:
      return self._default_state()
    try:
      self._sm.update(timeout)
      return self.snapshot()
    except Exception as e:
      cloudlog.error(f"aid: StateReader update failed: {e}")
      return self._default_state()

  def _default_state(self) -> VehicleState:
    return VehicleState(
      force_offroad=self._params.get_bool("dp_dev_go_off_road"),
      reader_unavailable=not self._healthy,
    )

  def _has_service(self, name: str) -> bool:
    return self._sm is not None and name in self._services

  def snapshot(self) -> VehicleState:
    if self._sm is None:
      return self._default_state()

    try:
      sm = self._sm
      has = self._has_service

      ignition = False
      controls_allowed = False
      safety_model = ""
      if has("pandaStates"):
        try:
          ps = sm["pandaStates"]
          if ps and len(ps) > 0:
            ignition = any(
              _safe_bool(p, "ignitionLine") or _safe_bool(p, "ignitionCan")
              for p in ps
            )
            p0 = ps[0]
            controls_allowed = _safe_bool(p0, "controlsAllowed")
            safety_model = _safe_str(p0, "safetyModel")
        except Exception as e:
          cloudlog.warning(f"aid: failed to read pandaStates: {e}")

      started = False
      thermal_status = ""
      max_temp_c = 0.0
      memory_usage_percent = 0
      free_space_percent = 0.0
      network_type = ""
      if has("deviceState"):
        ds = sm["deviceState"]
        started = _safe_bool(ds, "started") and ignition
        thermal_status = _safe_str(ds, "thermalStatus")
        max_temp_c = _safe_float(ds, "maxTempC")
        memory_usage_percent = _safe_int(ds, "memoryUsagePercent")
        free_space_percent = _safe_float(ds, "freeSpacePercent")
        network_type = _safe_str(ds, "networkType")

      v_ego = 0.0
      a_ego = 0.0
      standstill = False
      v_cruise = 0.0
      steering_angle_deg = 0.0
      steering_rate_deg = 0.0
      steering_pressed = False
      steering_disengage = False
      gas_pressed = False
      brake_pressed = False
      brake = 0.0
      gear_shifter = ""
      left_blinker = False
      right_blinker = False
      cruise_enabled = False
      can_valid = True
      acc_faulted = False
      steer_fault_temporary = False
      steer_fault_permanent = False
      invalid_lkas_setting = False
      stock_lkas = False
      esp_disabled = False
      if has("carState"):
        cs = sm["carState"]
        v_ego = _safe_float(cs, "vEgo")
        a_ego = _safe_float(cs, "aEgo")
        standstill = _safe_bool(cs, "standstill")
        v_cruise = _safe_float(cs, "vCruise")
        steering_angle_deg = _safe_float(cs, "steeringAngleDeg")
        steering_rate_deg = _safe_float(cs, "steeringRateDeg")
        steering_pressed = _safe_bool(cs, "steeringPressed")
        steering_disengage = _safe_bool(cs, "steeringDisengage")
        gas_pressed = _safe_bool(cs, "gasPressed")
        brake_pressed = _safe_bool(cs, "brakePressed")
        brake = _safe_float(cs, "brake")
        gear_shifter = _safe_str(cs, "gearShifter")
        left_blinker = _safe_bool(cs, "leftBlinker")
        right_blinker = _safe_bool(cs, "rightBlinker")
        can_valid = _safe_bool(cs, "canValid", True)
        acc_faulted = _safe_bool(cs, "accFaulted")
        steer_fault_temporary = _safe_bool(cs, "steerFaultTemporary")
        steer_fault_permanent = _safe_bool(cs, "steerFaultPermanent")
        invalid_lkas_setting = _safe_bool(cs, "invalidLkasSetting")
        stock_lkas = _safe_bool(cs, "stockLkas")
        esp_disabled = _safe_bool(cs, "espDisabled")
        try:
          cruise = getattr(cs, "cruiseState", None)
          if cruise is not None:
            cruise_enabled = _safe_bool(cruise, "enabled")
            if not v_cruise:
              v_cruise = _safe_float(cruise, "speed")
        except Exception:
          pass

      enabled = False
      active = False
      engageable = False
      selfdrive_state = ""
      alert_text1 = ""
      alert_text2 = ""
      alert_status = ""
      alert_type = ""
      experimental_mode = False
      if has("selfdriveState"):
        ss = sm["selfdriveState"]
        enabled = _safe_bool(ss, "enabled")
        active = _safe_bool(ss, "active")
        engageable = _safe_bool(ss, "engageable")
        selfdrive_state = _safe_str(ss, "state")
        alert_text1 = _safe_str(ss, "alertText1")
        alert_text2 = _safe_str(ss, "alertText2")
        alert_status = _safe_str(ss, "alertStatus")
        alert_type = _safe_str(ss, "alertType")
        experimental_mode = _safe_bool(ss, "experimentalMode")
      elif has("controlsState"):
        enabled = _safe_bool(sm["controlsState"], "enabled")

      brand = ""
      car_fingerprint = ""
      car_vin = ""
      openpilot_longitudinal_control = False
      pcm_cruise = False
      dashcam_only = False
      min_enable_speed = 0.0
      if has("carParams"):
        cp = sm["carParams"]
        brand = _safe_str(cp, "brand")
        car_fingerprint = _safe_str(cp, "carFingerprint")
        car_vin = _safe_str(cp, "carVin")
        openpilot_longitudinal_control = _safe_bool(cp, "openpilotLongitudinalControl")
        pcm_cruise = _safe_bool(cp, "pcmCruise")
        dashcam_only = _safe_bool(cp, "dashcamOnly")
        min_enable_speed = _safe_float(cp, "minEnableSpeed")

      events = _parse_onroad_events(sm, has("onroadEvents"))
      force_offroad = self._params.get_bool("dp_dev_go_off_road")

      return VehicleState(
        v_ego=v_ego,
        a_ego=a_ego,
        v_cruise=v_cruise,
        standstill=standstill,
        enabled=enabled,
        active=active,
        engageable=engageable,
        ignition=ignition,
        started=started,
        force_offroad=force_offroad,
        brand=brand,
        car_fingerprint=car_fingerprint,
        car_vin=car_vin,
        openpilot_longitudinal_control=openpilot_longitudinal_control,
        pcm_cruise=pcm_cruise,
        dashcam_only=dashcam_only,
        min_enable_speed=min_enable_speed,
        steering_angle_deg=steering_angle_deg,
        steering_rate_deg=steering_rate_deg,
        steering_pressed=steering_pressed,
        steering_disengage=steering_disengage,
        gas_pressed=gas_pressed,
        brake_pressed=brake_pressed,
        brake=brake,
        gear_shifter=gear_shifter,
        left_blinker=left_blinker,
        right_blinker=right_blinker,
        cruise_enabled=cruise_enabled,
        can_valid=can_valid,
        acc_faulted=acc_faulted,
        steer_fault_temporary=steer_fault_temporary,
        steer_fault_permanent=steer_fault_permanent,
        invalid_lkas_setting=invalid_lkas_setting,
        stock_lkas=stock_lkas,
        esp_disabled=esp_disabled,
        selfdrive_state=selfdrive_state,
        alert_text1=alert_text1,
        alert_text2=alert_text2,
        alert_status=alert_status,
        alert_type=alert_type,
        experimental_mode=experimental_mode,
        thermal_status=thermal_status,
        max_temp_c=max_temp_c,
        memory_usage_percent=memory_usage_percent,
        free_space_percent=free_space_percent,
        network_type=network_type,
        controls_allowed=controls_allowed,
        safety_model=safety_model,
        onroad_events=events,
      )
    except Exception as e:
      cloudlog.error(f"aid: snapshot failed: {e}")
      return self._default_state()

  def latest(self) -> dict[str, Any]:
    """Return a JSON-friendly dict of the latest relevant state."""
    snap = self.snapshot()
    if not self._healthy or self._sm is None:
      return {
        "error": "StateReader not initialized",
        "timestamp": time.time(),
        "vehicle": snap.to_dict(),
      }

    try:
      sm = self._sm
      has = self._has_service
      data: dict[str, Any] = {
        "timestamp": time.time(),
        "driving": snap.is_driving,
        "vehicle": snap.to_dict(),
        "valid": {},
        "alive": {},
      }

      for s in self._services:
        try:
          data["valid"][s] = self._sm.valid[s]
          data["alive"][s] = self._sm.alive[s]
        except Exception:
          data["valid"][s] = False
          data["alive"][s] = False

      if has("carParams"):
        cp = sm["carParams"]
        if cp:
          data["carParams"] = {
            "brand": _safe_str(cp, "brand"),
            "carFingerprint": _safe_str(cp, "carFingerprint"),
            "carVin": _safe_str(cp, "carVin"),
            "openpilotLongitudinalControl": _safe_bool(cp, "openpilotLongitudinalControl"),
            "pcmCruise": _safe_bool(cp, "pcmCruise"),
            "dashcamOnly": _safe_bool(cp, "dashcamOnly"),
            "minEnableSpeed": round(_safe_float(cp, "minEnableSpeed"), 2),
            "minSteerSpeed": round(_safe_float(cp, "minSteerSpeed"), 2),
            "steerControlType": _safe_str(cp, "steerControlType"),
            "notCar": _safe_bool(cp, "notCar"),
            "alphaLongitudinalAvailable": _safe_bool(cp, "alphaLongitudinalAvailable"),
            "radarUnavailable": _safe_bool(cp, "radarUnavailable"),
          }

      if has("carState"):
        cs = sm["carState"]
        if cs:
          ws = getattr(cs, "wheelSpeeds", None)
          data["carState"] = {
            "vEgo": round(_safe_float(cs, "vEgo"), 3),
            "aEgo": round(_safe_float(cs, "aEgo"), 3),
            "vEgoRaw": round(_safe_float(cs, "vEgoRaw"), 3),
            "vEgoCluster": round(_safe_float(cs, "vEgoCluster"), 3),
            "vCruise": round(_safe_float(cs, "vCruise"), 3),
            "standstill": _safe_bool(cs, "standstill"),
            "yawRate": round(_safe_float(cs, "yawRate"), 4),
            "steeringAngleDeg": round(_safe_float(cs, "steeringAngleDeg"), 2),
            "steeringRateDeg": round(_safe_float(cs, "steeringRateDeg"), 2),
            "steeringTorque": round(_safe_float(cs, "steeringTorque"), 3),
            "steeringPressed": _safe_bool(cs, "steeringPressed"),
            "steeringDisengage": _safe_bool(cs, "steeringDisengage"),
            "gasPressed": _safe_bool(cs, "gasPressed"),
            "brakePressed": _safe_bool(cs, "brakePressed"),
            "brake": round(_safe_float(cs, "brake"), 3),
            "regenBraking": _safe_bool(cs, "regenBraking"),
            "gearShifter": _safe_str(cs, "gearShifter"),
            "leftBlinker": _safe_bool(cs, "leftBlinker"),
            "rightBlinker": _safe_bool(cs, "rightBlinker"),
            "doorOpen": _safe_bool(cs, "doorOpen"),
            "seatbeltUnlatched": _safe_bool(cs, "seatbeltUnlatched"),
            "canValid": _safe_bool(cs, "canValid"),
            "canTimeout": _safe_bool(cs, "canTimeout"),
            "accFaulted": _safe_bool(cs, "accFaulted"),
            "steerFaultTemporary": _safe_bool(cs, "steerFaultTemporary"),
            "steerFaultPermanent": _safe_bool(cs, "steerFaultPermanent"),
            "invalidLkasSetting": _safe_bool(cs, "invalidLkasSetting"),
            "stockLkas": _safe_bool(cs, "stockLkas"),
            "stockAeb": _safe_bool(cs, "stockAeb"),
            "espDisabled": _safe_bool(cs, "espDisabled"),
            "vehicleSensorsInvalid": _safe_bool(cs, "vehicleSensorsInvalid"),
            "wheelSpeeds": {
              "fl": round(_safe_float(ws, "fl"), 3),
              "fr": round(_safe_float(ws, "fr"), 3),
              "rl": round(_safe_float(ws, "rl"), 3),
              "rr": round(_safe_float(ws, "rr"), 3),
            } if ws is not None else None,
          }
          cruise = getattr(cs, "cruiseState", None)
          if cruise is not None:
            data["carState"]["cruiseState"] = {
              "enabled": _safe_bool(cruise, "enabled"),
              "speed": round(_safe_float(cruise, "speed"), 3),
              "available": _safe_bool(cruise, "available"),
              "standstill": _safe_bool(cruise, "standstill"),
            }

      if has("selfdriveState"):
        ss = sm["selfdriveState"]
        if ss:
          data["selfdriveState"] = {
            "state": _safe_str(ss, "state"),
            "enabled": _safe_bool(ss, "enabled"),
            "active": _safe_bool(ss, "active"),
            "engageable": _safe_bool(ss, "engageable"),
            "alertText1": _safe_str(ss, "alertText1"),
            "alertText2": _safe_str(ss, "alertText2"),
            "alertStatus": _safe_str(ss, "alertStatus"),
            "alertType": _safe_str(ss, "alertType"),
            "experimentalMode": _safe_bool(ss, "experimentalMode"),
            "personality": _safe_str(ss, "personality"),
          }

      if has("controlsState"):
        ctrl = sm["controlsState"]
        if ctrl:
          data["controlsState"] = {
            "enabled": _safe_bool(ctrl, "enabled"),
            "longControlState": _safe_str(ctrl, "longControlState"),
            "curvature": round(_safe_float(ctrl, "curvature"), 5),
            "desiredCurvature": round(_safe_float(ctrl, "desiredCurvature"), 5),
            "forceDecel": _safe_bool(ctrl, "forceDecel"),
          }

      if has("deviceState"):
        ds = sm["deviceState"]
        if ds:
          cpu_temps = list(getattr(ds, "cpuTempC", []) or [])
          data["deviceState"] = {
            "started": _safe_bool(ds, "started"),
            "thermalStatus": _safe_str(ds, "thermalStatus"),
            "maxTempC": round(_safe_float(ds, "maxTempC"), 1),
            "cpuTempC": [round(float(t), 1) for t in cpu_temps[:4]],
            "memoryUsagePercent": _safe_int(ds, "memoryUsagePercent"),
            "freeSpacePercent": round(_safe_float(ds, "freeSpacePercent"), 1),
            "networkType": _safe_str(ds, "networkType"),
            "networkStrength": _safe_str(ds, "networkStrength"),
            "powerDrawW": round(_safe_float(ds, "powerDrawW"), 1),
          }

      if has("pandaStates"):
        try:
          ps = sm["pandaStates"]
          data["pandaStates"] = []
          if ps:
            for p in ps:
              data["pandaStates"].append({
                "ignitionLine": _safe_bool(p, "ignitionLine"),
                "ignitionCan": _safe_bool(p, "ignitionCan"),
                "controlsAllowed": _safe_bool(p, "controlsAllowed"),
                "safetyModel": _safe_str(p, "safetyModel"),
                "faultStatus": _safe_str(p, "faultStatus"),
                "heartbeatLost": _safe_bool(p, "heartbeatLost"),
                "voltage": _safe_int(p, "voltage"),
              })
        except Exception as e:
          cloudlog.warning(f"aid: latest failed to read pandaStates: {e}")

      if has("managerState"):
        try:
          ms = sm["managerState"]
          procs = getattr(ms, "processes", None) or []
          data["processes"] = [
            {
              "name": _safe_str(p, "name"),
              "running": _safe_bool(p, "running"),
              "shouldBeRunning": _safe_bool(p, "shouldBeRunning"),
              "pid": _safe_int(p, "pid"),
            }
            for p in procs
            if _safe_str(p, "name")
          ]
        except Exception as e:
          cloudlog.warning(f"aid: latest failed to read managerState: {e}")

      data["onroadEvents"] = snap.onroad_events or []
      return data
    except Exception as e:
      cloudlog.error(f"aid: latest failed: {e}")
      return {
        "error": f"StateReader failed: {e}",
        "timestamp": time.time(),
        "vehicle": snap.to_dict(),
      }
