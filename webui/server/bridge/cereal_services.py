"""Cereal service lists aligned with sunnypilot native UI (ui_state.py + UIStateSP)."""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger("webui.cereal")

# Mirrors openpilot/selfdrive/ui/ui_state.py SubMaster list + sm_services_ext.
STATE_HUB_SERVICES: tuple[str, ...] = (
  "modelV2",
  "controlsState",
  "onroadEvents",
  "extrinsicsCalibration",
  "radarState",
  "deviceState",
  "pandaStates",
  "carParams",
  "driverMonitoringState",
  "carState",
  "driverStateV2",
  "narrowRoadCameraState",
  "wideRoadCameraState",
  "managerState",
  "selfdriveState",
  "longitudinalPlan",
  "gpsLocationExternal",
  "testJoystick",
  "rawAudioData",
  "carOutput",
  "carControl",
  "vehicleParameters",
  "lateralTorqueParameters",
  "lateralDelay",
  "modelManagerSP",
  "selfdriveStateSP",
  "longitudinalPlanSP",
  "backupManagerSP",
  "gpsLocation",
  "carStateSP",
  "liveMapDataSP",
  "carParamsSP",
)

OVERLAY_SERVICES: tuple[str, ...] = (
  "modelV2",
  "extrinsicsCalibration",
  "radarState",
  "deviceState",
  "narrowRoadCameraState",
  "wideRoadCameraState",
  "selfdriveState",
  "longitudinalPlan",
  "carParams",
  "carState",
)

_MINIMAL_SERVICES: tuple[str, ...] = (
  "deviceState",
  "selfdriveState",
  "carState",
  "controlsState",
  "pandaStates",
  "managerState",
)

# Legacy names from older openpilot / webui drafts.
_LEGACY_SERVICE_ALIASES: dict[str, str] = {
  "liveCalibration": "extrinsicsCalibration",
  "roadCameraState": "narrowRoadCameraState",
  "liveParameters": "vehicleParameters",
  "liveTorqueParameters": "lateralTorqueParameters",
  "liveDelay": "lateralDelay",
}


def normalize_service_name(name: str) -> str:
  return _LEGACY_SERVICE_ALIASES.get(name, name)


def filter_known_services(services: list[str]) -> list[str]:
  """Drop services missing from SERVICE_LIST; map legacy names to current fork."""
  try:
    from openpilot.cereal.services import SERVICE_LIST
    known = SERVICE_LIST
  except Exception:
    return list(dict.fromkeys(normalize_service_name(s) for s in services))

  out: list[str] = []
  seen: set[str] = set()
  dropped: list[str] = []
  for raw in services:
    svc = normalize_service_name(raw)
    if svc in known:
      if svc not in seen:
        out.append(svc)
        seen.add(svc)
    else:
      dropped.append(raw)
  if dropped:
    _log.debug("filtered unknown cereal services: %s", ", ".join(dropped))
  return out


def make_submaster(services: list[str], *, poll: str = "deviceState") -> Any:
  import openpilot.cereal.messaging as messaging

  filtered = filter_known_services(services)
  if poll not in filtered:
    filtered = [poll, *filtered]
  try:
    return messaging.SubMaster(filtered, poll=poll)
  except Exception:
    minimal = filter_known_services(list(_MINIMAL_SERVICES))
    return messaging.SubMaster(minimal, poll="deviceState")
