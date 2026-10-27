"""CP-1 lever_maneuver port tests (PC-safe, run with pytest --noconftest).

Covers:
- the pure lever_maneuver decision table (ported from carrot desire_lib/lever.py)
- LaneTurnController integration: latched / one-touch / released lever semantics
  when carState.blinkerLever is present and BlinkerLatchedTurn is enabled
- fallback equivalence: cars without the lever signal (getattr -> None, e.g.
  Toyota) and with the param off behave exactly like the legacy blinker path
"""
import sys
import types

# common.params -> swaglog -> common.hardware -> gpio imports fcntl at module
# load on Linux; a bare module keeps the import chain alive on PC hosts.
try:
  import fcntl  # noqa: F401
except ImportError:
  sys.modules.setdefault('fcntl', types.ModuleType('fcntl'))

# common.params loads libparams_c.so via ctypes at import time; no Windows build
# exists. Same stub pattern as test_conditional_experimental_mode.py; every
# LaneTurnController here is built with a dict-backed fake Params.
try:
  from openpilot.common.params import Params  # noqa: F401
except (OSError, FileNotFoundError):
  _params_mod = types.ModuleType('openpilot.common.params')

  class _ParamsStub:
    def __init__(self, *args, **kwargs):
      raise RuntimeError("real Params is unavailable on PC; inject a fake in tests")

  _params_mod.Params = _ParamsStub
  sys.modules['openpilot.common.params'] = _params_mod

from types import SimpleNamespace

from openpilot.cereal import custom
from openpilot.common.constants import CV
from openpilot.sunnypilot.selfdrive.controls.lib.lever import (
  LEVER_LATCHED,
  LEVER_ONE_TOUCH,
  LEVER_RELEASED,
  lever_maneuver,
)
from openpilot.sunnypilot.selfdrive.controls.lib.lane_turn_desire import (
  BLINKER_LATCHED_TURN_DEFAULT,
  LaneTurnController,
)

TurnDirection = custom.ModelDataV2SP.TurnDirection

TURN_SPEED_MAX = 30 * CV.KPH_TO_MS  # 8.33 m/s


class FakeParams:
  """Dict-backed Params double: get(key) -> value or None; no registered keys needed."""

  def __init__(self, data=None):
    self._data = dict(data or {})

  def get(self, key, **kwargs):
    return self._data.get(key)

  def get_bool(self, key):
    value = self._data.get(key)
    return str(value).strip().lower() in ("1", "true", "yes", "on") if value is not None else False


class CarStateWithLever:
  """CarState double that exposes carState.blinkerLever (Hyundai CAN-FD style)."""

  def __init__(self, lever):
    self.blinkerLever = lever


class CarStateWithoutLever:
  """CarState double for cars without the signal (SP car.capnp / Toyota): the
  attribute does not exist, getattr(..., None) -> None."""


def make_controller(blinker_latched_turn_kph=None):
  params = FakeParams({"LaneTurnValue": "20", "LaneTurnDesire": "1"})
  controller = LaneTurnController(None, params=params)
  controller.enabled = True
  controller.lane_turn_value = 20 * CV.MPH_TO_MS
  if blinker_latched_turn_kph is not None:
    controller.blinker_latched_turn = blinker_latched_turn_kph * CV.KPH_TO_MS
  else:
    controller.blinker_latched_turn = BLINKER_LATCHED_TURN_DEFAULT * CV.KPH_TO_MS
  controller.turn_direction = TurnDirection.none
  return controller


class TestLeverManeuverPure:
  def test_off_when_speed_gate_zero(self):
    assert lever_maneuver(LEVER_LATCHED, 5.0, 0.0) == (None, False)
    assert lever_maneuver(LEVER_LATCHED, 5.0, -1.0) == (None, False)

  def test_above_speed_gate_is_lane_change(self):
    assert lever_maneuver(LEVER_LATCHED, TURN_SPEED_MAX + 0.1, TURN_SPEED_MAX) == ("lane_change", False)
    assert lever_maneuver(LEVER_ONE_TOUCH, TURN_SPEED_MAX + 5.0, TURN_SPEED_MAX) == ("lane_change", False)

  def test_forced_turn_gesture_is_turn(self):
    assert lever_maneuver(LEVER_LATCHED, 5.0, TURN_SPEED_MAX, forced_turn=True) == ("turn", False)

  def test_one_touch_below_gate_is_undecided_lane_change(self):
    assert lever_maneuver(LEVER_ONE_TOUCH, 5.0, TURN_SPEED_MAX) == ("lane_change", True)

  def test_plain_latch_below_gate_is_decided_lane_change(self):
    assert lever_maneuver(LEVER_LATCHED, 5.0, TURN_SPEED_MAX) == ("lane_change", False)

  def test_speed_gate_boundary_is_inclusive(self):
    # at exactly turn_speed_max the lever still decides (not "above it")
    assert lever_maneuver(LEVER_ONE_TOUCH, TURN_SPEED_MAX, TURN_SPEED_MAX) == ("lane_change", True)


class TestLaneTurnControllerWithLever:
  """blinkerLever present + BlinkerLatchedTurn enabled: lever semantics take priority."""

  def test_latched_left_blinker_is_turn(self):
    controller = make_controller(blinker_latched_turn_kph=30)
    controller.update_lane_turn(False, False, True, False, 5.0, CarStateWithLever(LEVER_LATCHED))
    assert controller.get_turn_direction() == TurnDirection.turnLeft

  def test_latched_right_blinker_is_turn(self):
    controller = make_controller(blinker_latched_turn_kph=30)
    controller.update_lane_turn(False, False, False, True, 5.0, CarStateWithLever(LEVER_LATCHED))
    assert controller.get_turn_direction() == TurnDirection.turnRight

  def test_one_touch_is_not_a_turn(self):
    controller = make_controller(blinker_latched_turn_kph=30)
    controller.update_lane_turn(False, False, True, False, 5.0, CarStateWithLever(LEVER_ONE_TOUCH))
    assert controller.get_turn_direction() == TurnDirection.none

  def test_above_speed_gate_even_latched_is_not_a_turn(self):
    controller = make_controller(blinker_latched_turn_kph=30)
    controller.update_lane_turn(False, False, True, False, TURN_SPEED_MAX + 0.5, CarStateWithLever(LEVER_LATCHED))
    assert controller.get_turn_direction() == TurnDirection.none

  def test_both_blinkers_is_not_a_turn(self):
    controller = make_controller(blinker_latched_turn_kph=30)
    controller.update_lane_turn(False, False, True, True, 5.0, CarStateWithLever(LEVER_LATCHED))
    assert controller.get_turn_direction() == TurnDirection.none

  def test_released_lever_falls_back_to_legacy(self):
    # released lever gives no lever information: the legacy blinker decision applies
    controller = make_controller(blinker_latched_turn_kph=30)
    controller.update_lane_turn(False, False, True, False, 5.0, CarStateWithLever(LEVER_RELEASED))
    assert controller.get_turn_direction() == TurnDirection.turnLeft


class TestLaneTurnControllerFallbackEquivalence:
  """No lever signal / feature off: behavior must equal the legacy blinker path."""

  # (left_blinker, right_blinker, v_ego, blindspot_left, blindspot_right, expected)
  LEGACY_TABLE = [
    (True, False, 5.0, False, False, TurnDirection.turnLeft),
    (False, True, 6.0, False, False, TurnDirection.turnRight),
    (True, False, 9.0, False, False, TurnDirection.none),   # above lane turn speed
    (True, False, 7.0, True, False, TurnDirection.none),    # blindspot
    (False, True, 6.0, False, True, TurnDirection.none),    # blindspot
    (False, False, 5.0, False, False, TurnDirection.none),
    (True, True, 5.0, False, False, TurnDirection.none),
  ]

  def _assert_all(self, controller, carstate):
    for left, right, v_ego, bsl, bsr, expected in self.LEGACY_TABLE:
      controller.turn_direction = TurnDirection.none
      controller.update_lane_turn(bsl, bsr, left, right, v_ego, carstate)
      assert controller.get_turn_direction() == expected

  def test_no_carstate_matches_legacy(self):
    self._assert_all(make_controller(), None)

  def test_carstate_without_signal_matches_legacy(self):
    # getattr(carstate, "blinkerLever", None) -> None: Toyota and stock SP car.capnp
    self._assert_all(make_controller(), CarStateWithoutLever())

  def test_signal_present_but_param_off_matches_legacy(self):
    # BlinkerLatchedTurn defaults to 0 (off): even a latched lever must not change anything
    self._assert_all(make_controller(), CarStateWithLever(LEVER_LATCHED))

  def test_latched_lever_does_not_change_legacy_results_when_off(self):
    controller = make_controller()
    controller.update_lane_turn(False, False, True, False, 5.0, CarStateWithLever(LEVER_LATCHED))
    assert controller.get_turn_direction() == TurnDirection.turnLeft
    controller.turn_direction = TurnDirection.none
    controller.update_lane_turn(False, False, False, True, 6.0, CarStateWithLever(LEVER_LATCHED))
    assert controller.get_turn_direction() == TurnDirection.turnRight


class TestParamReading:
  def test_unregistered_key_falls_back_to_default(self):
    # FakeParams returns None for unregistered keys -> code default 0.0 (off)
    controller = make_controller()
    assert controller.blinker_latched_turn == 0.0

  def test_read_params_picks_up_value(self):
    params = FakeParams({"LaneTurnValue": "20", "LaneTurnDesire": "1", "BlinkerLatchedTurn": "25"})
    controller = LaneTurnController(None, params=params)
    controller.param_read_counter = 0
    controller.read_params()
    assert controller.blinker_latched_turn == 25 * CV.KPH_TO_MS

  def test_read_params_bad_value_falls_back_to_default(self):
    params = FakeParams({"LaneTurnValue": "20", "LaneTurnDesire": "1", "BlinkerLatchedTurn": "abc"})
    controller = LaneTurnController(None, params=params)
    controller.read_params()
    assert controller.blinker_latched_turn == 0.0


class TestDesireHelperPassesCarstate:
  def test_desire_helper_forwards_carstate(self):
    # regression guard for the one-line desire_helper.py change: the call site
    # forwards carstate so the controller can read blinkerLever. Read from the
    # source file to keep this test independent of the desire_helper import chain.
    from pathlib import Path
    helper = Path(__file__).resolve().parents[5] / "selfdrive" / "controls" / "lib" / "desire_helper.py"
    source = helper.read_text(encoding="utf-8")
    assert "carstate=carstate" in source
