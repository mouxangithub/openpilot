"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

Unit tests for the Mapbox Driving-Match filler (mapbox_speed_limit.py) and its
integration into SpeedLimitResolver. The network is fully mocked: no test ever
touches api.mapbox.com.
"""
import calendar
import datetime

from openpilot.common.constants import CV
from openpilot.common.test import OpenpilotTestCase

from openpilot.cereal import custom

from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit import mapbox_speed_limit as msl_module
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.mapbox_speed_limit import (
  FREE_MAPBOX_REQUESTS,
  MapboxSpeedLimit,
)
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.speed_limit_resolver import SpeedLimitResolver
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.common import Policy

import time

SpeedLimitSource = custom.LongitudinalPlanSP.SpeedLimit.Source


class FakeParams:
  """Dict-backed stand-in for Params, sufficient for MapboxSpeedLimit and the resolver param refresh."""

  # Registered defaults (params_keys.h) for keys read with return_default=True
  # during SpeedLimitResolver.update_params.
  REGISTERED_DEFAULTS = {
    "SpeedLimitPolicy": 4,
    "SpeedLimitOffsetType": 0,
    "SpeedLimitValueOffset": 0,
  }

  def __init__(self, values=None):
    self.values = dict(values or {})

  def get(self, key, default=None, return_default=False, encoding=None):
    if key in self.values:
      return self.values[key]
    if return_default:
      return self.REGISTERED_DEFAULTS.get(key, 0)
    return default

  def get_bool(self, key, default=False, block=False):
    return bool(self.values.get(key, default))

  def get_float(self, key, default=0.0):
    try:
      return float(self.values.get(key, default))
    except (TypeError, ValueError):
      return default

  def put(self, key, dat, block=False):
    self.values[key] = dat

  def put_nonblocking(self, key, dat):
    self.put(key, dat)

  def put_float(self, key, val, block=False):
    self.put(key, float(val))


class StubFuture:
  """Minimal concurrent.futures.Future stand-in for the submit/recycle cycle."""

  def __init__(self, result=(0.0, 0.0), done=False):
    self._result = result
    self._done = done
    self.cancelled = False

  def done(self):
    return self._done

  def result(self, timeout=None):
    return self._result

  def cancel(self):
    self.cancelled = True
    return True


class SubmitRecorder:
  """Replaces the executor: records submissions, never runs the request."""

  def __init__(self, future=None):
    self.calls = []
    self.future = future if future is not None else StubFuture()

  def submit(self, fn, *args):
    self.calls.append((fn, args))
    return self.future


def make_mapbox(values=None):
  return MapboxSpeedLimit(FakeParams(values))


def valid_position():
  return {"latitude": 37.422, "longitude": -122.084, "bearing": 90.0}


def update_args(**overrides):
  args = {
    "now": datetime.datetime.now(),
    "time_validated": True,
    "v_ego": 20.0,
    "gps_valid": True,
    "position": valid_position(),
    "steering_angle": 0.0,
    "angle_offset": 0.0,
  }
  args.update(overrides)
  return args


class TestMapboxSpeedLimit(OpenpilotTestCase):

  def test_no_token_no_request(self, mocker):
    """Without MapboxSecretKey the filler resets and never submits a request."""
    mapbox = make_mapbox()
    assert mapbox.token is None
    mapbox.executor = SubmitRecorder()
    mapbox.update(**update_args())
    assert len(mapbox.executor.calls) == 0
    assert mapbox.limit == 0.0
    assert mapbox.segment_distance == 0.0

  def test_quota_exhausted_no_request(self, mocker):
    """Once the monthly budget is spent, no further requests are made."""
    now = datetime.datetime.now()
    mapbox = make_mapbox({
      "MapboxSecretKey": "token",
      "MapBoxRequests": {"total_requests": FREE_MAPBOX_REQUESTS, "max_requests": FREE_MAPBOX_REQUESTS, "month": now.month},
    })
    mapbox.executor = SubmitRecorder()
    mapbox.update(**update_args())
    assert len(mapbox.executor.calls) == 0
    assert mapbox.limit == 0.0

  def test_monthly_quota_reset(self, mocker):
    """A new month resets the counter and scales max_requests by the month's day count."""
    now = datetime.datetime.now()
    other_month = now.month % 12 + 1
    mapbox = make_mapbox({
      "MapboxSecretKey": "token",
      "MapBoxRequests": {"total_requests": 99_999, "max_requests": 99_900, "month": other_month},
    })
    mapbox.executor = SubmitRecorder()
    mapbox.update(**update_args())
    assert mapbox.requests["total_requests"] == 0
    assert mapbox.requests["month"] == now.month
    assert mapbox.requests["max_requests"] == FREE_MAPBOX_REQUESTS - calendar.monthrange(now.year, now.month)[1] * 100

  def test_no_request_when_time_not_validated(self, mocker):
    """Without a validated clock the month must not be flipped (a bad clock could wipe the quota)."""
    now = datetime.datetime.now()
    other_month = now.month % 12 + 1
    mapbox = make_mapbox({
      "MapboxSecretKey": "token",
      "MapBoxRequests": {"total_requests": 99_999, "max_requests": 99_900, "month": other_month},
    })
    mapbox.executor = SubmitRecorder()
    mapbox.update(**update_args(time_validated=False))
    assert mapbox.requests["month"] == other_month
    # quota still counts as spent from the stale bookkeeping
    assert len(mapbox.executor.calls) == 0

  def test_gps_invalid_or_hard_steering_resets(self, mocker):
    """No GPS fix or a steering angle far off the road bearing resets the cached limit."""
    mapbox = make_mapbox({"MapboxSecretKey": "token"})
    mapbox.executor = SubmitRecorder()
    mapbox.limit = 25.0
    mapbox.segment_distance = 100.0

    mapbox.update(**update_args(gps_valid=False))
    assert mapbox.limit == 0.0 and mapbox.segment_distance == 0.0

    mapbox.limit, mapbox.segment_distance = 25.0, 100.0
    mapbox.update(**update_args(steering_angle=90.0, angle_offset=0.0))
    assert mapbox.limit == 0.0 and mapbox.segment_distance == 0.0
    assert len(mapbox.executor.calls) == 0

  def test_no_request_at_standstill(self, mocker):
    """v_ego below 1 m/s never issues a new request."""
    mapbox = make_mapbox({"MapboxSecretKey": "token"})
    mapbox.executor = SubmitRecorder()
    mapbox.update(**update_args(v_ego=0.0))
    assert len(mapbox.executor.calls) == 0
    mapbox.update(**update_args(v_ego=0.5))
    assert len(mapbox.executor.calls) == 0

  def _mock_request(self, mocker, mapbox, speeds, distances):
    """Patch the ping check and the HTTP layer; returns the session.get mock."""
    mocker.patch.object(msl_module, "_is_url_pingable", return_value=True)
    response = mocker.MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
      "matchings": [{"legs": [{"annotation": {"maxspeed": speeds, "distance": distances}}]}],
    }
    mapbox.session.get = mocker.Mock(return_value=response)
    return response

  def test_parse_kmh(self, mocker):
    """A km/h maxspeed annotation converts to m/s with the segment distance."""
    mapbox = make_mapbox({"MapboxSecretKey": "token"})
    self._mock_request(mocker, mapbox, [{"speed": "80", "unit": "km/h"}], [500.0])
    limit, distance = mapbox._request(valid_position(), 20.0)
    assert abs(limit - 80 * CV.KPH_TO_MS) < 1e-6
    assert distance == 500.0

  def test_parse_mph(self, mocker):
    """A mph maxspeed annotation converts to m/s with the segment distance."""
    mapbox = make_mapbox({"MapboxSecretKey": "token"})
    self._mock_request(mocker, mapbox, [{"speed": "55", "unit": "mph"}], [300.0])
    limit, distance = mapbox._request(valid_position(), 20.0)
    assert abs(limit - 55 * CV.MPH_TO_MS) < 1e-6
    assert distance == 300.0

  def test_parse_missing_unit_defaults_to_kmh(self, mocker):
    mapbox = make_mapbox({"MapboxSecretKey": "token"})
    self._mock_request(mocker, mapbox, [{"speed": "60"}], [200.0])
    limit, _ = mapbox._request(valid_position(), 20.0)
    assert abs(limit - 60 * CV.KPH_TO_MS) < 1e-6

  def test_parse_none_speed_rejected(self, mocker):
    """'none' maxspeed (no data for that segment) yields no limit."""
    mapbox = make_mapbox({"MapboxSecretKey": "token"})
    self._mock_request(mocker, mapbox, [{"speed": "none", "unit": "km/h"}], [100.0])
    limit, distance = mapbox._request(valid_position(), 20.0)
    assert limit == 0.0

  def test_async_non_blocking_cycle(self, mocker):
    """Full tick cycle: submit is async, the result publishes a tick later,
    and while segment_distance > 0 no new request is made."""
    mapbox = make_mapbox({"MapboxSecretKey": "token"})
    future = StubFuture(result=(80 * CV.KPH_TO_MS, 500.0), done=False)
    mapbox.executor = SubmitRecorder(future)

    # tick 1: request submitted, nothing published yet
    mapbox.update(**update_args())
    assert len(mapbox.executor.calls) == 1
    assert mapbox.limit == 0.0

    # tick 2: future still in flight - still nothing, still no new submission
    mapbox.update(**update_args())
    assert len(mapbox.executor.calls) == 1
    assert mapbox.limit == 0.0

    # tick 3: future finished - result published
    future._done = True
    mapbox.update(**update_args())
    assert abs(mapbox.limit - 80 * CV.KPH_TO_MS) < 1e-6
    assert mapbox.segment_distance == 500.0

    # ticks 4..N: reuse without new requests, decaying by v_ego * DT_MDL per tick
    for _ in range(10):
      mapbox.update(**update_args())
      assert len(mapbox.executor.calls) == 1
    expected = 500.0 - 10 * 20.0 * msl_module.DT_MDL
    assert abs(mapbox.segment_distance - expected) < 1e-6
    assert abs(mapbox.limit - 80 * CV.KPH_TO_MS) < 1e-6

  def test_segment_distance_exhausted_requests_again(self, mocker):
    """Once the segment is used up a new request is submitted."""
    mapbox = make_mapbox({"MapboxSecretKey": "token"})
    future = StubFuture(result=(80 * CV.KPH_TO_MS, 1.0), done=True)
    mapbox.executor = SubmitRecorder(future)

    mapbox.update(**update_args())  # submit
    mapbox.update(**update_args())  # publish: limit set, segment_distance = 1.0
    assert abs(mapbox.limit - 80 * CV.KPH_TO_MS) < 1e-6
    # segment decays by v_ego * DT_MDL per tick; once exhausted a new request is submitted
    for _ in range(10):
      mapbox.update(**update_args())
      if len(mapbox.executor.calls) == 2:
        break
    assert len(mapbox.executor.calls) == 2
    mapbox.update(**update_args())  # second result publishes
    assert abs(mapbox.limit - 80 * CV.KPH_TO_MS) < 1e-6

  def test_request_failure_is_silent_and_recovers(self, mocker):
    """A failed future logs once, publishes no limit, and the filler keeps going."""
    mapbox = make_mapbox({"MapboxSecretKey": "token"})

    class FailingFuture(StubFuture):
      def result(self, timeout=None):
        raise RuntimeError("network down")

    future = FailingFuture(done=True)
    mapbox.executor = SubmitRecorder(future)

    mapbox.update(**update_args())
    assert len(mapbox.executor.calls) == 1
    mapbox.update(**update_args())
    assert mapbox.limit == 0.0

    # recovery: after clearing the failure's segment budget, a later submission publishes normally
    mapbox.reset()
    future2 = StubFuture(result=(70 * CV.KPH_TO_MS, 400.0), done=True)
    mapbox.executor = SubmitRecorder(future2)
    mapbox.update(**update_args())  # submit
    mapbox.update(**update_args())  # publish
    assert abs(mapbox.limit - 70 * CV.KPH_TO_MS) < 1e-6

  def test_reset_cancels_pending_future(self, mocker):
    mapbox = make_mapbox({"MapboxSecretKey": "token"})
    future = StubFuture(done=False)
    mapbox.executor = SubmitRecorder(future)
    mapbox.update(**update_args())
    mapbox.reset()
    assert future.cancelled
    assert mapbox.future is None
    assert mapbox.limit == 0.0

  def test_quota_bookkeeping_written_as_dict(self, mocker):
    """Each request increments the counter and writes the whole dict back."""
    mapbox = make_mapbox({"MapboxSecretKey": "token"})
    params = mapbox.params
    self._mock_request(mocker, mapbox, [{"speed": "80", "unit": "km/h"}], [500.0])
    mapbox._request(valid_position(), 20.0)
    assert mapbox.requests["total_requests"] == 1
    assert params.values["MapBoxRequests"]["total_requests"] == 1


def mapbox_sm(mocker, map_limit: float = 0.):
  """SubMaster stub with an empty offline map and a valid GPS fix."""
  live_map_data = mocker.MagicMock()
  live_map_data.speedLimit = map_limit
  live_map_data.speedLimitValid = map_limit > 0.
  live_map_data.speedLimitAhead = 0.
  live_map_data.speedLimitAheadValid = False
  live_map_data.speedLimitAheadDistance = 0.
  gps_data = mocker.MagicMock()
  gps_data.latitude = 37.422
  gps_data.longitude = -122.084
  gps_data.bearingDeg = 90.0
  gps_data.hasFix = True
  gps_data.unixTimestampMillis = time.monotonic() * 1e3
  car_state = mocker.MagicMock()
  car_state.steeringAngleDeg = 0.0
  car_state.standstill = False
  car_state_sp = mocker.MagicMock()
  car_state_sp.speedLimit = 0.
  sm = mocker.MagicMock()
  sm.__getitem__.side_effect = lambda key: {
    'carState': car_state,
    'carStateSP': car_state_sp,
    'liveMapDataSP': live_map_data,
    'gpsLocation': gps_data,
    'liveParameters': mocker.MagicMock(angleOffsetDeg=0.0),
  }[key]
  return sm


class TestResolverMapboxFill(OpenpilotTestCase):
  """The Mapbox filler only applies when every configured source is empty, and
  is folded into the `map` source (see SpeedLimitResolver._mapbox_fill)."""

  @staticmethod
  def _resolver():
    resolver = SpeedLimitResolver()
    resolver.policy = Policy.map_data_only
    # A FakeParams with the feature switch on: update_params re-reads it, so it
    # must be in the backing store, not just on the attribute.
    resolver.params = FakeParams({"SLCMapboxFiller": True})
    resolver.use_mapbox_filler = True
    # Inject a filler with a token and a stubbed executor: no network in tests.
    mapbox = MapboxSpeedLimit(FakeParams({"MapboxSecretKey": "token"}))
    mapbox.executor = SubmitRecorder()
    resolver.mapbox = mapbox
    return resolver

  def test_fills_empty_map_source(self, mocker):
    """No car/map limit + a published Mapbox result -> folded into `map`."""
    resolver = self._resolver()
    sm = mapbox_sm(mocker)

    # Request in flight on the first tick: nothing published, source stays none.
    future = StubFuture(result=(80 * CV.KPH_TO_MS, 500.0), done=False)
    resolver.mapbox.executor = SubmitRecorder(future)
    resolver.update(20.0, sm)
    assert resolver.source == SpeedLimitSource.none

    # Next tick: future done -> limit published -> folded into `map`.
    future._done = True
    resolver.update(20.0, sm)
    assert resolver.source == resolver._policy_to_sources_map[Policy.map_data_only][0]
    assert abs(resolver.speed_limit - 80 * CV.KPH_TO_MS) < 1e-6
    assert resolver.distance == 0.

  def test_live_source_resets_filler(self, mocker):
    """A real limit from another source wins and the filler is reset."""
    resolver = self._resolver()
    sm = mapbox_sm(mocker, map_limit=50 * CV.KPH_TO_MS)
    resolver.mapbox.limit = 25.0
    resolver.mapbox.segment_distance = 100.0

    resolver.update(20.0, sm)
    assert abs(resolver.speed_limit - 50 * CV.KPH_TO_MS) < 1e-6
    assert resolver.mapbox.limit == 0.0

  def test_disabled_param_ignores_mapbox(self, mocker):
    resolver = self._resolver()
    resolver.use_mapbox_filler = False
    sm = mapbox_sm(mocker)
    resolver.mapbox.limit = 25.0

    resolver.update(20.0, sm)
    assert resolver.source == SpeedLimitSource.none
    assert resolver.speed_limit == 0.
    assert resolver.mapbox.limit == 0.0

  def test_standstill_does_not_request(self, mocker):
    resolver = self._resolver()
    sm = mapbox_sm(mocker)
    resolver.update(0.0, sm)
    assert len(resolver.mapbox.executor.calls) == 0

  def test_previous_speed_limit_persisted_on_change(self, mocker):
    """PreviousSpeedLimit is written when the last valid limit changes, and not every frame."""
    resolver = self._resolver()
    fp = FakeParams()
    resolver.params = fp
    resolver._last_written_previous_limit = 0.0

    sm = mapbox_sm(mocker, map_limit=50 * CV.KPH_TO_MS)
    resolver.update(20.0, sm)
    assert fp.values["PreviousSpeedLimit"] == resolver.speed_limit_last

    # same value on later frames: no further writes
    writes = [fp.values["PreviousSpeedLimit"]]
    fp.put_float = lambda key, val, block=False: writes.append(val) if key == "PreviousSpeedLimit" else None
    resolver.update(20.0, sm)
    resolver.update(20.0, sm)
    assert len(writes) == 1
