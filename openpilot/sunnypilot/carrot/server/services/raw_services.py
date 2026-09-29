"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Which cereal services the raw relay will stream, and under which names.

This is where "unified through sunnypilot" has to be spelled out. The companion app asks
for CarrotPilot's names - it requests `carState,modelV2,selfdriveState,carrotMan` - but
this fork publishes fork-only payloads under its own names, and `carrotMan` does not exist
here at all. The app also decodes the payload with CarrotPilot's capnp layout, so the two
must line up field for field.

They do, because `CarrotManSP` is a strict superset of CarrotPilot's `CarrotMan`: every
one of its 33 fields is present with the same ordinal, and the 42 fork-only fields are
appended after them (verified against both schemas on 2026-09-27). So the mapping below is
a rename at the edge only - the bytes on the wire stay the fork's own, and nothing has to
be transcribed or duplicated.

A whitelist, not a passthrough: the client picks the names, so streaming anything it names
would hand out every service in the system.
"""

# CarrotPilot name (what clients send) -> sunnypilot service name (what cereal has).
RAW_SERVICE_ALIASES = {
  "carrotMan": "carrotManSP",
  "carrotNavi": "carrotNaviSP",
  "carrotNaviState": "carrotNaviStateSP",
  "carrotNaviMedia": "carrotNaviMediaSP",
  "navInstructionCarrot": "navInstructionCarrotSP",
  "onroadEvents": "onroadEventsSP",
  "roadCameraState": "narrowRoadCameraState",
  "qRoadCameraState": "qRoadCameraState",
  "driverCameraState": "cabinCameraState",
}

# Stock openpilot service names, identical in both forks.
_RAW_STOCK_SERVICES = (
  "selfdriveState",
  "carState",
  "carStateSP",
  "carControl",
  "carControlSP",
  "controlsState",
  "longitudinalPlan",
  "longitudinalPlanSP",
  "liveCalibration",
  "modelV2",
  "drivingModelData",
  "deviceState",
  "managerState",
  "peripheralState",
  "radarState",
  "gpsLocationExternal",
  "cameraOdometry",
  "driverMonitoringState",
  "wideRoadCameraState",
  "narrowRoadCameraState",
  "liveParameters",
  "liveDelay",
  "liveTorqueParameters",
  "liveTracks",
  "livePose",
)

RAW_CORE_SERVICES: tuple = (
  "selfdriveState",
  "carState",
  "controlsState",
  "longitudinalPlan",
  "liveCalibration",
  "modelV2",
  "narrowRoadCameraState",
  "deviceState",
)

RAW_OPTIONAL_SERVICES: tuple = tuple(
  name for name in (*_RAW_STOCK_SERVICES, *RAW_SERVICE_ALIASES)
  if name not in RAW_CORE_SERVICES
)

# Every name a client is allowed to put in `?services=`. Both spellings are accepted - the
# CarrotPilot name and this fork's own - so a client written against either works, and the
# fork names are listed explicitly rather than implied by the alias values.
SUPPORTED_RAW_SERVICES: frozenset = frozenset(
  (*_RAW_STOCK_SERVICES, *RAW_SERVICE_ALIASES, *RAW_SERVICE_ALIASES.values())
)


def raw_services() -> tuple:
  return tuple(sorted(SUPPORTED_RAW_SERVICES))


def is_supported_raw_service(service: str) -> bool:
  return service in SUPPORTED_RAW_SERVICES


def resolve_service(service: str) -> str | None:
  """Map a client-supplied name to the service this fork actually publishes.

  Returns None when the name is not on the whitelist. A name that is already a
  sunnypilot name is passed through unchanged, so `carrotManSP` works too.
  """
  if service in RAW_SERVICE_ALIASES:
    return RAW_SERVICE_ALIASES[service]
  if service in SUPPORTED_RAW_SERVICES:
    return service
  return None


def resolve_services(names) -> list:
  """Resolve a client request into [(client_name, device_service)], dropping unknown names.

  The client name is echoed back in the hello and used as the frame prefix, so the app
  keeps seeing the name it asked for; only the device side ever sees the fork's own name.
  """
  resolved, seen = [], set()
  for name in names:
    name = (name or "").strip()
    if not name or name in seen:
      continue
    device_service = resolve_service(name)
    if device_service is None:
      continue
    seen.add(name)
    resolved.append((name, device_service))
  return resolved
