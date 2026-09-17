"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import random
import time

from openpilot.common.constants import CV
from openpilot.common.parameterized import parameterized

from openpilot.cereal import custom
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit import LIMIT_MAX_MAP_DATA_AGE

from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.speed_limit_resolver import SpeedLimitResolver, ALL_SOURCES
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.common import Policy
from openpilot.common.test import OpenpilotTestCase

SpeedLimitSource = custom.LongitudinalPlanSP.SpeedLimit.Source


def create_mock(properties, mocker):
  mock = mocker.MagicMock()
  for _property, value in properties.items():
    setattr(mock, _property, value)
  return mock


def setup_sm_mock(mocker):
  cruise_speed_limit = random.uniform(0, 120)
  live_map_data_limit = random.uniform(0, 120)

  car_state = create_mock({
    'gasPressed': False,
    'brakePressed': False,
    'standstill': False,
  }, mocker)
  car_state_sp = create_mock({
    'speedLimit': cruise_speed_limit,
  }, mocker)
  live_map_data = create_mock({
    'speedLimit': live_map_data_limit,
    'speedLimitValid': True,
    'speedLimitAhead': 0.,
    'speedLimitAheadValid': 0.,
    'speedLimitAheadDistance': 0.,
  }, mocker)
  gps_data = create_mock({
    'unixTimestampMillis': time.monotonic() * 1e3,
  }, mocker)
  sm_mock = mocker.MagicMock()
  sm_mock.__getitem__.side_effect = lambda key: {
    'carState': car_state,
    'liveMapDataSP': live_map_data,
    'carStateSP': car_state_sp,
    'gpsLocation': gps_data,
  }[key]
  return sm_mock


parametrized_policies = parameterized.expand(
  [
    (Policy.car_state_only, 'carStateSP', SpeedLimitSource.car),
    (Policy.car_state_priority, 'carStateSP', SpeedLimitSource.car),
    (Policy.map_data_only, 'liveMapDataSP', SpeedLimitSource.map),
    (Policy.map_data_priority, 'liveMapDataSP', SpeedLimitSource.map),
  ],
  names=["policy", "sm_key", "function_key"]
)


def resolver_class():
  return SpeedLimitResolver


class TestSpeedLimitResolverValidation(OpenpilotTestCase):

  @parameterized.expand(list(Policy), names=["policy"])
  def test_initial_state(self, resolver_class, policy):
    resolver = resolver_class()
    resolver.policy = policy
    for source in ALL_SOURCES:
      if source in resolver.limit_solutions:
        assert resolver.limit_solutions[source] == 0.
        assert resolver.distance_solutions[source] == 0.

  @parametrized_policies
  def test_resolver(self, resolver_class, policy, sm_key, function_key, mocker):
    resolver = resolver_class()
    resolver.policy = policy
    sm_mock = setup_sm_mock(mocker)
    source_speed_limit = sm_mock[sm_key].speedLimit

    # Assert the resolver
    resolver.update(source_speed_limit, sm_mock)
    assert resolver.speed_limit == source_speed_limit
    assert resolver.source == ALL_SOURCES[function_key]

  def test_resolver_combined(self, resolver_class, mocker):
    resolver = resolver_class()
    resolver.policy = Policy.combined
    sm_mock = setup_sm_mock(mocker)
    socket_to_source = {'carStateSP': SpeedLimitSource.car, 'liveMapDataSP': SpeedLimitSource.map}
    minimum_key, minimum_speed_limit = min(
      ((key, sm_mock[key].speedLimit) for key in
       socket_to_source.keys()), key=lambda x: x[1])

    # Assert the resolver
    resolver.update(minimum_speed_limit, sm_mock)
    assert resolver.speed_limit == minimum_speed_limit
    assert resolver.source == socket_to_source[minimum_key]

  @parametrized_policies
  def test_parser(self, resolver_class, policy, sm_key, function_key, mocker):
    resolver = resolver_class()
    resolver.policy = policy
    sm_mock = setup_sm_mock(mocker)
    source_speed_limit = sm_mock[sm_key].speedLimit

    # Assert the parsing
    resolver.update(source_speed_limit, sm_mock)
    assert resolver.limit_solutions[ALL_SOURCES[function_key]] == source_speed_limit
    assert resolver.distance_solutions[ALL_SOURCES[function_key]] == 0.

  @parameterized.expand(list(Policy), names=["policy"])
  def test_resolve_interaction_in_update(self, resolver_class, policy, mocker):
    v_ego = 50
    resolver = resolver_class()
    resolver.policy = policy

    sm_mock = setup_sm_mock(mocker)
    resolver.update(v_ego, sm_mock)

    # After resolution
    assert resolver.speed_limit is not None
    assert resolver.distance is not None
    assert resolver.source is not None

  @parameterized.expand(list(Policy), names=["policy"])
  def test_old_map_data_ignored(self, resolver_class, policy, mocker):
    resolver = resolver_class()
    resolver.policy = policy
    sm_mock = mocker.MagicMock()
    sm_mock['gpsLocation'].unixTimestampMillis = (time.monotonic() - 2 * LIMIT_MAX_MAP_DATA_AGE) * 1e3
    resolver._get_from_map_data(sm_mock)
    assert resolver.limit_solutions[SpeedLimitSource.map] == 0.
    assert resolver.distance_solutions[SpeedLimitSource.map] == 0.


def carrot_sm(mocker, map_limit: float = 0., **carrot_fields):
  """SubMaster stub exposing carrotManSP plus an (optionally empty) live map."""
  carrot = create_mock({
    'activeCarrot': 1,
    'nRoadLimitSpeed': 0,
    'xSpdLimit': 0,
    'xSpdDist': 0.,
  } | carrot_fields, mocker)
  live_map_data = create_mock({
    'speedLimit': map_limit,
    'speedLimitValid': map_limit > 0.,
    'speedLimitAhead': 0.,
    'speedLimitAheadValid': False,
    'speedLimitAheadDistance': 0.,
  }, mocker)
  gps_data = create_mock({'unixTimestampMillis': time.monotonic() * 1e3}, mocker)
  sm = mocker.MagicMock()
  sm.__getitem__.side_effect = lambda key: {
    'liveMapDataSP': live_map_data,
    'gpsLocation': gps_data,
    'carrotManSP': carrot,
  }[key]
  sm.valid.get = lambda key: key == 'carrotManSP'
  sm.recv_time = {'carrotManSP': time.monotonic()}
  return sm


class TestCarrotSpeedLimitMerge(OpenpilotTestCase):
  """carrot phone-navigation limits are folded into the `map` source so the SLA
  widget and Speed Limit Assist both see them, without touching the cereal
  schema. See SpeedLimitResolver._merge_carrot_speed_limit."""

  @staticmethod
  def _resolver():
    resolver = SpeedLimitResolver()
    resolver.policy = Policy.map_data_only
    resolver.use_carrot_limits = True
    return resolver

  def test_road_limit_used_when_map_is_empty(self, mocker):
    resolver = self._resolver()
    resolver._get_from_map_data(carrot_sm(mocker, nRoadLimitSpeed=60))
    assert abs(resolver.limit_solutions[SpeedLimitSource.map] - 60 * CV.KPH_TO_MS) < 1e-6
    assert resolver.distance_solutions[SpeedLimitSource.map] == 0.

  def test_sdi_limit_ignored_until_braking_distance(self, mocker):
    """SDI camera limit only takes effect once the car is close enough to
    start braking with LIMIT_ADAPT_ACC."""
    resolver = self._resolver()
    # 70 kph ≈ 19.44 m/s; 40 kph ≈ 11.11 m/s; delta v = -8.33 m/s.
    # adapt_time = -8.33 / LIMIT_ADAPT_ACC; adapt_distance ≈ 23.1 m.
    resolver.v_ego = 70 * CV.KPH_TO_MS
    sm = carrot_sm(mocker, xSpdLimit=40, xSpdDist=300.)
    resolver._get_from_map_data(sm)
    # 300 m is far beyond the adapt distance → keep the road limit at zero.
    assert resolver.limit_solutions[SpeedLimitSource.map] == 0.
    assert resolver.distance_solutions[SpeedLimitSource.map] == 0.

    # Now place the camera inside the adapt distance → SDI becomes active.
    sm = carrot_sm(mocker, xSpdLimit=40, xSpdDist=20.)
    resolver._get_from_map_data(sm)
    assert abs(resolver.limit_solutions[SpeedLimitSource.map] - 40 * CV.KPH_TO_MS) < 1e-6
    assert abs(resolver.distance_solutions[SpeedLimitSource.map] - 20.) < 1e-6

    # A camera limit with no distance means the camera is not ahead → ignored.
    resolver = self._resolver()
    resolver._merge_carrot_speed_limit(carrot_sm(mocker, xSpdLimit=50, xSpdDist=0.))
    assert resolver.limit_solutions[SpeedLimitSource.map] == 0.

  def test_sdi_limit_stricter_than_road_limit(self, mocker):
    resolver = self._resolver()
    resolver.v_ego = 90 * CV.KPH_TO_MS
    sm = carrot_sm(mocker, nRoadLimitSpeed=80, xSpdLimit=60, xSpdDist=15.)
    resolver._get_from_map_data(sm)
    assert abs(resolver.limit_solutions[SpeedLimitSource.map] - 60 * CV.KPH_TO_MS) < 1e-6
    assert abs(resolver.distance_solutions[SpeedLimitSource.map] - 15.) < 1e-6

  def test_sdi_limit_does_not_raise_above_road_limit(self, mocker):
    """If the SDI camera limit is *above* the road-class limit, the road-class
    limit remains effective immediately."""
    resolver = self._resolver()
    resolver.v_ego = 70 * CV.KPH_TO_MS
    sm = carrot_sm(mocker, nRoadLimitSpeed=60, xSpdLimit=80, xSpdDist=20.)
    resolver._get_from_map_data(sm)
    assert abs(resolver.limit_solutions[SpeedLimitSource.map] - 60 * CV.KPH_TO_MS) < 1e-6
    assert resolver.distance_solutions[SpeedLimitSource.map] == 0.

  def test_carrot_cannot_raise_an_existing_map_limit(self, mocker):
    resolver = self._resolver()
    resolver.limit_solutions[SpeedLimitSource.map] = 40 * CV.KPH_TO_MS
    resolver._merge_carrot_speed_limit(carrot_sm(mocker, nRoadLimitSpeed=80))
    assert abs(resolver.limit_solutions[SpeedLimitSource.map] - 40 * CV.KPH_TO_MS) < 1e-6

  def test_carrot_out_of_range_is_rejected(self, mocker):
    resolver = self._resolver()
    for bad in [0, 400, -5, "abc"]:
      resolver._merge_carrot_speed_limit(carrot_sm(mocker, nRoadLimitSpeed=bad))
      assert resolver.limit_solutions[SpeedLimitSource.map] == 0.

  def test_disabled_param_ignores_carrot(self, mocker):
    resolver = self._resolver()
    resolver.use_carrot_limits = False
    resolver._get_from_map_data(carrot_sm(mocker, nRoadLimitSpeed=60))
    assert resolver.limit_solutions[SpeedLimitSource.map] == 0.

  def test_inactive_or_absent_carrot_is_ignored(self, mocker):
    resolver = self._resolver()
    resolver._merge_carrot_speed_limit(carrot_sm(mocker, activeCarrot=0, nRoadLimitSpeed=60))
    assert resolver.limit_solutions[SpeedLimitSource.map] == 0.

    no_carrot = mocker.MagicMock()
    no_carrot.valid.get = lambda key: False
    resolver._merge_carrot_speed_limit(no_carrot)
    assert resolver.limit_solutions[SpeedLimitSource.map] == 0.

  def test_stale_carrot_packet_is_ignored(self, mocker):
    resolver = self._resolver()
    sm = carrot_sm(mocker, nRoadLimitSpeed=60)
    sm.recv_time['carrotManSP'] = time.monotonic() - LIMIT_MAX_MAP_DATA_AGE - 1.
    resolver._merge_carrot_speed_limit(sm)
    assert resolver.limit_solutions[SpeedLimitSource.map] == 0.
