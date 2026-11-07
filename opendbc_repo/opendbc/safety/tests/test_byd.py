#!/usr/bin/env python3
import unittest

from opendbc.car.structs import CarParams
from opendbc.safety.tests.libsafety import libsafety_py
import opendbc.safety.tests.common as common
from opendbc.safety.tests.common import CANPackerSafety

BYD_CANBUS_ESC = 0
BYD_CANBUS_MPC = 2

BYD_FLAG_HAN_TANG_DMEV = 0x1
BYD_FLAG_TANG_DMI = 0x2
BYD_FLAG_SONG_PLUS_DMI = 0x4
BYD_FLAG_QIN_PLUS_DMI = 0x8
BYD_FLAG_YUAN_PLUS_DMI_ATTO3 = 0x10
BYD_FLAG_ATTO3_GENERAL = 0x20

BYD_COMMON_TX_MSGS = [
  [0x32E, BYD_CANBUS_ESC],  # ACC_CMD
  [0x316, BYD_CANBUS_ESC],  # ACC_MPC_STATE
  [0x318, BYD_CANBUS_MPC],  # ACC_EPS_STATE
]

BYD_RELAY_MALFUNCTION_ADDRS = {BYD_CANBUS_ESC: (0x316,)}
BYD_FWD_BLACKLISTED_ADDRS = {
  BYD_CANBUS_ESC: [0x318],
  BYD_CANBUS_MPC: [0x316, 0x32E],
}

BYD_ATTO3_GENERAL_TX_MSGS = [
  [0x1E2, BYD_CANBUS_ESC],  # STEERING_MODULE_ADAS
  [0x316, BYD_CANBUS_ESC],  # LKAS_HUD_ADAS
]

BYD_ANGLE_GENERIC_TX_MSGS = [
  [0x1E2, BYD_CANBUS_ESC],  # CID_TCDUBH angle command
  [0x32D, BYD_CANBUS_ESC],  # CID_XQYNBW ACC HUD
  [0x32E, BYD_CANBUS_ESC],  # CID_RJDCMR ACC CMD
  [0x3B0, BYD_CANBUS_ESC],  # CID_YHMGPU PCM buttons
]

BYD_ATTO3_RELAY_MALFUNCTION_ADDRS = {BYD_CANBUS_ESC: (0x1E2,)}
BYD_ATTO3_FWD_BLACKLISTED_ADDRS = {
  BYD_CANBUS_MPC: [0x1E2, 0x316],
}
BYD_ATTO3_FWD_BUS_LOOKUP = {BYD_CANBUS_ESC: BYD_CANBUS_MPC, BYD_CANBUS_MPC: BYD_CANBUS_ESC}

BYD_ANGLE_GENERIC_RELAY_MALFUNCTION_ADDRS = {BYD_CANBUS_ESC: (0x1E2,)}
BYD_ANGLE_GENERIC_FWD_BLACKLISTED_ADDRS = {
  BYD_CANBUS_MPC: [0x1E2],
}
BYD_ANGLE_GENERIC_FWD_BUS_LOOKUP = {BYD_CANBUS_ESC: BYD_CANBUS_MPC, BYD_CANBUS_MPC: BYD_CANBUS_ESC}

BYD_FLAG_ANGLE_MODE = 0x100


class BydSafetyBase(common.CarSafetyTest, common.MotorTorqueSteeringSafetyTest):
  TX_MSGS = BYD_COMMON_TX_MSGS
  RELAY_MALFUNCTION_ADDRS = BYD_RELAY_MALFUNCTION_ADDRS
  FWD_BLACKLISTED_ADDRS = BYD_FWD_BLACKLISTED_ADDRS

  MAX_RATE_UP = 17
  MAX_RATE_DOWN = 17
  MAX_TORQUE_LOOKUP = [0], [300]
  MAX_RT_DELTA = 243
  MAX_TORQUE_ERROR = 80
  TORQUE_MEAS_TOLERANCE = 0

  FLAGS = 0

  def setUp(self):
    # common.SafetyTestBase.setUp re-applies the hooks from these; set them to
    # match what this Base configures so the super() call is a no-op repeat.
    # super().setUp() re-initializes the safety state, so the CruiseActivated
    # precondition has to be fed after it, not before.
    self.SAFETY_MODEL = CarParams.SafetyModel.byd
    self.SAFETY_PARAM = self.FLAGS
    self.packer = CANPackerSafety("byd_han_dmev_2020")
    self.safety = libsafety_py.libsafety
    self.safety.set_safety_hooks(CarParams.SafetyModel.byd, self.FLAGS)
    self.safety.init_tests()
    super().setUp()
    # BYD requires CruiseActivated from ACC_EPS_STATE before LKAS_Active counts as a steer request
    self._rx(self._acc_eps_state_msg(cruise_activated=True))

  def _acc_eps_state_msg(self, cruise_activated=False, torque=0):
    values = {"CruiseActivated": int(cruise_activated), "MainTorque": torque}
    return self.packer.make_can_msg_safety("ACC_EPS_STATE", BYD_CANBUS_ESC, values)

  def _torque_cmd_msg(self, torque, steer_req=1):
    values = {"LKAS_Output": torque, "LKAS_Active": steer_req}
    return self.packer.make_can_msg_safety("ACC_MPC_STATE", BYD_CANBUS_ESC, values)

  def _torque_meas_msg(self, torque):
    return self._acc_eps_state_msg(torque=torque)

  def _speed_msg(self, speed):
    values = {"CarDisplaySpeed": speed}
    return self.packer.make_can_msg_safety("CARSPEED", BYD_CANBUS_ESC, values)

  def _speed_msg_2(self, speed: float):
    return None

  def _user_brake_msg(self, brake):
    values = {"BrakePedal": int(brake)}
    return self.packer.make_can_msg_safety("PEDAL", BYD_CANBUS_ESC, values)

  def _user_gas_msg(self, gas):
    values = {"AcceleratorPedal": int(gas)}
    return self.packer.make_can_msg_safety("PEDAL", BYD_CANBUS_ESC, values)

  def _pcm_status_msg(self, enable):
    values = {"AccState": 3 if enable else 0}
    return self.packer.make_can_msg_safety("ACC_HUD_ADAS", BYD_CANBUS_MPC, values)

  # MADS button / ACC main are not wired up for BYD; leave abstract to skip those tests
  def _lkas_button_msg(self, enabled):
    raise NotImplementedError

  def _acc_state_msg(self, enabled):
    # AccState=2 is ACC_ON (main switch on, not yet active), which sets acc_main_on without engaging cruise
    values = {"AccState": 2 if enabled else 0}
    return self.packer.make_can_msg_safety("ACC_HUD_ADAS", BYD_CANBUS_MPC, values)


class TestBydSafety(BydSafetyBase):
  FLAGS = BYD_FLAG_HAN_TANG_DMEV

  def _switch_platform(self, flags):
    self.safety.set_safety_hooks(CarParams.SafetyModel.byd, flags)
    self.safety.init_tests()
    self._rx(self._acc_eps_state_msg(cruise_activated=True))

  def test_steer_req_requires_cruise_activated(self):
    self.safety.set_controls_allowed(True)
    self._set_prev_torque(self.MAX_TORQUE)

    # Without CruiseActivated the steer request bit is ignored -> blocked
    self.safety.init_tests()
    self._rx(self._acc_eps_state_msg(cruise_activated=False))
    self.assertFalse(self._tx(self._torque_cmd_msg(self.MAX_TORQUE, steer_req=1)))

    # With CruiseActivated, torque is allowed
    self._rx(self._acc_eps_state_msg(cruise_activated=True))
    self.assertTrue(self._tx(self._torque_cmd_msg(self.MAX_TORQUE, steer_req=1)))

  def _assert_platform_torque_allowed(self, flags):
    self._switch_platform(flags)
    self.safety.set_controls_allowed(True)
    self._set_prev_torque(self.MAX_TORQUE)
    self.assertTrue(self._tx(self._torque_cmd_msg(self.MAX_TORQUE)))

  def test_tang_dmi_safety_config(self):
    self._assert_platform_torque_allowed(BYD_FLAG_TANG_DMI)

  def test_song_plus_dmi_safety_config(self):
    self._assert_platform_torque_allowed(BYD_FLAG_SONG_PLUS_DMI)

  def test_qin_plus_dmi_safety_config(self):
    self._assert_platform_torque_allowed(BYD_FLAG_QIN_PLUS_DMI)

  def test_default_safety_config(self):
    # param = 0 falls back to the HAN/Tang DM-i config
    self._switch_platform(0)
    self.safety.set_controls_allowed(True)
    self._set_prev_torque(self.MAX_TORQUE)
    self.assertTrue(self._tx(self._torque_cmd_msg(self.MAX_TORQUE)))


class BydAtto3GeneralSafetyBase(common.CarSafetyTest, common.AngleSteeringSafetyTest):
  TX_MSGS = BYD_ATTO3_GENERAL_TX_MSGS
  RELAY_MALFUNCTION_ADDRS = BYD_ATTO3_RELAY_MALFUNCTION_ADDRS
  FWD_BLACKLISTED_ADDRS = BYD_ATTO3_FWD_BLACKLISTED_ADDRS
  FWD_BUS_LOOKUP = BYD_ATTO3_FWD_BUS_LOOKUP

  # Angle control limits (mirror CarControllerParams.ANGLE_LIMITS)
  STEER_ANGLE_MAX = 90
  DEG_TO_CAN = 10

  ANGLE_RATE_BP = [0., 5., 25.]
  ANGLE_RATE_UP = [2.5, 1.5, 0.4]   # windup limit per message (50 Hz)
  ANGLE_RATE_DOWN = [2.5, 1.5, 0.6]  # unwind limit per message (50 Hz)

  LATERAL_FREQUENCY = 50

  FLAGS = BYD_FLAG_ATTO3_GENERAL

  def setUp(self):
    # common.SafetyTestBase.setUp re-applies the hooks from these; set them to
    # match what this Base configures so the super() call is a no-op repeat.
    self.SAFETY_MODEL = CarParams.SafetyModel.byd
    self.SAFETY_PARAM = self.FLAGS
    self.packer = CANPackerSafety("byd_general")
    self.safety = libsafety_py.libsafety
    self.safety.set_safety_hooks(CarParams.SafetyModel.byd, self.FLAGS)
    self.safety.init_tests()
    super().setUp()

  def _angle_cmd_msg(self, angle: float, enabled: bool, increment_timer: bool = True):
    values = {"STEER_ANGLE": angle, "STEER_REQ": 1 if enabled else 0}
    return self.packer.make_can_msg_safety("STEERING_MODULE_ADAS", BYD_CANBUS_ESC, values)

  def _angle_meas_msg(self, angle: float):
    values = {"STEER_ANGLE_2": angle}
    return self.packer.make_can_msg_safety("STEER_MODULE_2", BYD_CANBUS_ESC, values)

  def _speed_msg(self, speed):
    values = {"WHEELSPEED_%s" % s: float(speed * 3.6 * 10) for s in ["FL", "FR", "BL", "BR"]}
    return self.packer.make_can_msg_safety("WHEEL_SPEED", BYD_CANBUS_ESC, values)

  def _speed_msg_2(self, speed: float):
    return None

  def _user_brake_msg(self, brake):
    values = {"BRAKE_PEDAL": int(brake)}
    return self.packer.make_can_msg_safety("PEDAL", BYD_CANBUS_ESC, values)

  def _user_gas_msg(self, gas):
    values = {"GAS_PEDAL": int(gas)}
    return self.packer.make_can_msg_safety("PEDAL", BYD_CANBUS_ESC, values)

  def _pcm_status_msg(self, enable):
    values = {"ACC_ON_1": int(enable), "ACC_ON_2": int(enable), "CMD_REQ_ACTIVE_LOW": int(not enable)}
    return self.packer.make_can_msg_safety("ACC_CMD", BYD_CANBUS_MPC, values)

  # MADS button / ACC main are not wired up for BYD; leave abstract to skip those tests
  def _lkas_button_msg(self, enabled):
    raise NotImplementedError

  def _acc_state_msg(self, enabled):
    values = {"ACC_ON1": int(enabled), "ACC_ON2": int(enabled)}
    return self.packer.make_can_msg_safety("ACC_HUD_ADAS", BYD_CANBUS_MPC, values)


class TestBydAtto3GeneralSafety(BydAtto3GeneralSafetyBase):
  pass


class TestBydAngleGenericSafety(common.CarSafetyTest, common.AngleSteeringSafetyTest):
  """Safety coverage for generic DBC angle platforms (SEAL/TENGSHI/QIN_L)."""
  TX_MSGS = BYD_ANGLE_GENERIC_TX_MSGS
  RELAY_MALFUNCTION_ADDRS = BYD_ANGLE_GENERIC_RELAY_MALFUNCTION_ADDRS
  FWD_BLACKLISTED_ADDRS = BYD_ANGLE_GENERIC_FWD_BLACKLISTED_ADDRS
  FWD_BUS_LOOKUP = BYD_ANGLE_GENERIC_FWD_BUS_LOOKUP
  STEER_ANGLE_MAX = 64
  DEG_TO_CAN = 10
  ANGLE_RATE_BP = [0., 30., 60.]
  ANGLE_RATE_UP = [5., 1.5, 0.5]
  ANGLE_RATE_DOWN = [5., 1.5, 0.5]
  LATERAL_FREQUENCY = 50
  FLAGS = BYD_FLAG_ANGLE_MODE

  def setUp(self):
    # common.SafetyTestBase.setUp re-applies the hooks from these; set them to
    # match what this class configures so the super() call is a no-op repeat.
    self.SAFETY_MODEL = CarParams.SafetyModel.byd
    self.SAFETY_PARAM = self.FLAGS
    self.packer = CANPackerSafety("byd_generic_pt")
    self.safety = libsafety_py.libsafety
    self.safety.set_safety_hooks(CarParams.SafetyModel.byd, self.FLAGS)
    self.safety.init_tests()
    super().setUp()

  def _angle_cmd_msg(self, angle: float, enabled: bool, increment_timer: bool = True):
    values = {"sig_kqgoqc": angle, "sig_ausukb": int(enabled)}
    return self.packer.make_can_msg_safety("CID_TCDUBH", BYD_CANBUS_ESC, values)

  def _angle_meas_msg(self, angle: float):
    return self.packer.make_can_msg_safety("CID_VSUYVS", BYD_CANBUS_ESC, {"sig_uefwof": angle})

  def _speed_msg(self, speed):
    return self.packer.make_can_msg_safety("CID_QXPDTS", BYD_CANBUS_ESC, {"sig_mniqdb": speed})

  def _speed_msg_2(self, speed: float):
    return None

  def _user_brake_msg(self, brake):
    return self.packer.make_can_msg_safety("CID_GDWRBP", BYD_CANBUS_ESC, {"sig_wrfhru": int(brake)})

  def _user_gas_msg(self, gas):
    return self.packer.make_can_msg_safety("CID_GDWRBP", BYD_CANBUS_ESC, {"sig_oefitp": int(gas)})

  def _pcm_status_msg(self, enable):
    return self.packer.make_can_msg_safety("CID_XQYNBW", BYD_CANBUS_MPC, {"sig_hprcqm": 3 if enable else 0})

  def _lkas_button_msg(self, enabled):
    raise NotImplementedError

  def _acc_state_msg(self, enabled):
    return self.packer.make_can_msg_safety("CID_XQYNBW", BYD_CANBUS_MPC, {"sig_hprcqm": 2 if enabled else 0})


class TestBydYuanPlusAtto3Safety(BydAtto3GeneralSafetyBase):
  FLAGS = BYD_FLAG_YUAN_PLUS_DMI_ATTO3


if __name__ == "__main__":
  unittest.main()
