"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import time

import openpilot.cereal.messaging as messaging
from openpilot.cereal import custom
from openpilot.common.constants import CV
from openpilot.common.gps import get_gps_location_service
from openpilot.common.params import Params
from openpilot.common.realtime import DT_MDL
from openpilot.sunnypilot import PARAMS_UPDATE_PERIOD, get_sanitize_int_param
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit import LIMIT_MAX_MAP_DATA_AGE, LIMIT_ADAPT_ACC
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.common import Policy, OffsetType

SpeedLimitSource = custom.LongitudinalPlanSP.SpeedLimit.Source

ALL_SOURCES = tuple(SpeedLimitSource.schema.enumerants.values())

# carrot reports its limits as kph integers over the phone link. Anything
# outside this range is a parse error or a stale/garbage packet, and clamping it
# would silently turn 400 into 250 and still be wrong — so it is rejected.
CARROT_LIMIT_MIN_KPH = 1
CARROT_LIMIT_MAX_KPH = 250


def _carrot_limit_ms(kph) -> float:
  """carrot limit (kph) → m/s, or 0.0 when it is not a plausible value."""
  try:
    value = int(kph)
  except (TypeError, ValueError):
    return 0.
  if CARROT_LIMIT_MIN_KPH <= value <= CARROT_LIMIT_MAX_KPH:
    return float(value) * CV.KPH_TO_MS
  return 0.


class SpeedLimitResolver:
  limit_solutions: dict[custom.LongitudinalPlanSP.SpeedLimit.Source, float]
  distance_solutions: dict[custom.LongitudinalPlanSP.SpeedLimit.Source, float]
  v_ego: float
  speed_limit: float
  speed_limit_last: float
  speed_limit_final: float
  speed_limit_final_last: float
  distance: float
  source: custom.LongitudinalPlanSP.SpeedLimit.Source
  speed_limit_offset: float

  def __init__(self):
    self.params = Params()
    self.frame = -1

    self._gps_location_service = get_gps_location_service(self.params)
    self.limit_solutions = {}  # Store for speed limit solutions from different sources
    self.distance_solutions = {}  # Store for distance to current speed limit start for different sources

    self.policy = self.params.get("SpeedLimitPolicy", return_default=True)
    self.policy = get_sanitize_int_param(
      "SpeedLimitPolicy",
      Policy.min().value,
      Policy.max().value,
      self.params
    )
    self._policy_to_sources_map = {
      Policy.car_state_only: [SpeedLimitSource.car],
      Policy.map_data_only: [SpeedLimitSource.map],
      Policy.car_state_priority: [SpeedLimitSource.car, SpeedLimitSource.map],
      Policy.map_data_priority: [SpeedLimitSource.map, SpeedLimitSource.car],
      Policy.combined: [SpeedLimitSource.car, SpeedLimitSource.map],
    }
    self.source = SpeedLimitSource.none
    for source in ALL_SOURCES:
      self._reset_limit_sources(source)

    self.is_metric = self.params.get_bool("IsMetric")
    self.offset_type = get_sanitize_int_param(
      "SpeedLimitOffsetType",
      OffsetType.min().value,
      OffsetType.max().value,
      self.params
    )
    self.offset_value = self.params.get("SpeedLimitValueOffset", return_default=True)

    # carrot phone-navigation limit: folded into the `map` source so it is both
    # displayed by the SLA widget and available to Speed Limit Assist. Opt-out
    # via CarrotNavCruiseSpeedEnabled; the actual speed control still requires
    # SpeedLimitMode == assist, so this alone never changes vehicle behaviour.
    self.use_carrot_limits = self.params.get_bool("CarrotNavCruiseSpeedEnabled")

    self.v_ego = 0.
    self.distance = 0.
    self.speed_limit = 0.
    self.speed_limit_last = 0.
    self.speed_limit_final = 0.
    self.speed_limit_final_last = 0.
    self.speed_limit_offset = 0.

  def update_speed_limit_states(self) -> None:
    self.speed_limit_final = self.speed_limit + self.speed_limit_offset

    if self.speed_limit > 0.:
      self.speed_limit_last = self.speed_limit
      self.speed_limit_final_last = self.speed_limit_final

  @property
  def speed_limit_valid(self) -> bool:
    return self.speed_limit > 0.

  @property
  def speed_limit_last_valid(self) -> bool:
    return self.speed_limit_last > 0.

  def update_params(self):
    if self.frame % int(PARAMS_UPDATE_PERIOD / DT_MDL) == 0:
      self.policy = self.params.get("SpeedLimitPolicy", return_default=True)
      self.is_metric = self.params.get_bool("IsMetric")
      self.offset_type = self.params.get("SpeedLimitOffsetType", return_default=True)
      self.offset_value = self.params.get("SpeedLimitValueOffset", return_default=True)
      self.use_carrot_limits = self.params.get_bool("CarrotNavCruiseSpeedEnabled")

  def _get_speed_limit_offset(self) -> float:
    if self.offset_type == OffsetType.off:
      return 0
    elif self.offset_type == OffsetType.fixed:
      return float(self.offset_value * (CV.KPH_TO_MS if self.is_metric else CV.MPH_TO_MS))
    elif self.offset_type == OffsetType.percentage:
      return float(self.offset_value * 0.01 * self.speed_limit)
    else:
      raise NotImplementedError("Offset not supported")

  def _reset_limit_sources(self, source: custom.LongitudinalPlanSP.SpeedLimit.Source) -> None:
    self.limit_solutions[source] = 0.
    self.distance_solutions[source] = 0.

  def _get_from_car_state(self, sm: messaging.SubMaster) -> None:
    self._reset_limit_sources(SpeedLimitSource.car)
    self.limit_solutions[SpeedLimitSource.car] = sm['carStateSP'].speedLimit
    self.distance_solutions[SpeedLimitSource.car] = 0.

  def _get_from_map_data(self, sm: messaging.SubMaster) -> None:
    self._reset_limit_sources(SpeedLimitSource.map)
    self._process_map_data(sm)
    self._merge_carrot_speed_limit(sm)

  def _merge_carrot_speed_limit(self, sm: messaging.SubMaster) -> None:
    """Fold the carrot phone-navigation limit into the `map` source.

    carrot receives two speed limits from the phone over carrotManSP:
      * ``nRoadLimitSpeed`` — the road-class limit of the road being driven
      * ``xSpdLimit``       — the SDI speed-camera limit (only meaningful while
                              ``xSpdDist`` > 0, i.e. the camera is ahead)

    carrot is a navigation/map provider and supplies its own phone GPS fix, so
    it is merged into the existing ``map`` source instead of adding a new
    enumerant to ``LongitudinalPlanSP.SpeedLimit.Source`` (which would change the
    cereal schema and invalidate route logs). The merged value can only *lower*
    the map solution, never raise it, so it stays conservative. Controlled by
    ``CarrotNavCruiseSpeedEnabled``.
    """
    if not self.use_carrot_limits:
      return
    try:
      if not sm.valid.get('carrotManSP'):
        return
      # Bail out if the packet is stale: SubMaster.recv_time is the wall clock
      # at which this service last received a packet.
      if time.monotonic() - sm.recv_time['carrotManSP'] > LIMIT_MAX_MAP_DATA_AGE:
        return
      carrot = sm['carrotManSP']
      if int(carrot.activeCarrot) <= 0:
        return

      road_limit_ms = _carrot_limit_ms(carrot.nRoadLimitSpeed)
      sdi_limit_ms = _carrot_limit_ms(carrot.xSpdLimit)
      sdi_dist = float(carrot.xSpdDist)

      # Start from the current map-data solution; the road-class limit takes
      # effect immediately. The SDI camera limit only takes effect once the
      # vehicle is close enough to start braking with LIMIT_ADAPT_ACC.
      limit_ms = 0.
      distance = 0.
      if road_limit_ms > 0.:
        limit_ms = road_limit_ms

      if sdi_limit_ms > 0. and sdi_dist > 0. and self.v_ego >= sdi_limit_ms:
        adapt_time = (sdi_limit_ms - self.v_ego) / LIMIT_ADAPT_ACC
        adapt_distance = self.v_ego * adapt_time + 0.5 * LIMIT_ADAPT_ACC * adapt_time ** 2
        if sdi_dist <= adapt_distance:
          # SDI is stricter; replace/lower the road-class limit.
          if limit_ms <= 0. or sdi_limit_ms < limit_ms:
            limit_ms = sdi_limit_ms
            distance = sdi_dist

      # If both limits are absent, do nothing.
      if limit_ms <= 0.:
        return

      # If a road-class limit is already active from map data, only allow carrot
      # to *lower* it. This prevents a navigation glitch from raising the limit
      # above what the car's own map source says.
      current = self.limit_solutions[SpeedLimitSource.map]
      if current > 0. and limit_ms >= current:
        return

      self.limit_solutions[SpeedLimitSource.map] = limit_ms
      self.distance_solutions[SpeedLimitSource.map] = distance
    except Exception:
      return

  def _process_map_data(self, sm: messaging.SubMaster) -> None:
    gps_data = sm[self._gps_location_service]
    map_data = sm['liveMapDataSP']

    gps_fix_age = time.monotonic() - gps_data.unixTimestampMillis * 1e-3
    if gps_fix_age > LIMIT_MAX_MAP_DATA_AGE:
      return

    speed_limit = map_data.speedLimit if map_data.speedLimitValid else 0.
    next_speed_limit = map_data.speedLimitAhead if map_data.speedLimitAheadValid else 0.

    self._calculate_map_data_limits(sm, speed_limit, next_speed_limit)

  def _calculate_map_data_limits(self, sm: messaging.SubMaster, speed_limit: float, next_speed_limit: float) -> None:
    gps_data = sm[self._gps_location_service]
    map_data = sm['liveMapDataSP']

    distance_since_fix = self.v_ego * (time.monotonic() - gps_data.unixTimestampMillis * 1e-3)
    distance_to_speed_limit_ahead = max(0., map_data.speedLimitAheadDistance - distance_since_fix)

    self.limit_solutions[SpeedLimitSource.map] = speed_limit
    self.distance_solutions[SpeedLimitSource.map] = 0.

    # FIXME-SP: this is not working as expected
    if 0. < next_speed_limit < self.v_ego:
      adapt_time = (next_speed_limit - self.v_ego) / LIMIT_ADAPT_ACC
      adapt_distance = self.v_ego * adapt_time + 0.5 * LIMIT_ADAPT_ACC * adapt_time ** 2

      if distance_to_speed_limit_ahead <= adapt_distance:
        self.limit_solutions[SpeedLimitSource.map] = next_speed_limit
        self.distance_solutions[SpeedLimitSource.map] = distance_to_speed_limit_ahead

  def _get_source_solution_according_to_policy(self) -> custom.LongitudinalPlanSP.SpeedLimit.Source:
    sources_for_policy = self._policy_to_sources_map[Policy(self.policy)]

    if Policy(self.policy) != Policy.combined:
      # They are ordered in the order of preference, so we pick the first that's non-zero
      for source in sources_for_policy:
        if self.limit_solutions[source] > 0.:
          return source
      return SpeedLimitSource.none

    sources_with_limits = [(s, limit) for s, limit in [(s, self.limit_solutions[s]) for s in sources_for_policy] if limit > 0.]
    if sources_with_limits:
      return min(sources_with_limits, key=lambda x: x[1])[0]

    return SpeedLimitSource.none

  def _resolve_limit_sources(self, sm: messaging.SubMaster) -> tuple[float, float, custom.LongitudinalPlanSP.SpeedLimit.Source]:
    """Get limit solutions from each data source"""
    self._get_from_car_state(sm)
    self._get_from_map_data(sm)

    source = self._get_source_solution_according_to_policy()
    speed_limit = self.limit_solutions[source] if source else 0.
    distance = self.distance_solutions[source] if source else 0.

    return speed_limit, distance, source

  def update(self, v_ego: float, sm: messaging.SubMaster) -> None:
    self.v_ego = v_ego
    self.update_params()

    self.speed_limit, self.distance, self.source = self._resolve_limit_sources(sm)
    self.speed_limit_offset = self._get_speed_limit_offset()

    self.update_speed_limit_states()

    self.frame += 1
