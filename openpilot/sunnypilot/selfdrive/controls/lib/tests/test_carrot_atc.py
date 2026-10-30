"""CarrotPilot ATC semantics tests for the rewritten DesireHelper synthetic-blinker path.

PC-runnable: stubs fcntl and the native Params backend before imports.
Device: PYTHONPATH="/data/openpilot" python -m unittest openpilot.sunnypilot.selfdrive.controls.lib.tests.test_carrot_atc
"""
import sys
import types
import unittest
from types import SimpleNamespace

# --- PC import stubs (must run before any openpilot import) -----------------
if 'fcntl' not in sys.modules or not hasattr(sys.modules.get('fcntl'), 'flock'):
  _fcntl = types.ModuleType('fcntl')
  _fcntl.flock = lambda *a, **k: None
  _fcntl.lockf = lambda *a, **k: None
  _fcntl.ioctl = lambda *a, **k: 0
  _fcntl.LOCK_EX, _fcntl.LOCK_SH, _fcntl.LOCK_UN, _fcntl.LOCK_NB = 2, 1, 8, 4
  sys.modules['fcntl'] = _fcntl

try:
  from openpilot.common.params import Params  # noqa: F401  (probe the native backend)
except Exception:
  class Params:  # noqa: E704  (PC fallback: no libparams_c.so)
    _store: dict[str, str] = {}

    def __init__(self, *args, **kwargs):
      pass

    @classmethod
    def _reset(cls):
      cls._store = {}

    def get_bool(self, key, return_default=False, **kwargs):
      return self._store.get(key, "0") == "1"

    def get_int(self, key, return_default=False, **kwargs):
      try:
        return int(self._store.get(key, "0"))
      except (TypeError, ValueError):
        return 0

    def get(self, key, encoding=None, return_default=False, **kwargs):
      # real Params casts INT-typed keys to int (common/params.py ParamKeyType.INT);
      # mirror that so int comparisons like lane_change_set_timer in (OFF, NUDGE) hold.
      value = self._store.get(key)
      if value is None:
        return 0 if return_default else None
      try:
        return int(value)
      except (TypeError, ValueError):
        return value

    def put(self, key, value, **kwargs):
      if value is True or value == "1":
        value = "1"
      elif value is False or value == "0":
        value = "0"
      else:
        value = str(value)
      self._store[key] = value

  # The real module raises during its own import (CDLL at module level), so it is
  # not left in sys.modules: install the stub module wholesale.
  _params_mod = types.ModuleType('openpilot.common.params')
  _params_mod.Params = Params
  sys.modules['openpilot.common.params'] = _params_mod

from openpilot.cereal import log, custom  # noqa: E402

from openpilot.selfdrive.controls.lib.desire_helper import (  # noqa: E402
  DesireHelper, BLINKER_LEFT, BLINKER_RIGHT,
)
from openpilot.sunnypilot.selfdrive.controls.lib.auto_lane_change import AutoLaneChangeMode  # noqa: E402

TurnDirection = custom.ModelDataV2SP.TurnDirection


def make_carstate(**overrides):
  state = dict(
    vEgo=25.0,  # above LANE_CHANGE_SPEED_MIN
    leftBlinker=False, rightBlinker=False,
    leftBlindspot=False, rightBlindspot=False,
    canValid=True, steeringPressed=False, steeringTorque=0.0, brakePressed=False,
  )
  state.update(overrides)
  return SimpleNamespace(**state)


def make_carrot_man(atc_type="", carrot_cmd="", carrot_arg="", carrot_cmd_index=0):
  return SimpleNamespace(atcType=atc_type, carrotCmd=carrot_cmd, carrotArg=carrot_arg,
                         carrotCmdIndex=carrot_cmd_index)


def frames(dh, n, carstate=None, carrot_man=None, radar_state=None, **kwargs):
  desire = None
  for _ in range(n):
    desire = dh.update(carstate or make_carstate(), True, 0.0,
                       carrot_man=carrot_man, radar_state=radar_state, **kwargs)
  return desire


def reset_params():
  """Reset only the keys this suite touches.

  PC stub: in-memory dict reset. Device (real libparams): remove() the keys so
  other vehicle settings stored in /data/params are left untouched.
  """
  if hasattr(Params, "_reset"):
    Params._reset()
  else:
    p = Params()
    for key in ("CarrotAtcBlinkerEnabled", "AutoLaneChangeTimer", "LaneChangeNeedTorque"):
      try:
        p.remove(key)
      except Exception:
        pass


class TestCarrotAtc(unittest.TestCase):
  def setUp(self):
    reset_params()

  def _atc_dh(self):
    # real Params type-checks: BOOL keys must be written as bool, INT as int
    Params().put("CarrotAtcBlinkerEnabled", True)
    dh = DesireHelper()
    dh.alc.lane_change_set_timer = AutoLaneChangeMode.NUDGE  # default: ATC lamp may act alone
    return dh

  def test_killswitch_off_no_synthetic_blinker(self):
    dh = DesireHelper()  # CarrotAtcBlinkerEnabled defaults off
    frames(dh, 3, carrot_man=make_carrot_man("fork right"))
    self.assertEqual(dh.carrot_virtual_blinker, 0)
    self.assertFalse(dh.carrot_atc_active)
    self.assertEqual(dh.lane_change_state, log.LaneChangeState.off)

  def test_fork_right_auto_lane_change(self):
    """导航 fork right：无驾驶员转向灯时虚拟灯独立进入 FSM 并自动启动（cp 语义修复点）。"""
    dh = self._atc_dh()
    frames(dh, 3, carrot_man=make_carrot_man("fork right"))
    self.assertEqual(dh.carrot_virtual_blinker, BLINKER_RIGHT)
    self.assertTrue(dh.carrot_atc_active)
    self.assertEqual(dh.lane_change_state, log.LaneChangeState.laneChangeStarting)
    self.assertEqual(dh.lane_change_direction, log.LaneChangeDirection.right)

  def test_fork_left_manual_only(self):
    """cp: 左侧 fork 需要驾驶员确认，不自动启动。"""
    dh = self._atc_dh()
    frames(dh, 3, carrot_man=make_carrot_man("fork left"))
    self.assertEqual(dh.carrot_virtual_blinker, BLINKER_LEFT)
    self.assertEqual(dh.lane_change_state, log.LaneChangeState.preLaneChange)

  def test_turn_type_gives_turn_desire(self):
    dh = self._atc_dh()
    frames(dh, 3, carrot_man=make_carrot_man("turn right"))
    self.assertEqual(dh.lane_turn_direction, TurnDirection.turnRight)
    self.assertEqual(dh.desire, log.Desire.turnRight)
    self.assertEqual(dh.lane_change_state, log.LaneChangeState.off)

  def test_type_change_debounce_one_frame(self):
    dh = self._atc_dh()
    dh.update(make_carstate(), True, 0.0, carrot_man=make_carrot_man("fork right"))
    # first frame on a fresh type is ignored
    self.assertEqual(dh.lane_change_state, log.LaneChangeState.off)

  def test_driver_opposite_blinker_conflict(self):
    dh = self._atc_dh()
    frames(dh, 3, make_carstate(rightBlinker=True), carrot_man=make_carrot_man("fork left"))
    self.assertEqual(dh.atc_active, 2)
    self.assertEqual(dh.carrot_virtual_blinker, 0)
    self.assertEqual(dh.lane_change_direction, log.LaneChangeDirection.right)

  def test_bsd_blocks_atc_start(self):
    dh = self._atc_dh()
    frames(dh, 3, make_carstate(rightBlindspot=True), carrot_man=make_carrot_man("fork right"))
    self.assertNotEqual(dh.lane_change_state, log.LaneChangeState.laneChangeStarting)

  def test_side_radar_object_blocks_atc_start(self):
    dh = self._atc_dh()
    lead = SimpleNamespace(present=True, dRel=4.0, vRel=0.0, vLead=0.0, radarTrackId=7)
    radar_state = SimpleNamespace(leadLeft=SimpleNamespace(present=False), leadRight=lead,
                                  leadsLeft=(), leadsRight=(lead,))
    frames(dh, 3, carrot_man=make_carrot_man("fork right"), radar_state=radar_state)
    self.assertNotEqual(dh.lane_change_state, log.LaneChangeState.laneChangeStarting)

  def test_opposite_torque_cancels_and_ignores_atc(self):
    dh = self._atc_dh()
    frames(dh, 3, carrot_man=make_carrot_man("fork right"))
    self.assertEqual(dh.lane_change_state, log.LaneChangeState.laneChangeStarting)
    # opposite torque (leftward = positive) cancels the right change and latches blinker_ignore
    dh.update(make_carstate(steeringPressed=True, steeringTorque=2.0), True, 0.0,
              carrot_man=make_carrot_man("fork right"))
    self.assertEqual(dh.lane_change_state, log.LaneChangeState.off)
    self.assertTrue(dh.blinker_ignore)

  def test_server_lanechange_command_forces(self):
    dh = self._atc_dh()
    carrot_man = make_carrot_man("", carrot_cmd="LANECHANGE", carrot_arg="RIGHT", carrot_cmd_index=100)
    frames(dh, 3, carrot_man=carrot_man)
    self.assertEqual(dh.lane_change_state, log.LaneChangeState.laneChangeStarting)
    self.assertEqual(dh.lane_change_direction, log.LaneChangeDirection.right)


if __name__ == "__main__":
  unittest.main()
