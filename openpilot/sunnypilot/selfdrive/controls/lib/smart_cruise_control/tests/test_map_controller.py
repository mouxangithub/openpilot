"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import json
import math
import platform
import time


from openpilot.cereal import custom
from openpilot.common.constants import CV
from openpilot.common.params import Params
from openpilot.common.realtime import DT_MDL
from openpilot.selfdrive.car.cruise import V_CRUISE_UNSET
from openpilot.sunnypilot.selfdrive.controls.lib.smart_cruise_control.map_controller import (
  R, TMC_CONGESTION_SPEED_KPH, TMC_LOOKAHEAD_M, TMC_MAX_AGE_SEC,
  SmartCruiseControlMap, congestion_cap_ms,
)
from openpilot.common.test import OpenpilotTestCase

MapState = VisionState = custom.LongitudinalPlanSP.SmartCruiseControl.MapState


class TestSmartCruiseControlMap(OpenpilotTestCase):

  def setup_method(self):
    self.params = Params()
    self.mem_params = Params("/dev/shm/params") if platform.system() != "Darwin" else self.params
    self.reset_params()
    self.scc_m = SmartCruiseControlMap()

  def reset_params(self):
    self.params.put_bool("SmartCruiseControlMap", True, block=True)

    # TODO-SP: mock data from gpsLocation
    self.params.put("LastGPSPosition", "{}", block=True)
    self.params.put("MapTargetVelocities", "{}", block=True)

  def test_initial_state(self):
    assert self.scc_m.state == VisionState.disabled
    assert not self.scc_m.is_active
    assert self.scc_m.output_v_target == V_CRUISE_UNSET
    assert self.scc_m.output_a_target == 0.

  def test_system_disabled(self):
    self.params.put_bool("SmartCruiseControlMap", False, block=True)
    self.scc_m.enabled = self.params.get_bool("SmartCruiseControlMap")

    for _ in range(int(10. / DT_MDL)):
      self.scc_m.update(True, False, 0., 0., 0.)
    assert self.scc_m.state == VisionState.disabled
    assert not self.scc_m.is_active

  def test_disabled(self):
    for _ in range(int(10. / DT_MDL)):
      self.scc_m.update(False, False, 0., 0., 0.)
    assert self.scc_m.state == VisionState.disabled

  def test_transition_disabled_to_enabled(self):
    for _ in range(int(10. / DT_MDL)):
      self.scc_m.update(True, False, 0., 0., 0.)
    assert self.scc_m.state == VisionState.enabled

  def test_moderate_curve(self):
    # Regression: `... / 2 * a` parsed as `(.../2)*a` instead of `.../(2*a)`,
    # making max_d ~11x too small so the moderate-curve branch never tripped.
    # v_ego=25, a_ego=0, tv=24: fixed max_d≈45m vs buggy ≈4m at a 40m waypoint.
    waypoint_lon_deg = (40.0 / R) * (180.0 / math.pi)
    self.mem_params.put("LastGPSPosition", json.dumps({"latitude": 0.0, "longitude": 0.0}), block=True)
    self.mem_params.put("MapTargetVelocities",
                        json.dumps([{"latitude": 0.0, "longitude": waypoint_lon_deg, "velocity": 24.0}]), block=True)

    self.scc_m.update(True, False, 25.0, 0.0, 30.0)

    self.assertAlmostEqual(self.scc_m.v_target, 24.0, delta=24.0 * 1e-6)

  # TODO-SP: mock data from modelV2 to test other states


class _FakeCarrotManSP:
  def __init__(self, statuses="", distances="", active=1):
    self.tmcSegmentStatuses = statuses
    self.tmcSegmentDistances = distances
    self.activeCarrot = active


class _FakeSM:
  """Minimal SubMaster stand-in exposing only what the congestion path reads."""

  def __init__(self, carrot=None, age=0.0):
    self._carrot = carrot
    self.valid = {"carrotManSP": carrot is not None}
    self.alive = {"carrotManSP": carrot is not None}
    self.recv_time = {"carrotManSP": time.monotonic() - age}

  def __getitem__(self, key):
    if key == "carrotManSP":
      return self._carrot
    raise KeyError(key)


class TestCongestionCap(OpenpilotTestCase):
  """Pure-function coverage for the carrot TMC congestion cap."""

  def test_free_and_very_free_never_cap(self):
    for status in (1, 5):
      carrot = _FakeCarrotManSP(json.dumps([status]), json.dumps([100]))
      assert congestion_cap_ms(carrot) == 0.

  def test_unknown_statuses_never_cap(self):
    carrot = _FakeCarrotManSP(json.dumps([0, 10]), json.dumps([100, 100]))
    assert congestion_cap_ms(carrot) == 0.

  def test_status_maps_to_expected_speed(self):
    for status, kph in TMC_CONGESTION_SPEED_KPH.items():
      carrot = _FakeCarrotManSP(json.dumps([status]), json.dumps([100]))
      self.assertAlmostEqual(congestion_cap_ms(carrot), kph * CV.KPH_TO_MS)

  def test_worst_status_within_window_wins(self):
    carrot = _FakeCarrotManSP(json.dumps([1, 2, 4, 3]), json.dumps([100, 100, 100, 100]))
    self.assertAlmostEqual(congestion_cap_ms(carrot), 30 * CV.KPH_TO_MS)

  def test_congestion_beyond_lookahead_is_ignored(self):
    carrot = _FakeCarrotManSP(json.dumps([3]), json.dumps([int(TMC_LOOKAHEAD_M) + 1]))
    assert congestion_cap_ms(carrot) == 0.

  def test_malformed_payloads_are_ignored(self):
    assert congestion_cap_ms(_FakeCarrotManSP("not json", "")) == 0.
    assert congestion_cap_ms(_FakeCarrotManSP("", "")) == 0.
    assert congestion_cap_ms(_FakeCarrotManSP(json.dumps([]), json.dumps([]))) == 0.


class TestCongestionGating(OpenpilotTestCase):
  """The congestion fold-in must be off by default and only ever lower."""

  def setup_method(self):
    self.params = Params()
    self.params.put_bool("SmartCruiseControlMap", True, block=True)
    self.params.put("LastGPSPosition", "{}", block=True)
    self.params.put("MapTargetVelocities", "{}", block=True)
    self.scc_m = SmartCruiseControlMap()

  def test_disabled_by_default(self):
    # Killswitch default OFF: a congestion payload must not move the target.
    self.params.put_bool("CarrotTrafficCongestionEnabled", False, block=True)
    self.scc_m.use_carrot_congestion = False
    self.scc_m.v_target = 30.0
    sm = _FakeSM(_FakeCarrotManSP(json.dumps([4]), json.dumps([100])))
    self.scc_m._update_congestion(sm)
    assert self.scc_m.v_target == 30.0
    assert not self.scc_m.congestion_used

  def test_congestion_lowers_target(self):
    self.scc_m.use_carrot_congestion = True
    self.scc_m.v_target = 30.0
    sm = _FakeSM(_FakeCarrotManSP(json.dumps([3]), json.dumps([100])))
    self.scc_m._update_congestion(sm)
    self.assertAlmostEqual(self.scc_m.v_target, 40 * CV.KPH_TO_MS)
    assert self.scc_m.congestion_used

  def test_congestion_never_raises_target(self):
    self.scc_m.use_carrot_congestion = True
    self.scc_m.v_target = 10.0  # already slower than the 40 kph cap
    sm = _FakeSM(_FakeCarrotManSP(json.dumps([3]), json.dumps([100])))
    self.scc_m._update_congestion(sm)
    assert self.scc_m.v_target == 10.0
    assert not self.scc_m.congestion_used

  def test_stale_packet_is_ignored(self):
    self.scc_m.use_carrot_congestion = True
    self.scc_m.v_target = 30.0
    sm = _FakeSM(_FakeCarrotManSP(json.dumps([4]), json.dumps([100])), age=TMC_MAX_AGE_SEC + 1.0)
    self.scc_m._update_congestion(sm)
    assert self.scc_m.v_target == 30.0

  def test_inactive_carrot_is_ignored(self):
    self.scc_m.use_carrot_congestion = True
    self.scc_m.v_target = 30.0
    sm = _FakeSM(_FakeCarrotManSP(json.dumps([4]), json.dumps([100]), active=0))
    self.scc_m._update_congestion(sm)
    assert self.scc_m.v_target == 30.0

  def test_missing_service_is_ignored(self):
    self.scc_m.use_carrot_congestion = True
    self.scc_m.v_target = 30.0
    self.scc_m._update_congestion(_FakeSM(None))
    assert self.scc_m.v_target == 30.0

  def test_none_sm_is_tolerated(self):
    self.scc_m.use_carrot_congestion = True
    self.scc_m.v_target = 30.0
    self.scc_m._update_congestion(None)
    assert self.scc_m.v_target == 30.0
