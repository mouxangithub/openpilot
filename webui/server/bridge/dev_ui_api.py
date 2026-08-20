"""Developer UI snapshot for web HUD (mirrors developer_ui/elements.py)."""

from __future__ import annotations

from typing import Any

from openpilot.common.constants import CV


def _color_hex(r: int, g: int, b: int) -> str:
  return f"#{r:02x}{g:02x}{b:02x}"


def _lead_dist_color(d_rel: float) -> str:
  if d_rel < 5:
    return "#ff0000"
  if d_rel < 15:
    return "#ffbc00"
  return "#ffffff"


def _lead_speed_color(v_rel: float) -> str:
  if v_rel < -4.4704:
    return "#ff0000"
  if v_rel < 0:
    return "#ffbc00"
  return "#ffffff"


def _lat_color(lat_active: bool, steer_override: bool, angle_deg: float = 0.0, check_angle: bool = False) -> str:
  color = "#ffffff"
  if lat_active:
    color = "#919b95" if steer_override else "#00ff00"

  if check_angle:
    if abs(angle_deg) > 180:
      return "#ff0000"
    if abs(angle_deg) > 90:
      return "#ffbc00"
  return color


def _desired_steer_color(lat_active: bool, angle_deg: float) -> str:
  if not lat_active:
    return "#ffffff"
  if abs(angle_deg) > 180:
    return "#ff0000"
  if abs(angle_deg) > 90:
    return "#ffbc00"
  return "#00ff00"


def _gps_data(sm: Any):
  if sm.valid.get("gpsLocationExternal"):
    return sm["gpsLocationExternal"], True
  if sm.valid.get("gpsLocation"):
    return sm["gpsLocation"], True
  return None, False


def _bearing_value(gps_data) -> str:
  bearing_accuracy_deg = float(getattr(gps_data, "bearingAccuracyDeg", 180.0))
  bearing_deg = float(getattr(gps_data, "bearingDeg", 0.0))
  if bearing_accuracy_deg == 180.0:
    return "OFF | -"

  if (337.5 <= bearing_deg <= 360) or (0 <= bearing_deg <= 22.5):
    dir_value = "N"
  elif 22.5 < bearing_deg < 67.5:
    dir_value = "NE"
  elif 67.5 <= bearing_deg <= 112.5:
    dir_value = "E"
  elif 112.5 < bearing_deg < 157.5:
    dir_value = "SE"
  elif 157.5 <= bearing_deg <= 202.5:
    dir_value = "S"
  elif 202.5 < bearing_deg < 247.5:
    dir_value = "SW"
  elif 247.5 <= bearing_deg <= 292.5:
    dir_value = "W"
  else:
    dir_value = "NW"
  return f"{dir_value} | {bearing_deg:.0f}°"


def snapshot_dev_ui(sm: Any, is_metric: bool) -> dict[str, Any] | None:
  from webui.server.bridge.car_context import get_car_context

  car_ctx = get_car_context()
  try:
    mode = int(car_ctx.developer_ui or 0)
  except Exception:
    return None

  if mode == 0:
    return None

  try:
    if sm.recv_frame["carState"] < int(car_ctx.started_frame or 0):
      return None
  except Exception:
    pass

  cs = sm["carState"]
  ctrl = sm["controlsState"]
  cc = sm["carControl"]
  conv = CV.MS_TO_KPH if is_metric else CV.MS_TO_MPH
  speed_unit = "km/h" if is_metric else "mph"
  accel_unit = "m/s^2"

  lead = sm["radarState"].leadOne if sm.valid.get("radarState") else None
  lead_present = bool(lead and lead.present)
  lead_d = float(lead.dRel) if lead_present else 0.0
  lead_v = float(lead.vRel) if lead_present else 0.0
  v_ego = float(cs.vEgo)

  lat_active = bool(cc.latActive)
  steer_override = bool(cs.steeringPressed)
  angle_steers = float(cs.steeringAngleDeg)
  roll = float(sm["vehicleParameters"].roll) if sm.valid.get("vehicleParameters") else 0.0
  curvature = float(ctrl.curvature)
  actual_la = (curvature * v_ego ** 2) - (roll * 9.81)

  right: list[dict[str, str]] = [
    {
      "label": "REL DIST",
      "value": f"{lead_d:.0f}" if lead_present else "-",
      "unit": "m",
      "color": _lead_dist_color(lead_d) if lead_present else "#ffffff",
    },
    {
      "label": "REL SPEED",
      "value": f"{lead_v * conv:.0f}" if lead_present else "-",
      "unit": speed_unit,
      "color": _lead_speed_color(lead_v) if lead_present else "#ffffff",
    },
    {
      "label": "REAL STEER",
      "value": f"{angle_steers:.1f}°",
      "unit": "",
      "color": _lat_color(lat_active, steer_override, angle_steers, check_angle=True),
    },
  ]

  lat_which = ""
  try:
    lat_which = ctrl.lateralControlState.which()
  except Exception:
    pass

  if lat_which == "torqueState":
    desired_curv = float(ctrl.desiredCurvature)
    desired_la = (desired_curv * v_ego ** 2) - (roll * 9.81)
    right.insert(3, {
      "label": "DESIRED L.A.",
      "value": f"{desired_la:.2f}" if lat_active else "-",
      "unit": accel_unit,
      "color": _lat_color(lat_active, steer_override),
    })
  elif lat_which == "angleState":
    steer_desired = float(ctrl.lateralControlState.angleState.steeringAngleDeg)
    right.insert(3, {
      "label": "DESIRED STEER",
      "value": f"{steer_desired:.1f}°" if lat_active else "-",
      "unit": "",
      "color": _desired_steer_color(lat_active, angle_steers),
    })
  elif lat_which == "pidState":
    steer_desired = float(ctrl.lateralControlState.pidState.steeringAngleDesiredDeg)
    right.insert(3, {
      "label": "DESIRED STEER",
      "value": f"{steer_desired:.1f}°" if lat_active else "-",
      "unit": "",
      "color": _desired_steer_color(lat_active, angle_steers),
    })

  right.append({
    "label": "ACTUAL L.A.",
    "value": f"{actual_la:.2f}",
    "unit": accel_unit,
    "color": _lat_color(lat_active, steer_override),
  })

  bottom: list[dict[str, str]] = [
    {
      "label": "ACC.",
      "value": f"{float(cs.aEgo):.1f}",
      "unit": accel_unit,
      "color": "#ffffff",
    },
    {
      "label": "L.S.",
      "value": f"{(lead_v + v_ego) * conv:.0f}" if lead_present else "-",
      "unit": speed_unit,
      "color": _lead_speed_color(lead_v) if lead_present else "#ffffff",
    },
  ]

  if lat_which == "torqueState":
    override_active = (
      car_ctx.enforce_torque_control
      and car_ctx.custom_torque_params
      and car_ctx.torque_override_enabled
    )
    if sm.valid.get("lateralTorqueParameters") or override_active:
      if override_active:
        fric_val = f"{car_ctx.torque_override_friction:.3f}"
        laf_val = f"{car_ctx.torque_override_lat_accel_factor:.3f}"
        fric_color = "#ffffff"
        laf_color = "#ffffff"
      else:
        ltp = sm["lateralTorqueParameters"]
        fric_val = f"{ltp.frictionCoefficientFiltered:.3f}"
        laf_val = f"{ltp.latAccelFactorFiltered:.3f}"
        live_valid = bool(getattr(ltp, "valid", getattr(ltp, "liveValid", False)))
        fric_color = "#00ff00" if live_valid else "#ffffff"
        laf_color = fric_color
      bottom.extend([
        {
          "label": "FRIC.",
          "value": fric_val,
          "unit": "",
          "color": fric_color,
        },
        {
          "label": "L.A.F.",
          "value": laf_val,
          "unit": "",
          "color": laf_color,
        },
      ])
  else:
    bottom.append({
      "label": "E.T.",
      "value": f"{abs(float(cs.steeringTorqueEps)):.1f}",
      "unit": "N·dm",
      "color": "#ffffff",
    })
    gps_data, gps_valid = _gps_data(sm)
    if gps_valid:
      bottom.append({
        "label": "B.D.",
        "value": _bearing_value(gps_data),
        "unit": "",
        "color": "#ffffff",
      })

  gps_data, gps_valid = _gps_data(sm)
  if gps_valid:
    altitude = float(getattr(gps_data, "altitude", 0.0))
    if sm.valid.get("gpsLocationExternal"):
      gps_accuracy = float(getattr(gps_data, "horizontalAccuracy", 0.0))
    else:
      gps_accuracy = 1.0
    bottom.append({
      "label": "ALT.",
      "value": f"{altitude:.1f}" if gps_accuracy != 0.0 else "-",
      "unit": "m",
      "color": "#ffffff",
    })

  return {"mode": mode, "bottom": bottom, "right": right}
