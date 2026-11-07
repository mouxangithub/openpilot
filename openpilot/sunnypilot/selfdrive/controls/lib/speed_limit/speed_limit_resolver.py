"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import datetime
import platform
import time

import openpilot.cereal.messaging as messaging
from openpilot.cereal import custom
from openpilot.common.constants import CV
from openpilot.common.gps import get_gps_location_service
from openpilot.common.params import Params
from openpilot.common.realtime import DT_MDL
from openpilot.common.swaglog import cloudlog
from openpilot.common.time_helpers import system_time_valid
from openpilot.sunnypilot import PARAMS_UPDATE_PERIOD, get_sanitize_int_param
from openpilot.sunnypilot.common.param_read import read_bool, read_float
from openpilot.sunnypilot.selfdrive.controls.lib.smart_cruise_control.limits import COMMIT_FRAC, OP_LONG_COAST_A, get_planning_limits
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit import LIMIT_MAX_MAP_DATA_AGE, LIMIT_ADAPT_ACC, V_CRUISE_UNSET
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.common import Policy, OffsetType
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.mapbox_speed_limit import MapboxSpeedLimit
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.tiered_offset import (
  TIER_KEY_SUFFIXES,
  tiered_offset_ms,
)
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.vision_limit import (
  merge_lower_limit,
  resolve_vision_limit,
)

SpeedLimitSource = custom.LongitudinalPlanSP.SpeedLimit.Source

ALL_SOURCES = tuple(SpeedLimitSource.schema.enumerants.values())

# carrot reports its limits as kph integers over the phone link. Anything
# outside this range is a parse error or a stale/garbage packet, and clamping it
# would silently turn 400 into 250 and still be wrong — so it is rejected.
CARROT_LIMIT_MIN_KPH = 1
CARROT_LIMIT_MAX_KPH = 250

# Speed limit change announcement (SpeedLimitChangedAlert param, default off): the jump the
# limit must cross before it counts as a change, how long the new value must hold steady
# before the alert fires, and how much the "steady" value may wobble while it holds.
SPEED_LIMIT_CHANGED_ALERT_MIN_DELTA_KPH = 5.  # kph
SPEED_LIMIT_CHANGED_ALERT_HOLD_S = 2.         # s
SPEED_LIMIT_CHANGED_ALERT_STABLE_KPH = 1.     # kph


class SpeedLimitChangedAlertTracker:
  """Detects a sustained jump of the resolver's speedLimitLast.

  Ported from StarPilot's slc limit-change announcement (starpilot_events): when the last
  valid speed limit moves by at least SPEED_LIMIT_CHANGED_ALERT_MIN_DELTA_KPH and the new
  value holds steady for SPEED_LIMIT_CHANGED_ALERT_HOLD_S, update() returns True exactly
  once. The hold-time debounce rides out flaky sources - a map handoff, a one-frame vision
  flicker, a carrot reconnect - which either snap back inside the hold window or keep
  moving, both of which reset the timer without alerting.

  The announced baseline only follows values that stay within the jump threshold of it, so
  a slow re-grade (50 -> 52 -> 54 km/h) never chimes; only a genuine sign change does.
  """

  def __init__(self):
    self._announced = 0.  # m/s, the limit the driver has already been living with
    self._candidate = 0.  # m/s, the new limit waiting out its hold time
    self._timer = 0.      # s, how long the candidate has held steady

  def reset(self) -> None:
    self._announced = 0.
    self._candidate = 0.
    self._timer = 0.

  def update(self, speed_limit_last: float, dt: float) -> bool:
    """Feed one frame of speedLimitLast (m/s); True exactly once per confirmed change."""
    if speed_limit_last <= 0.:
      # no limit: nothing to announce and nothing to compare against
      self.reset()
      return False

    if self._announced <= 0.:
      # first limit after a reset (plannerd start, or the first sign of a session):
      # seed the baseline without alerting
      self._announced = speed_limit_last
      self._candidate = 0.
      self._timer = 0.
      return False

    if abs(speed_limit_last - self._announced) * CV.MS_TO_KPH < SPEED_LIMIT_CHANGED_ALERT_MIN_DELTA_KPH:
      # back on (or drifting within the threshold of) the announced value: re-arm
      self._announced = speed_limit_last
      self._candidate = 0.
      self._timer = 0.
      return False

    if self._candidate > 0. and abs(speed_limit_last - self._candidate) * CV.MS_TO_KPH < SPEED_LIMIT_CHANGED_ALERT_STABLE_KPH:
      self._timer += dt
    else:
      # a new (or still-moving) value: restart the hold timer on it
      self._candidate = speed_limit_last
      self._timer = 0.

    if self._timer >= SPEED_LIMIT_CHANGED_ALERT_HOLD_S:
      self._announced = self._candidate
      self._candidate = 0.
      self._timer = 0.
      return True
    return False


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

  def __init__(self, CP=None):
    self.params = Params()
    self.frame = -1
    # swap to the upcoming lower limit once we are inside the braking distance the
    # platform can actually deliver (openpilot long coasts to it); the fixed LIMIT_ADAPT_ACC remains the no-CP fallback
    if CP is None:
      self._adapt_acc = LIMIT_ADAPT_ACC
    else:
      a_budget = OP_LONG_COAST_A if CP.openpilotLongitudinalControl else get_planning_limits(CP).a_budget
      self._adapt_acc = -COMMIT_FRAC * a_budget

    self._gps_location_service = get_gps_location_service(self.params)
    # The vision limit daemon publishes to the shared-memory params, so the
    # resolver reads them from there rather than from a message.
    self.mem_params = Params("/dev/shm/params") if platform.system() != "Darwin" else self.params
    self.use_vision_limits = read_bool(self.params, "VisionSpeedLimitEnabled")
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
    # Tiered offsets: one value per posted-limit band, read once here and
    # refreshed with the other params. The tiers only apply when the offset
    # type is `tiered`; the single value above stays in charge otherwise.
    self.tier_offsets = self._read_tier_offsets()

    # carrot phone-navigation limit: folded into the `map` source so it is both
    # displayed by the SLA widget and available to Speed Limit Assist. Opt-out
    # via CarrotNavCruiseSpeedEnabled; the actual speed control still requires
    # SpeedLimitMode == assist, so this alone never changes vehicle behaviour.
    self.use_carrot_limits = self.params.get_bool("CarrotNavCruiseSpeedEnabled")
    self._carrot_merge_warned = False  # one-shot: avoid a log flood every frame

    # Mapbox Driving-Match filler: when every configured source comes up empty
    # (no offline map section, carrot offline, no vision reading) a Mapbox
    # lookup around the GPS fix fills the gap. Requests are async, so the
    # plannerd loop is never blocked. The retrieved limit is folded into the
    # `map` source for the same reason as the carrot and vision limits: adding
    # an enumerant to ``LongitudinalPlanSP.SpeedLimit.Source`` would change the
    # cereal schema and invalidate every recorded route. Opt-out via
    # SLCMapboxFiller; the actual speed control still requires
    # SpeedLimitMode == assist, so this alone never changes vehicle behaviour.
    self.use_mapbox_filler = read_bool(self.params, "SLCMapboxFiller")
    self.mapbox = MapboxSpeedLimit(self.params)
    self._mapbox_warned = False  # one-shot: avoid a log flood every frame

    # PreviousSpeedLimit: the last valid limit, persisted so the sign survives
    # a reboot (the UI falls back to it while the resolver has no
    # speedLimitLast yet). Written only when the value changes to keep the
    # 10 Hz loop from hammering the params store.
    self._last_written_previous_limit = 0.
    self._previous_limit_write_warned = False  # one-shot: avoid a log flood every frame

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
      self._persist_previous_speed_limit()

  def _persist_previous_speed_limit(self) -> None:
    """Persist the last valid limit into PreviousSpeedLimit (m/s).

    Only written when the value actually changes: this runs at plannerd rate,
    and the params store does not need a write every frame for a value that
    just moved once per sign.
    """
    if abs(self.speed_limit_last - self._last_written_previous_limit) < 0.01:
      return
    try:
      self.params.put_float("PreviousSpeedLimit", float(self.speed_limit_last))
      self._last_written_previous_limit = self.speed_limit_last
    except Exception as e:
      # A libparams build without the key registered must not kill plannerd;
      # the feature degrades to "no sign after reboot".
      if not self._previous_limit_write_warned:
        self._previous_limit_write_warned = True
        cloudlog.warning(f"speed_limit_resolver: PreviousSpeedLimit write failed: {type(e).__name__}: {e}")

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
      self.use_mapbox_filler = read_bool(self.params, "SLCMapboxFiller")
      self.tier_offsets = self._read_tier_offsets()

  def _read_tier_offsets(self) -> list[float]:
    """The per-band offset values, in the unit the user picked.

    A tier whose parameter is missing reads as 0, so a partially configured
    set of tiers degrades to "no offset on the missing bands" rather than
    failing the whole feature.
    """
    values = []
    for key in TIER_KEY_SUFFIXES:
      values.append(float(self.params.get(key, return_default=True)))
    return values

  def _get_speed_limit_offset(self) -> float:
    if self.offset_type == OffsetType.off:
      return 0
    elif self.offset_type == OffsetType.fixed:
      return float(self.offset_value * (CV.KPH_TO_MS if self.is_metric else CV.MPH_TO_MS))
    elif self.offset_type == OffsetType.percentage:
      return float(self.offset_value * 0.01 * self.speed_limit)
    elif self.offset_type == OffsetType.tiered:
      return self._get_tiered_offset()
    else:
      raise NotImplementedError("Offset not supported")

  def _get_tiered_offset(self) -> float:
    """The offset for the band the current posted limit falls into.

    The band is chosen from the posted limit, not from the current speed: a
    60 km/h sign is the 60 band whether the car is doing 40 or 70 in it.
    """
    return tiered_offset_ms(self.speed_limit, self.tier_offsets, self.is_metric)

  def _reset_limit_sources(self, source: custom.LongitudinalPlanSP.SpeedLimit.Source) -> None:
    self.limit_solutions[source] = 0.
    self.distance_solutions[source] = 0.

  def _get_from_car_state(self, sm: messaging.SubMaster) -> None:
    self._reset_limit_sources(SpeedLimitSource.car)
    self.limit_solutions[SpeedLimitSource.car] = sm['carStateSP'].speedLimit
    self.distance_solutions[SpeedLimitSource.car] = 0.

  def _vision_limit(self, sm: messaging.SubMaster) -> float:
    """The speed limit the vision daemon currently sees, in m/s.

    Zero when the feature is off or the daemon has no reading. The daemon
    publishes to the shared-memory params, which is where the vision
    pipeline already writes, so no new message and no cereal change is
    needed.

    The decision rules live in vision_limit.py, which is plain logic and
    unit tested on its own.
    """
    if not self.use_vision_limits:
      return 0.0

    try:
      raw_limit = self.mem_params.get_float("VisionSpeedLimit")
    except Exception:
      return 0.0

    support_count = 0
    support_speed = 0.0
    try:
      support_count = self.mem_params.get_int("VisionSpeedLimitSupportCount")
      support_speed = self.mem_params.get_float("VisionSpeedLimitSupportSpeed")
    except Exception:
      pass

    return resolve_vision_limit(
      raw_limit,
      self._vision_reference_speed(sm),
      bool(sm['carState'].standstill),
      support_count=support_count,
      support_speed=support_speed,
      low_limit_filter=read_bool(self.params, "VisionSpeedLimitLowLimitFilter"),
      low_limit_threshold=read_float(self.params, "VisionSpeedLimitLowLimitThreshold"),
    )

  def _vision_reference_speed(self, sm: messaging.SubMaster) -> float:
    """The speed a vision limit is compared against.

    The set speed when there is one, otherwise the current speed. A car
    driving at its set speed with a sign far away from it is the usual
    case; at standstill there is nothing to compare against, which is why
    the caller skips the check there.
    """
    try:
      set_speed_kph = float(sm['carState'].vCruise)
    except Exception:
      set_speed_kph = 0.0

    if 0.0 < set_speed_kph < V_CRUISE_UNSET:
      return set_speed_kph * CV.KPH_TO_MS
    return max(float(self.v_ego), 0.0)

  def _merge_vision_speed_limit(self, sm: messaging.SubMaster) -> None:
    """Fold the vision limit into the `map` source.

    The vision pipeline is a separate detection source, but adding an
    enumerant to ``LongitudinalPlanSP.SpeedLimit.Source`` would change the
    cereal schema and invalidate every recorded route. The carrot limit is
    folded into `map` for the same reason.

    The merged value can only *lower* the map solution, never raise it, so
    the map limit stays authoritative and the vision limit acts as an extra
    brake.
    """
    vision_limit = self._vision_limit(sm)
    if vision_limit <= 0.0:
      return

    current = self.limit_solutions.get(SpeedLimitSource.map, 0.0)
    merged = merge_lower_limit(current, vision_limit)
    if merged != current:
      self.limit_solutions[SpeedLimitSource.map] = merged
      self.distance_solutions[SpeedLimitSource.map] = 0.0

  def _mapbox_fill(self, sm: messaging.SubMaster) -> None:
    """Fill an empty solution with a Mapbox Driving-Match lookup, folded into the `map` source.

    The filler is a navigation/map provider in the same sense as carrot and the
    offline map, so it is merged into the existing ``map`` source instead of
    adding a new enumerant to ``LongitudinalPlanSP.SpeedLimit.Source`` (which
    would change the cereal schema and invalidate route logs). It only applies
    when every configured source came up empty, so it can never outvote the
    car's CAN limit, the offline map, carrot or vision.

    Never blocks: MapboxSpeedLimit.update only submits/collects an async
    future. No new requests at standstill (MapboxSpeedLimit gates new requests
    on v_ego >= 1). Like the carrot merge, failures are logged once instead of
    flooding swaglog every frame.
    """
    try:
      gps_data = sm[self._gps_location_service]
      position = {
        "latitude": float(gps_data.latitude),
        "longitude": float(gps_data.longitude),
        "bearing": float(gps_data.bearingDeg),
      }
      gps_valid = bool(gps_data.hasFix) and (position["latitude"] != 0. or position["longitude"] != 0.)

      # plannerd does not subscribe to vehicleParameters; without it the steering
      # sanity check compares against a 0 offset, which is close enough to the
      # true value for its 45 deg window at the speeds this filler runs at.
      try:
        angle_offset = float(sm['vehicleParameters'].angleOffsetDeg)
      except Exception:
        angle_offset = 0.0

      self.mapbox.update(
        datetime.datetime.now(), system_time_valid(), self.v_ego, gps_valid, position,
        float(sm['carState'].steeringAngleDeg), angle_offset,
      )

      if self.mapbox.limit >= 1.:
        self.limit_solutions[SpeedLimitSource.map] = self.mapbox.limit
        self.distance_solutions[SpeedLimitSource.map] = 0.
    except Exception as e:
      # Log rather than swallow, but only once - same one-shot pattern as the
      # carrot merge above.
      if not self._mapbox_warned:
        self._mapbox_warned = True
        cloudlog.warning(f"speed_limit_resolver: mapbox limit fill failed: {type(e).__name__}: {e}")
      return

  def _get_from_map_data(self, sm: messaging.SubMaster) -> None:
    self._reset_limit_sources(SpeedLimitSource.map)
    self._process_map_data(sm)
    self._merge_carrot_speed_limit(sm)
    self._merge_vision_speed_limit(sm)

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

    R3 / D2 — we deliberately read the RAW ``nRoadLimitSpeed`` / ``xSpdLimit``
    fields here and NOT carrot's synthesized ``desiredSpeed``. ``desiredSpeed``
    is already a *post-``calculate_current_speed``* "currently permitted speed":
    it is the output of Carrot's own deceleration model (``AutoNaviSpeedDecelRate``
    / ``AutoNaviSpeedCtrlEnd``), i.e. "the speed you may be at right now after
    Carrot has already started braking." If we folded ``desiredSpeed`` into the
    resolver, SLA would then apply its own ``LIMIT_ADAPT_ACC`` advance-braking
    and adapting acceleration on top of an already-braked-down value, counting
    the deceleration twice and braking earlier/harder than either model intends.
    The raw fields are the *inputs* from which ``desiredSpeed`` is derived, so
    consuming them loses nothing for the road-limit feature. Do not "helpfully"
    switch this to ``desiredSpeed`` — it reintroduces the double-decel trap.
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
        adapt_time = (sdi_limit_ms - self.v_ego) / self._adapt_acc
        adapt_distance = self.v_ego * adapt_time + 0.5 * self._adapt_acc * adapt_time ** 2
        if sdi_dist <= adapt_distance:
          # SDI is stricter; replace/lower the road-class limit.
          if limit_ms <= 0. or sdi_limit_ms < limit_ms:
            limit_ms = sdi_limit_ms
            distance = sdi_dist

      # Section (point-to-point average) cap, ported from cp speedcam branch.
      # Inside a section, carrot publishes max(section limit * safety factor,
      # time-bank allowance) as xSectionLimitKph; it closes the gap where the
      # point camera above goes silent past the start camera and nothing else
      # caps the speed until the section ends. It is an absolute constraint
      # that takes effect immediately (distance 0) and, like every carrot
      # contribution here, it can only lower the map solution - the resolver
      # never lets it raise the road-class limit.
      if bool(carrot.xSectionActive):
        section_limit_ms = _carrot_limit_ms(carrot.xSectionLimitKph)
        if section_limit_ms > 0. and (limit_ms <= 0. or section_limit_ms < limit_ms):
          limit_ms = section_limit_ms
          distance = 0.

      # NOTE: ATC / curve / route speeds are NOT handled here. They were briefly folded
      # into this map source, but they are navigation-driven deceleration for a point
      # ahead, which SmartCruiseControlMap already models with its jerk/accel-limited
      # lookahead - see _update_carrot_map_decel. SLA stays the owner of speed-limit
      # signs: absolute constraints, sourced from nRoadLimitSpeed and the SDI limit.

      # If both limits are absent, do nothing.
      if limit_ms <= 0.:
        return

      # carrot takes priority over the map provider outright: when the phone is
      # projecting navigation, its limit wins whether it is higher or lower than what
      # OSM reported. This replaces the previous lower-only rule, which meant a limit
      # carrot considered authoritative could be silently outvoted by the offline map.
      # Requested explicitly, and the priority matches how the data is produced: a phone
      # projecting a route has the road the driver is actually on, while the offline map
      # can be years out of date or simply lack the section.
      #
      # The car's own CAN limit is still merged as a separate source and can still be
      # stricter, so a physical sign the vehicle reports is not overridden here - see
      # _get_from_car_state and the combined policy.
      self.limit_solutions[SpeedLimitSource.map] = limit_ms
      self.distance_solutions[SpeedLimitSource.map] = distance
    except Exception as e:
      # Log rather than swallow. This block silently returning is why a broken carrot
      # limit link went unnoticed: carrot_man published nRoadLimitSpeed from `_raw`
      # while every producer except KISA wrote the attribute, so the limit simply never
      # appeared, and there was nothing in swaglog to say why.
      if not self._carrot_merge_warned:
        self._carrot_merge_warned = True
        cloudlog.warning(f"speed_limit_resolver: carrot limit merge failed: {type(e).__name__}: {e}")
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
      adapt_time = (next_speed_limit - self.v_ego) / self._adapt_acc
      adapt_distance = self.v_ego * adapt_time + 0.5 * self._adapt_acc * adapt_time ** 2

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

    # Mapbox filler: only when every configured source came up empty and the
    # feature is on. A live source keeps the filler reset, matching
    # StarPilot's _apply_mapbox_filler guard.
    if source != SpeedLimitSource.none or not self.use_mapbox_filler:
      self.mapbox.reset()
    else:
      self._mapbox_fill(sm)
      if self.limit_solutions[SpeedLimitSource.map] > 0.:
        source = SpeedLimitSource.map

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
