import json
import math
import platform
import time

from openpilot.cereal import custom
from openpilot.common.constants import CV
from openpilot.common.params import Params
from openpilot.common.realtime import DT_MDL
from openpilot.selfdrive.car.cruise import V_CRUISE_UNSET
from openpilot.sunnypilot import PARAMS_UPDATE_PERIOD
from openpilot.sunnypilot.navd.helpers import coordinate_from_param, Coordinate
from openpilot.sunnypilot.selfdrive.controls.lib.smart_cruise_control import MIN_V

MapState = VisionState = custom.LongitudinalPlanSP.SmartCruiseControl.MapState

ACTIVE_STATES = (MapState.turning, )
ENABLED_STATES = (MapState.enabled, MapState.overriding, *ACTIVE_STATES)

R = 6373000.0  # approximate radius of earth in meters
TO_RADIANS = math.pi / 180
TO_DEGREES = 180 / math.pi
TARGET_JERK = -0.6  # m/s^3 There's some jounce limits that are not consistent so we're fudging this some
TARGET_ACCEL = -1.2  # m/s^2 should match up with the long planner limit
TARGET_OFFSET = 1.0  # seconds - This controls how soon before the curve you reach the target velocity. It also helps
                     # reach the target velocity when inaccuracies in the distance modeling logic would cause overshoot.
                     # The value is multiplied against the target velocity to determine the additional distance. This is
                     # done to keep the distance calculations consistent but results in the offset actually being less
                     # time than specified depending on how much of a speed differential there is between v_ego and the
                     # target velocity.

# --- Carrot TMC congestion (phone navigation, App field list §2.5) --------- #
# The phone reports a per-segment traffic status along the route. We fold it
# into THIS controller rather than adding a second map-deceleration entry point,
# so "map says slow down ahead" has exactly one implementation.
#
# Only statuses that mean "actually slowed down" map to a speed cap. free (1)
# and very-free (5) must never lower the target; 0/10 mean unknown / current
# position and are ignored.
TMC_CONGESTION_SPEED_KPH = {
  2: 60,  # slow
  3: 40,  # congested
  4: 30,  # severe
}
# Congestion is advisory: hold it no longer than this after the last update.
TMC_MAX_AGE_SEC = 10.0
# Do not act on congestion further ahead than this (metres).
TMC_LOOKAHEAD_M = 3000.0
# Ignore caps that are not meaningfully below the current cruise target.
TMC_MIN_CAP_DELTA_MS = 1.0

# Carrot map-deceleration sources (ATC turn speed, curve speed, route-curvature speed).
# Same freshness budget as the TMC arrays: they arrive on the same carrotManSP packet.
MAP_DECEL_MAX_AGE_SEC = 10.0
# Amap's route curve speed arrives on liveMapDataSP instead - a different packet with a
# different publisher and refresh cadence - so it gets its own budget rather than
# sharing the carrot one. mapd_manager refreshes on a 2 s TTL / 20 m movement, so 10 s
# is ~5 refreshes of slack and still tight enough that a lost lock cannot linger.
AMAP_CURVE_MAX_AGE_SEC = 10.0
# Only fold a value in when it is meaningfully below the current target, so tiny
# differences do not flap the state machine.
MAP_DECEL_MIN_DELTA_MS = 1.0


def velocities_from_param(param: str, params: Params):
  if params is None:
    params = Params()

  json_str = params.get(param)
  if json_str is None:
    return None

  velocities = json.loads(json_str)

  return velocities


def _parse_int_list(raw) -> list[int]:
  """Decode a compact JSON int array, tolerating bytes / bad payloads."""
  if not raw:
    return []
  if isinstance(raw, (bytes, bytearray)):
    try:
      raw = raw.decode("utf-8", errors="ignore")
    except Exception:
      return []
  if isinstance(raw, (list, tuple)):
    items = raw
  else:
    try:
      items = json.loads(raw)
    except (TypeError, ValueError):
      return []
  if not isinstance(items, (list, tuple)):
    return []
  out: list[int] = []
  for v in items:
    try:
      out.append(int(v))
    except (TypeError, ValueError):
      out.append(0)
  return out


def congestion_cap_ms(carrot) -> float:
  """Speed cap (m/s) implied by the phone's TMC congestion report, else 0.

  Returns 0 when there is nothing actionable: no report, an all-clear route, or
  congestion that lies beyond ``TMC_LOOKAHEAD_M``.

  The cap is the *worst* status found within the look-ahead window, translated
  through ``TMC_CONGESTION_SPEED_KPH``. Only statuses in that table produce a
  cap, so free (1) / very-free (5) / unknown (0, 10) never slow the car.
  """
  statuses = _parse_int_list(getattr(carrot, "tmcSegmentStatuses", ""))
  if not statuses:
    return 0.

  distances = _parse_int_list(getattr(carrot, "tmcSegmentDistances", ""))
  # Segments are reported from the current position forward; walk them and stop
  # once the cumulative distance leaves the look-ahead window.
  travelled = 0.0
  worst = 0
  for i, status in enumerate(statuses):
    if i < len(distances):
      travelled += max(0.0, float(distances[i]))
    if travelled > TMC_LOOKAHEAD_M:
      break
    if status in TMC_CONGESTION_SPEED_KPH:
      worst = max(worst, status)

  if worst == 0:
    return 0.
  return float(TMC_CONGESTION_SPEED_KPH[worst]) * CV.KPH_TO_MS


def calculate_accel(t, target_jerk, a_ego):
  return a_ego + target_jerk * t


def calculate_velocity(t, target_jerk, a_ego, v_ego):
  return v_ego + a_ego * t + target_jerk/2 * (t ** 2)


def calculate_distance(t, target_jerk, a_ego, v_ego):
  return t * v_ego + a_ego/2 * (t ** 2) + target_jerk/6 * (t ** 3)


# points should be in radians
# output is meters
def distance_to_point(ax, ay, bx, by):
  a = math.sin((bx-ax)/2)*math.sin((bx-ax)/2) + math.cos(ax) * math.cos(bx)*math.sin((by-ay)/2)*math.sin((by-ay)/2)
  c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

  return R * c  # in meters


class SmartCruiseControlMap:
  v_target: float = 0
  a_target: float = 0.
  v_ego: float = 0.
  a_ego: float = 0.
  output_v_target: float = V_CRUISE_UNSET
  output_a_target: float = 0.

  def __init__(self):
    self.params = Params()
    self.mem_params = Params("/dev/shm/params") if platform.system() != "Darwin" else self.params
    self.enabled = self.params.get_bool("SmartCruiseControlMap")
    self.long_enabled = False
    self.long_override = False
    self.is_enabled = False
    self.is_active = False
    self.state = MapState.disabled
    self.v_cruise = 0
    self.target_lat = 0.0
    self.target_lon = 0.0
    self.frame = -1

    self.last_position = coordinate_from_param("LastGPSPosition", self.mem_params) or Coordinate(0.0, 0.0)
    self.target_velocities = velocities_from_param("MapTargetVelocities", self.mem_params) or []

    # Carrot TMC congestion (killswitch default OFF, see update_params()).
    self.use_carrot_congestion = self.params.get_bool("CarrotTrafficCongestionEnabled")
    self.congestion_cap = 0.0
    self.congestion_used = False

    # Carrot navigation deceleration (ATC / curve / route). Gated by
    # CarrotMapDecelEnabled; like the congestion cap it only folds into v_target and
    # therefore still needs SmartCruiseControlMap to actuate.
    self.use_carrot_map_decel = self.params.get_bool("CarrotMapDecelEnabled")
    self.map_decel_speed = 0.0
    self.map_decel_source = ""

    # Amap map-route curve speed, a fourth candidate in the same family. It arrives on
    # a DIFFERENT packet (liveMapDataSP, published by mapd_manager) than the carrot
    # deceleration sources (carrotManSP), so it has its own freshness budget rather
    # than sharing MAP_DECEL_MAX_AGE_SEC. Gated by AmapCurveSpeedEnabled, the switch
    # the provider already reads; this is the consumer that switch never had.
    self.use_amap_curve = self.params.get_bool("AmapCurveSpeedEnabled")

  def get_v_target_from_control(self) -> float:
    if self.is_active:
      return max(self.v_target, MIN_V)

    return V_CRUISE_UNSET

  def get_a_target_from_control(self) -> float:
    return self.a_ego

  def _update_congestion(self, sm) -> None:
    """Fold the phone's TMC congestion report into ``self.v_target``.

    Gated by ``CarrotTrafficCongestionEnabled`` (default OFF). Reads only the
    RAW TMC arrays published on ``carrotManSP``; the phone's own synthesized
    speeds are deliberately not consumed (same double-decel reasoning as
    ``SpeedLimitResolver._merge_carrot_speed_limit``).

    IMPORTANT — this switch alone does not actuate. ``self.v_target`` only
    reaches the planner through ``get_v_target_from_control()``, which returns
    ``V_CRUISE_UNSET`` unless ``self.is_active``, which requires the state
    machine to reach ``MapState.turning``, which requires ``self.enabled``
    (``SmartCruiseControlMap``). So BOTH ``CarrotTrafficCongestionEnabled`` and
    ``SmartCruiseControlMap`` must be on for the car to respond. That is
    intentional: this feature folds into the existing map-deceleration
    controller rather than creating a second path to the vehicle, so it inherits
    that controller's master switch.

    The cap can only ever *lower* the map controller's target:
      * a stale packet is ignored entirely;
      * a cap that is not meaningfully below the current target is ignored;
      * ``free``/``very-free``/``unknown`` statuses never produce a cap.
    """
    self.congestion_cap = 0.0
    self.congestion_used = False
    if not self.use_carrot_congestion or sm is None:
      return
    try:
      if not sm.valid.get("carrotManSP", False) or not sm.alive.get("carrotManSP", False):
        return
      if time.monotonic() - sm.recv_time["carrotManSP"] > TMC_MAX_AGE_SEC:
        return
      carrot = sm["carrotManSP"]
      if int(getattr(carrot, "activeCarrot", 0) or 0) <= 0:
        return

      cap = congestion_cap_ms(carrot)
      if cap <= 0.:
        return
      self.congestion_cap = cap

      # Only lower an existing target, and only by a meaningful margin.
      if self.v_target > 0. and cap >= self.v_target - TMC_MIN_CAP_DELTA_MS:
        return
      self.v_target = cap
      self.congestion_used = True
    except Exception:
      return

  def _update_carrot_map_decel(self, sm) -> None:
    """Fold map-derived navigation deceleration into ``self.v_target``.

    Handles the map-derived "slow down for something ahead" sources:
      * ``atcSpeed``    - ATC turn speed (auto turn control)          [carrot]
      * ``vTurnSpeedMs``- the turn-table curve speed                  [carrot]
      * ``routeSpeed``  - route-curvature speed from the nav polyline [carrot]
      * ``curveSpeed``  - route-shape curve speed from Amap           [liveMapData]

    Why here and not in SLA: SLA owns speed-limit *signs* - absolute constraints the
    driver can see - while navigation-driven deceleration for a point ahead is what this
    controller already models with its jerk/accel-limited lookahead (TARGET_JERK /
    TARGET_ACCEL / TARGET_OFFSET). Folding them in here reuses that model instead of
    building a second one, and matches how the TMC congestion cap already works. The
    visual curbside case stays with SmartCruiseControlVision, which is model-derived
    rather than map-derived.

    The carrot and Amap families arrive on different packets and are gated
    independently; see ``_carrot_decel_candidates`` / ``_amap_curve_candidates``.
    Amap's curve speed is switched by ``AmapCurveSpeedEnabled``, its own param - not
    by ``CarrotMapDecelEnabled``, which only governs the carrot sources.

    Only ever LOWERS the target, and only by a meaningful margin:
      * a stale or inactive packet is ignored entirely;
      * a source without a usable distance is skipped;
      * a value that is not meaningfully below the current target is ignored.
    Like the congestion cap, this still needs SmartCruiseControlMap to actuate.
    """
    self.map_decel_speed = 0.0
    self.map_decel_source = ""
    if sm is None:
      return
    try:
      # Collect from every eligible source, then take the lowest. The two families
      # arrive on different packets and must be gated independently: a carrot packet
      # that is absent, stale or inactive says nothing about whether Amap's route
      # curve speed is usable, and vice versa. Returning early on either one would
      # silently disable the other.
      candidates: list[tuple[float, float, str]] = []

      if self.use_carrot_map_decel:
        candidates.extend(self._carrot_decel_candidates(sm))
      if self.use_amap_curve:
        candidates.extend(self._amap_curve_candidates(sm))

      best = 0.0
      best_label = ""
      for speed, dist, label in candidates:
        if not (0.0 < speed < 250.0):
          continue
        # A source with no usable distance is skipped rather than applied immediately -
        # "slow now for something an unknown distance away" is not something this
        # controller can place on its map, and applying it unconditionally would turn a
        # stale value into a permanent cap.
        if dist <= 0.0:
          continue
        if best <= 0.0 or speed < best:
          best = speed
          best_label = label

      if best <= 0.0:
        return
      self.map_decel_speed = best

      # Only lower an existing target, and only by a meaningful margin.
      if self.v_target > 0. and best >= self.v_target - MAP_DECEL_MIN_DELTA_MS:
        return
      self.v_target = best
      self.map_decel_source = best_label
    except Exception:
      return

  def _carrot_decel_candidates(self, sm) -> list[tuple[float, float, str]]:
    """Carrot's ATC / turn-table / route-curvature speeds, as ``(ms, m, label)``.

    Returns an empty list when the packet is missing, stale or inactive - in that
    case carrot simply has nothing to contribute, which is not an error.
    """
    if not sm.valid.get("carrotManSP", False) or not sm.alive.get("carrotManSP", False):
      return []
    if time.monotonic() - sm.recv_time["carrotManSP"] > MAP_DECEL_MAX_AGE_SEC:
      return []
    carrot = sm["carrotManSP"]
    if int(getattr(carrot, "activeCarrot", 0) or 0) <= 0:
      return []

    # A zero speed means "no value", and 250.0 is carrot's "no limit" sentinel for ATC.
    return [
      (float(getattr(carrot, "atcSpeed", 0.0) or 0.0),
       float(getattr(carrot, "atcDist", 0.0) or 0.0), "atc"),
      (float(getattr(carrot, "vTurnSpeedMs", 0.0) or 0.0),
       float(getattr(carrot, "xDistToTurn", 0) or 0), "curve"),
      (float(getattr(carrot, "routeSpeed", 0.0) or 0.0),
       float(getattr(carrot, "routeDist", 0.0) or 0.0), "route"),
    ]

  def _amap_curve_candidates(self, sm) -> list[tuple[float, float, str]]:
    """Amap's route-shape curve speed, as ``(ms, m, label)``.

    Read from ``liveMapDataSP`` (published by mapd_manager), which carries its own
    ``curveSpeedValid`` flag. That flag is authoritative: a zero speed with the flag
    clear means "no curve constraint" - a straight road or a provider without route
    geometry - and must never be read as "stop". A stale packet is ignored on the
    same principle as the carrot sources.
    """
    if not sm.valid.get("liveMapDataSP", False) or not sm.alive.get("liveMapDataSP", False):
      return []
    if time.monotonic() - sm.recv_time["liveMapDataSP"] > AMAP_CURVE_MAX_AGE_SEC:
      return []
    map_data = sm["liveMapDataSP"]
    if not bool(getattr(map_data, "curveSpeedValid", False)):
      return []
    speed = float(getattr(map_data, "curveSpeed", 0.0) or 0.0)
    dist = float(getattr(map_data, "curveSpeedDistance", 0.0) or 0.0)
    return [(speed, dist, "amap_curve")]

  def update_params(self):
    if self.frame % int(PARAMS_UPDATE_PERIOD / DT_MDL) == 0:
      self.enabled = self.params.get_bool("SmartCruiseControlMap")
      self.use_carrot_congestion = self.params.get_bool("CarrotTrafficCongestionEnabled")
      self.use_carrot_map_decel = self.params.get_bool("CarrotMapDecelEnabled")
      self.use_amap_curve = self.params.get_bool("AmapCurveSpeedEnabled")
      # Auto-arm: with carrot navigation on, any of its map-deceleration sub-features
      # turns this controller on by itself. SCC Map stays the single execution path -
      # the user just no longer has to find and flip a second switch to make the first
      # one do anything.
      if not self.enabled and self.params.get_bool("CarrotEnabled"):
        self.enabled = (self.use_carrot_congestion or self.use_carrot_map_decel
                        or self.use_amap_curve)

  def update_calculations(self) -> None:
    self.last_position = coordinate_from_param("LastGPSPosition", self.mem_params) or Coordinate(0.0, 0.0)
    lat = self.last_position.latitude
    lon = self.last_position.longitude

    self.target_velocities = velocities_from_param("MapTargetVelocities", self.mem_params) or []

    if self.last_position is None or self.target_velocities is None:
      return

    min_dist = 1000
    min_idx = 0
    distances = []

    # find our location in the path
    for i in range(len(self.target_velocities)):
      target_velocity = self.target_velocities[i]
      tlat = target_velocity["latitude"]
      tlon = target_velocity["longitude"]
      d = distance_to_point(lat * TO_RADIANS, lon * TO_RADIANS, tlat * TO_RADIANS, tlon * TO_RADIANS)
      distances.append(d)
      if d < min_dist:
        min_dist = d
        min_idx = i

    # only look at values from our current position forward
    forward_points = self.target_velocities[min_idx:]
    forward_distances = distances[min_idx:]

    # find velocities that we are within the distance we need to adjust for
    valid_velocities = []
    for i in range(len(forward_points)):
      target_velocity = forward_points[i]
      tlat = target_velocity["latitude"]
      tlon = target_velocity["longitude"]
      tv = target_velocity["velocity"]
      if tv > self.v_ego:
        continue

      d = forward_distances[i]

      a_diff = (self.a_ego - TARGET_ACCEL)
      accel_t = abs(a_diff / TARGET_JERK)
      min_accel_v = calculate_velocity(accel_t, TARGET_JERK, self.a_ego, self.v_ego)

      max_d = 0
      if tv > min_accel_v:
        # calculate time needed based on target jerk
        a = 0.5 * TARGET_JERK
        b = self.a_ego
        c = self.v_ego - tv
        t_a = -1 * ((b**2 - 4 * a * c) ** 0.5 + b) / (2 * a)
        t_b = ((b**2 - 4 * a * c) ** 0.5 - b) / (2 * a)
        if not isinstance(t_a, complex) and t_a > 0:
          t = t_a
        else:
          t = t_b
        if isinstance(t, complex):
          continue

        max_d = max_d + calculate_distance(t, TARGET_JERK, self.a_ego, self.v_ego)
      else:
        t = accel_t
        max_d = calculate_distance(t, TARGET_JERK, self.a_ego, self.v_ego)

        # calculate additional time needed based on target accel
        t = abs((min_accel_v - tv) / TARGET_ACCEL)
        max_d += calculate_distance(t, 0, TARGET_ACCEL, min_accel_v)

      if d < max_d + tv * TARGET_OFFSET:
        valid_velocities.append((float(tv), tlat, tlon))

    # Find the smallest velocity we need to adjust for
    min_v = 100.0
    target_lat = 0.0
    target_lon = 0.0
    for tv, lat, lon in valid_velocities:
      if tv < min_v:
        min_v = tv
        target_lat = lat
        target_lon = lon

    if self.v_target < min_v and not (self.target_lat == 0 and self.target_lon == 0):
      for i in range(len(forward_points)):
        target_velocity = forward_points[i]
        tlat = target_velocity["latitude"]
        tlon = target_velocity["longitude"]
        tv = target_velocity["velocity"]
        if tv > self.v_ego:
          continue

        if tlat == self.target_lat and tlon == self.target_lon and tv == self.v_target:
          return

      # not found so let's reset
      self.v_target = 0.0
      self.target_lat = 0.0
      self.target_lon = 0.0

    self.v_target = min_v
    self.target_lat = target_lat
    self.target_lon = target_lon

  def _update_state_machine(self) -> tuple[bool, bool]:
    # ENABLED, TURNING
    if self.state != MapState.disabled:
      if not self.long_enabled or not self.enabled:
        self.state = MapState.disabled
      elif self.long_override:
        self.state = MapState.overriding

      else:
        # ENABLED
        if self.state == MapState.enabled:
          if self.v_cruise > self.v_target != 0:
            self.state = MapState.turning

        # TURNING
        elif self.state == MapState.turning:
          if self.v_cruise <= self.v_target or self.v_target == 0:
            self.state = MapState.enabled

        # OVERRIDING
        elif self.state == MapState.overriding:
          if not self.long_override:
            if self.v_cruise > self.v_target != 0:
              self.state = MapState.turning
            else:
              self.state = MapState.enabled

    # DISABLED
    elif self.state == MapState.disabled:
      if self.long_enabled and self.enabled:
        if self.long_override:
          self.state = MapState.overriding
        else:
          self.state = MapState.enabled

    enabled = self.state in ENABLED_STATES
    active = self.state in ACTIVE_STATES

    return enabled, active

  def update(self, long_enabled: bool, long_override: bool, v_ego, a_ego, v_cruise, sm=None) -> None:
    self.long_enabled = long_enabled
    self.long_override = long_override
    self.v_ego = v_ego
    self.a_ego = a_ego
    self.v_cruise = v_cruise

    self.update_params()
    self.update_calculations()
    # Fold in phone TMC congestion AFTER the map velocities so the cap can only
    # lower the target, never raise it. `sm` is optional so existing callers
    # that only exercise the map-velocity path keep working unchanged.
    self._update_congestion(sm)
    # Same folding rule as the congestion cap: after the map velocities, lower-only.
    self._update_carrot_map_decel(sm)

    self.is_enabled, self.is_active = self._update_state_machine()

    self.output_v_target = self.get_v_target_from_control()
    self.output_a_target = self.get_a_target_from_control()

    self.frame += 1
