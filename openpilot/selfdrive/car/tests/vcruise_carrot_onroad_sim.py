"""Onroad simulation harness for VCruiseCarrot.

Runs the real VCruiseCarrot against real pycapnp CarState / CarControl / CS_SP
messages, driving it through the exact sequence that happens on the car:

    offroad -> ignition -> cruise available -> SET engage -> button presses
             -> standstill -> gas/brake -> disengage

No openpilot process, no CAN, no device. This is how we catch the crashes that
only fire at engage time (signature mismatches, missing capnp fields, Params API
misuse) which py_compile and code review both miss.

Run from the repo root:
    PYTHONPATH=E:\\sp python .workbuddy/onroad_sim.py
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'opendbc_repo'))

# ---------------------------------------------------------------------------
# Params shim: sunnypilot's Params is a ctypes binding to libparams_c.so and
# does not exist on Windows. Provide the SAME public surface (get/get_bool/put/
# put_nonblocking/put_bool) so any call the real code makes is exercised.
# ---------------------------------------------------------------------------
_PARAM_TYPES = {
  'AutoEngage': int, 'UseLaneLineSpeed': int, 'AutoCruiseControl': int,
  'AutoGasTokSpeed': int, 'AutoGasCancelSpeed': int, 'AutoGasSyncSpeed': int,
  'SpeedFromPCM': int, 'CruiseSpeedUnit': int, 'CruiseButtonLongDelay': int,
  'CruiseSpeedUnitBasic': int, 'PaddleMode': int, 'CruiseButtonMode': int,
  'CancelButtonMode': int, 'LfaButtonMode': int, 'AutoRoadSpeedLimitOffset': int,
  'LongitudinalPersonalityMax': int, 'CruiseGapLevels': int, 'LongitudinalPersonality': int,
  'MyDrivingMode': int, 'ApplyModelSpeed': float, 'AutoSpeedUptoRoadSpeedLimit': float,
  'AutoRoadAdjust': float, 'AutoRoadSpeedAdjust': float, 'AutoNaviSpeedSafetyFactor': float,
  'CruiseOnDist': float, 'CruiseSpeed1': float, 'CruiseSpeed2': float, 'CruiseSpeed3': float,
  'CruiseSpeed4': float, 'CruiseSpeed5': float,
  'SoftHoldOnCancel': bool, 'DisengageOnAccelerator': bool, 'CarrotEnabled': bool,
}


def _defaults():
  store = {}
  for k, t in _PARAM_TYPES.items():
    store[k] = t() if t is not bool else False
  store.update({'CruiseSpeedUnit': 10, 'CruiseSpeedUnitBasic': 10, 'CruiseButtonLongDelay': 40,
                'LongitudinalPersonalityMax': 3, 'CruiseGapLevels': 4, 'AutoGasCancelSpeed': 30,
                'MyDrivingMode': 3, 'AutoNaviSpeedSafetyFactor': 100})
  return store


class FakeParams:
  def __init__(self, store=None):
    self._store = store if store is not None else _defaults()

  def get(self, key, block=False, return_default=False):
    v = self._store.get(key)
    if v is None:
      return None
    t = _PARAM_TYPES.get(key)
    if t is bool:
      return v == '1' or v is True
    if t is int:
      try:
        return int(v)
      except (TypeError, ValueError):
        return None
    if t is float:
      try:
        return float(v)
      except (TypeError, ValueError):
        return None
    # Untyped params come back as text in the real store
    if isinstance(v, bytes):
      return v.decode('utf-8', errors='replace')
    return v

  def get_bool(self, key, block=False):
    return bool(self.get(key))

  def put(self, key, dat, block=False):
    self._store[key] = dat

  def put_nonblocking(self, key, dat):
    self._store[key] = dat

  def put_bool(self, key, val, block=False):
    self._store[key] = val

  def remove(self, key):
    self._store.pop(key, None)


_params_mod = types.ModuleType('openpilot.common.params')
_params_mod.Params = FakeParams
sys.modules['openpilot.common.params'] = _params_mod

# swaglog pulls zmq, which is not installed here.
_cloudlog = types.SimpleNamespace(
  warning=lambda *a, **k: None, error=lambda *a, **k: None,
  info=lambda *a, **k: None, debug=lambda *a, **k: None, event=lambda *a, **k: None,
)
for mod_name in ('openpilot.common.swaglog',):
  m = types.ModuleType(mod_name)
  m.cloudlog = _cloudlog
  sys.modules[mod_name] = m

# fcntl / gpio are Linux-only and only used by hardware modules we never touch.
_fcntl = types.ModuleType('fcntl')
_fcntl.flock = lambda *a, **k: None
_fcntl.LOCK_EX = 2
_fcntl.LOCK_SH = 1
_fcntl.LOCK_NB = 4
_fcntl.ioctl = lambda *a, **k: 0
sys.modules['fcntl'] = _fcntl

_gpio = types.ModuleType('openpilot.common.gpio')
_gpio.gpio_set = lambda *a, **k: None
_gpio.gpio_init = lambda *a, **k: None
_gpio.gpio_read = lambda *a, **k: 0
_gpio.get_irqs_for_action = lambda *a, **k: []
sys.modules['openpilot.common.gpio'] = _gpio

_hw = types.ModuleType('openpilot.common.hardware')
_hw.PC = True
_hw.COMMA_HARDWARE = False
_hw.HARDWARE = types.SimpleNamespace(get_device_type=lambda: 'pc')
_hw.TICI = False
_hw.__path__ = []
sys.modules['openpilot.common.hardware'] = _hw

_hw_hw = types.ModuleType('openpilot.common.hardware.hw')
class _Paths:
  @staticmethod
  def config_root():
    return '/tmp/op_sim'
  @staticmethod
  def params_root():
    return '/dev/shm/params'
_hw_hw.Paths = _Paths
_hw_hw.HardwareBase = object
sys.modules['openpilot.common.hardware.hw'] = _hw_hw
_hw.hw = _hw_hw

_rt = types.ModuleType('openpilot.common.realtime')
_rt.DT_CTRL = 0.01
_rt.DT_MDL = 0.05
_rt.DT_DMON = 0.05
_rt.RATE = 100
sys.modules['openpilot.common.realtime'] = _rt

# The PC msgq shim is Python-2 syntax (octal literals), so anything importing
# openpilot.cereal.messaging transitively must be stubbed, not imported.
_msgq = types.ModuleType('msgq')
for _n in ('fake_event_handle', 'drain_sock_raw', 'MultiplePublishersError', 'IpcError',
           'Context', 'Poller', 'SubSocket', 'PubSocket', 'SocketEventHandle',
           'toggle_fake_events', 'set_fake_prefix', 'get_fake_prefix',
           'delete_fake_prefix', 'wait_for_one_event'):
  setattr(_msgq, _n, type(_n, (Exception,), {}) if 'Error' in _n else (lambda *a, **k: None))
sys.modules['msgq'] = _msgq

_messaging = types.ModuleType('openpilot.cereal.messaging')
for _n in ('SubMaster', 'PubMaster', 'new_message', 'log_from_bytes', 'drain_sock_raw',
           'sub_sock', 'pub_sock'):
  setattr(_messaging, _n, lambda *a, **k: None)
sys.modules['openpilot.cereal.messaging'] = _messaging

# EventsSP only needs the enum identity; the cruise helper never emits alerts here.
_events_mod = types.ModuleType('openpilot.sunnypilot.selfdrive.selfdrived.events')
class _EventsSP:
  def __init__(self, *a, **k):
    pass
_events_mod.EventsSP = _EventsSP
_events_mod.EventNameSP = types.SimpleNamespace()
sys.modules['openpilot.sunnypilot.selfdrive.selfdrived.events'] = _events_mod

from openpilot.selfdrive.car.cruise import VCruiseCarrot, ButtonType, GearShifter  # noqa: E402

# NO capnp.load() in this process, by design.
#
# Importing cruise.py already loads opendbc's car.capnp (via opendbc.car.structs).
# pycapnp aborts the interpreter (exit 127 / 0xC0000409) the moment a SECOND schema
# is loaded in the same process - regardless of order, even when the second schema
# is custom.capnp and even when it only re-imports the first. Verified both orders.
#
# So both CarState and CarStateSP are plain attribute objects here. They mirror the
# real field names exactly, which preserves the failure mode we care about: an
# access to a field that does not exist still raises AttributeError.
#
# Field-existence itself is verified separately, one schema per process, by
# .workbuddy/audit_one_schema.py (see verify_schemas.ps1).

PASS = 0
FAIL = 0


def step(name, fn):
  global PASS, FAIL
  try:
    fn()
  except Exception as e:  # noqa: BLE001
    FAIL += 1
    print(f'  FAIL  {name}: {type(e).__name__}: {e}')
  else:
    PASS += 1
    print(f'  ok    {name}')


class _ButtonEvent:
  """Stands in for capnp CarState.ButtonEvent.

    `type` must compare equal to cruise.py's ButtonType members the same way a
    capnp enum reader does, so we store the enum member itself.
    """
  def __init__(self, type_, pressed):
    self.type = type_
    self.pressed = pressed


class _CruiseState:
  def __init__(self, available, enabled, standstill, speed):
    self.available = available
    self.enabled = enabled
    self.standstill = standstill
    self.speed = speed
    self.speedCluster = speed


class _CarState:
  """Plain CarState stand-in.

    Deliberately NOT a capnp message: loading car.capnp and custom.capnp in the
    same process aborts pycapnp. Field names mirror opendbc's CarState exactly so
    an access to a field that does not exist still raises AttributeError here,
    which is the whole point of the simulation.
    """
  def __init__(self, v_ego=0.0, available=True, enabled=False, standstill=False,
               gear=None, buttons=(), gas_pressed=False, brake_pressed=False):
    self.vEgo = v_ego
    self.vEgoCluster = v_ego
    self.aEgo = 0.0
    self.steeringAngleDeg = 0.0
    self.gasPressed = gas_pressed
    self.brakePressed = brake_pressed
    self.brakeHoldActive = False
    self.parkingBrake = False
    self.gearShifter = gear if gear is not None else GearShifter.drive
    self.cruiseState = _CruiseState(available, enabled, standstill, v_ego)
    self.pcmCruiseGap = 0
    self.leftBlinker = False
    self.rightBlinker = False
    self.buttonEvents = [_ButtonEvent(getattr(ButtonType, t) if isinstance(t, str) else t, p)
                         for t, p in buttons]


def make_cs(v_ego=0.0, available=True, enabled=False, standstill=False, gear=None,
            buttons=(), gas_pressed=False, brake_pressed=False):
  return _CarState(v_ego=v_ego, available=available, enabled=enabled, standstill=standstill,
                   gear=gear, buttons=buttons, gas_pressed=gas_pressed, brake_pressed=brake_pressed)


class _CarStateSP:
  """Plain CarStateSP stand-in; mirrors custom.capnp's CarStateSP fields."""
  def __init__(self, big_step=False):
    self.speedLimit = 0.0
    self.carrotLaneValid = False
    self.carrotLeftLineBlocked = False
    self.carrotRightLineBlocked = False
    self.carrotLeftBlindHint = False
    self.carrotRightBlindHint = False
    self.carrotCruiseSpeedBigStep = big_step


def make_cs_sp(big_step=False):
  return _CarStateSP(big_step=big_step)


def make_sm(cs, cs_sp, enabled=False, alive=None):
  cc = types.SimpleNamespace(enabled=enabled)
  lp = types.SimpleNamespace(xState=0, trafficState=0, aTarget=0.0)
  rs = types.SimpleNamespace(leadOne=types.SimpleNamespace(dRel=0.0, vRel=0.0, vLeadK=0.0, present=False))
  dmd = types.SimpleNamespace(action=types.SimpleNamespace(desiredAcceleration=0.0))

  alive_map = {'longitudinalPlan': True, 'radarState': True, 'drivingModelData': True}
  if alive:
    alive_map.update(alive)

  services = {'carControl': cc, 'carrotManSP': None, 'longitudinalPlan': lp,
              'radarState': rs, 'drivingModelData': dmd}

  class SM:
    def __init__(self):
      self.alive = alive_map
      self.valid = {'carrotManSP': False, 'carStateSP': True}
      self.updated = {}
      self.frame = 0

    def __getitem__(self, k):
      v = services.get(k)
      if v is None:
        raise KeyError(k)
      return v

  return SM()


def build_cp(pcm_cruise=False, openpilot_long=True):
  return types.SimpleNamespace(pcmCruise=pcm_cruise, openpilotLongitudinalControl=openpilot_long,
                               brand='hyundai', carFingerprint='TEST')


def build_cp_sp():
  return types.SimpleNamespace(pcmCruiseSpeed=False)


print('=== VCruiseCarrot onroad simulation ===')

helper = VCruiseCarrot(build_cp(), build_cp_sp())
store = helper.params._store


def t_offroad_tick():
  cs = make_cs(v_ego=0.0, available=False)
  helper.update_v_cruise(cs, False, True, make_sm(cs, make_cs_sp()), make_cs_sp())


step('offroad tick (cruise unavailable)', t_offroad_tick)


def t_ignition_cruise_available():
  for _ in range(5):
    cs = make_cs(v_ego=0.0, available=True)
    helper.update_v_cruise(cs, False, True, make_sm(cs, make_cs_sp()), make_cs_sp())


step('cruise becomes available', t_ignition_cruise_available)


def t_set_engage():
  """Exactly the card.py call that raised the reported TypeError."""
  cs_prev = make_cs(v_ego=15.0, available=True)
  helper.initialize_v_cruise(cs_prev, False, False)


step('initialize_v_cruise(CS, experimental, dynamic) [the reported crash]', t_set_engage)


def t_engage_with_experimental():
  helper.initialize_v_cruise(make_cs(v_ego=15.0), True, False)
  helper.initialize_v_cruise(make_cs(v_ego=15.0), True, True)
  helper.initialize_v_cruise(make_cs(v_ego=15.0), False, True)


step('initialize_v_cruise across all experimental combinations', t_engage_with_experimental)


def t_button_press_cycle():
  buttons = ['accelCruise', 'decelCruise', 'setCruise', 'resumeCruise', 'cancel',
             'gapAdjustCruise', 'lfaButton']
  for btn in buttons:
    for pressed in (True, False):
      cs = make_cs(v_ego=15.0, available=True, buttons=[(btn, pressed)])
      helper.update_v_cruise(cs, True, True, make_sm(cs, make_cs_sp(), enabled=True), make_cs_sp())
      # Long-press path (button_cnt > 0 branch)
      helper.button_cnt = 5
      helper.update_v_cruise(cs, True, True, make_sm(cs, make_cs_sp(), enabled=True), make_cs_sp())


step('every ButtonType, press + release, short + long', t_button_press_cycle)


def t_vw_big_step_latch():
  cs = make_cs(v_ego=15.0, available=True, buttons=[('accelCruise', True)])
  helper.update_v_cruise(cs, True, True, make_sm(cs, make_cs_sp(big_step=True)), make_cs_sp(big_step=True))
  assert helper.button_big_step, 'big-step latch did not engage from CarStateSP'


step('VW stage-2 latch reads CarStateSP.carrotCruiseSpeedBigStep', t_vw_big_step_latch)


def t_paddle_buttons():
  for btn in ('paddleLeft', 'paddleRight'):
    cs = make_cs(v_ego=15.0, available=True, buttons=[(btn, True)])
    helper.update_v_cruise(cs, True, True, make_sm(cs, make_cs_sp()), make_cs_sp())


step('paddle buttons (cp-specific ButtonType enum members)', t_paddle_buttons)


def t_standstill_and_resume():
  cs = make_cs(v_ego=0.0, available=True, standstill=True, buttons=[('accelCruise', True)])
  helper.update_v_cruise(cs, True, True, make_sm(cs, make_cs_sp()), make_cs_sp())
  cs = make_cs(v_ego=0.0, available=True, standstill=True, buttons=[('accelCruise', False)])
  helper.update_v_cruise(cs, True, True, make_sm(cs, make_cs_sp()), make_cs_sp())


step('standstill + resume', t_standstill_and_resume)


def t_gas_and_brake():
  for _ in range(5):
    cs = make_cs(v_ego=15.0, available=True, gas_pressed=True)
    helper.update_v_cruise(cs, True, True, make_sm(cs, make_cs_sp(), enabled=True), make_cs_sp())
  for _ in range(5):
    cs = make_cs(v_ego=0.0, available=True, brake_pressed=True, standstill=True)
    helper.update_v_cruise(cs, True, True, make_sm(cs, make_cs_sp(), enabled=True), make_cs_sp())
  cs = make_cs(v_ego=15.0, available=True)
  helper.update_v_cruise(cs, True, True, make_sm(cs, make_cs_sp()), make_cs_sp())


step('gas pressed / brake pressed / soft-hold', t_gas_and_brake)


def t_gear_transitions():
  for gear in ('park', 'reverse', 'neutral', 'drive', 'sport', 'low', 'brake', 'eco', 'manumatic'):
    cs = make_cs(v_ego=15.0, available=True, gear=gear)
    helper.update_v_cruise(cs, True, True, make_sm(cs, make_cs_sp(), enabled=True), make_cs_sp())


step('every GearShifter value', t_gear_transitions)


def t_leads_and_plans():
  """Lead present/absent and plan-alive flips - the getattr-guarded reads."""
  for present in (True, False):
    for lp_alive in (True, False):
      cs = make_cs(v_ego=15.0, available=True)
      sm = make_sm(cs, make_cs_sp(), enabled=True,
                   alive={'longitudinalPlan': lp_alive, 'radarState': True, 'drivingModelData': True})
      sm['radarState'].leadOne = types.SimpleNamespace(dRel=50.0, vRel=-2.0, vLeadK=12.0, present=present)
      helper.update_v_cruise(cs, True, True, sm, make_cs_sp())


step('lead present/absent x longitudinalPlan alive/dead', t_leads_and_plans)


def t_no_submaster():
  """Base-class call shape: VCruiseHelper path with sm omitted."""
  for _ in range(3):
    cs = make_cs(v_ego=15.0, available=True)
    helper.update_v_cruise(cs, True, True)


step('update_v_cruise without sm (base-class call shape)', t_no_submaster)


def t_no_cs_sp():
  cs = make_cs(v_ego=15.0, available=True, buttons=[('accelCruise', True)])
  helper.update_v_cruise(cs, True, True, make_sm(cs, make_cs_sp()), None)


step('update_v_cruise with CS_SP=None', t_no_cs_sp)


def t_long_soak():
  import random
  random.seed(7)
  btns = ['accelCruise', 'decelCruise', 'setCruise', 'resumeCruise', 'cancel',
          'gapAdjustCruise', 'lfaButton', 'paddleLeft', 'paddleRight']
  for i in range(4000):
    pressed = random.random() < 0.5
    buttons = [(random.choice(btns), pressed)] if random.random() < 0.6 else []
    cs = make_cs(v_ego=random.uniform(0, 35), available=random.random() < 0.9,
                 standstill=random.random() < 0.1,
                 gear=random.choice(['drive', 'drive', 'drive', 'park']),
                 buttons=buttons, gas_pressed=random.random() < 0.1,
                 brake_pressed=random.random() < 0.1)
    if i % 10 == 0:
      helper.update_v_cruise(cs, True, True, make_sm(cs, make_cs_sp(), enabled=True), make_cs_sp())
    else:
      helper.update_v_cruise(cs, True, True, make_sm(cs, make_cs_sp()), make_cs_sp())


step('4000-tick randomized soak', t_long_soak)


print()
print(f'PASSED {PASS}, FAILED {FAIL}')
sys.exit(1 if FAIL else 0)
