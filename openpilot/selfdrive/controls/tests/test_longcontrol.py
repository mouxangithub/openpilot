from openpilot.common.test import OpenpilotTestCase
from opendbc.car.structs import car
from openpilot.cereal import custom
from openpilot.common.realtime import DT_CTRL
from openpilot.selfdrive.controls.lib.drive_helpers import STOPPING_SPEED, should_stop
from openpilot.selfdrive.controls.lib.longcontrol import STOPPING_DECEL_RATE, LongControl, LongCtrlState, long_control_state_trans


class TestLongControlStateTransition(OpenpilotTestCase):

  def test_stay_stopped(self):
    CP_SP = custom.CarParamsSP.new_message()
    active = True
    current_state = LongCtrlState.stopping
    next_state = long_control_state_trans(CP_SP, active, current_state,
                             should_stop=True, brake_pressed=False, cruise_standstill=False)
    assert next_state == LongCtrlState.stopping
    next_state = long_control_state_trans(CP_SP, active, current_state,
                             should_stop=False, brake_pressed=True, cruise_standstill=False)
    assert next_state == LongCtrlState.stopping
    next_state = long_control_state_trans(CP_SP, active, current_state,
                             should_stop=False, brake_pressed=False, cruise_standstill=True)
    assert next_state == LongCtrlState.stopping
    next_state = long_control_state_trans(CP_SP, active, current_state,
                             should_stop=False, brake_pressed=False, cruise_standstill=False)
    assert next_state == LongCtrlState.pid
    active = False
    next_state = long_control_state_trans(CP_SP, active, current_state,
                             should_stop=False, brake_pressed=False, cruise_standstill=False)
    assert next_state == LongCtrlState.off

  def test_engage(self):
    CP_SP = custom.CarParamsSP.new_message()
    active = True
    current_state = LongCtrlState.off
    next_state = long_control_state_trans(CP_SP, active, current_state,
                             should_stop=True, brake_pressed=False, cruise_standstill=False)
    assert next_state == LongCtrlState.stopping
    next_state = long_control_state_trans(CP_SP, active, current_state,
                             should_stop=False, brake_pressed=True, cruise_standstill=False)
    assert next_state == LongCtrlState.stopping
    next_state = long_control_state_trans(CP_SP, active, current_state,
                             should_stop=False, brake_pressed=False, cruise_standstill=True)
    assert next_state == LongCtrlState.stopping
    next_state = long_control_state_trans(CP_SP, active, current_state,
                             should_stop=False, brake_pressed=False, cruise_standstill=False)
    assert next_state == LongCtrlState.pid


class TestTerminalStop(OpenpilotTestCase):
  def test_stopping_tune_is_gentler_than_upstream_default(self):
    # Upstream #38394 hardcoded a 1.0 m/s^2/s ramp and a 0.3 m/s latch. comma's own one-stopping-tune uses
    # 0.3 / 0.25, and every stop recorded on this car was driven with that pair. Both must stay on the less
    # braking side, or a future edit re-deepens the terminal brake unnoticed - which already happened once.
    assert 0.0 < STOPPING_DECEL_RATE <= 1.0
    assert 0.0 < STOPPING_SPEED <= 0.3
    assert should_stop(STOPPING_SPEED - 0.01, 0.0)
    assert not should_stop(0.29, 0.0)  # the band upstream would latch in and we do not

  def test_stopping_caps_a_hard_pid_brake(self):
    cp = car.CarParams.new_message()
    cp.stopAccel = -2.0
    cp.longitudinalTuning.kiBP = [0.0]
    cp.longitudinalTuning.kiV = [0.0]
    cp_sp = custom.CarParamsSP.new_message()
    cs = car.CarState.new_message()
    cs.vEgo = 0.2
    cs.cruiseState.standstill = False

    long_control = LongControl(cp, cp_sp)
    long_control.long_control_state = LongCtrlState.pid
    long_control.last_output_accel = -3.5

    output_accel = long_control.update(True, cs, 0.0, True, (-3.5, 2.0))

    assert output_accel == cp.stopAccel
    assert output_accel > -3.5
