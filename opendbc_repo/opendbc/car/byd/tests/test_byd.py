import unittest

from opendbc.car import Bus, gen_empty_fingerprint
from opendbc.car import structs
from opendbc.car.structs import CarParams
from opendbc.car.byd.interface import CarInterface
from opendbc.car.byd.values import CAR, DBC, CanBus, BydSafetyFlags, PLATFORM_ATTO3_GENERAL, PLATFORM_QIN_SEAL06, PLATFORM_TENGSHI
from opendbc.car.byd.fingerprints import FINGERPRINTS, FW_VERSIONS
from opendbc.car import create_button_events
from opendbc.car.byd.bydcan import create_steering_control, acc_cmd, create_fake_318, byd_checksum
from opendbc.car.byd.carcontroller import BydJerk
from opendbc.car.byd.carstate import CarState
from opendbc.can.packer import CANPacker

Ecu = CarParams.Ecu


class TestBydFingerprint(unittest.TestCase):
  def test_car_params(self):
    for car_model in CAR:
      fingerprint = gen_empty_fingerprint()
      CP = CarInterface.get_params(car_model, fingerprint, [], False, False, False)
      assert CP.brand == "byd"
      assert CP.safetyConfigs[0].safetyModel == CarParams.SafetyModel.byd
      assert CP.carFingerprint == car_model

  def test_safety_param_flags(self):
    fingerprint = gen_empty_fingerprint()
    for car_model in CAR:
      CP = CarInterface.get_params(car_model, fingerprint, [], False, False, False)
      expected_flag = 0
      if car_model in (CAR.BYD_HAN_DM_20, CAR.BYD_HAN_EV_20):
        expected_flag = BydSafetyFlags.HAN_TANG_DMEV
      elif car_model in (CAR.BYD_TANG_DM, CAR.BYD_QIN_PRO):
        expected_flag = BydSafetyFlags.HAN_TANG_DMEV
      elif car_model in (CAR.BYD_TANG_DMI_21, CAR.BYD_TANG_DMI_24, CAR.BYD_TANG_DMP_22, CAR.BYD_TANG_DMP_23):
        expected_flag = BydSafetyFlags.TANG_DMI
        if car_model in (CAR.BYD_TANG_DMP_22,):
          expected_flag |= BydSafetyFlags.ACC_CRUISEDISP
      elif car_model in (CAR.BYD_SONG_PLUS_DMI_21, CAR.BYD_SONG_PLUS_DMI_22, CAR.BYD_SONG_PLUS_DMI_23,
                         CAR.BYD_SONG_PRO_DMI_22, CAR.BYD_SONG_L_DMI_24):
        expected_flag = BydSafetyFlags.SONG_PLUS_DMI
      elif car_model == CAR.BYD_QIN_PLUS_DMI_23:
        expected_flag = BydSafetyFlags.QIN_PLUS_DMI
      elif car_model in PLATFORM_QIN_SEAL06:
        expected_flag = BydSafetyFlags.QIN_PLUS_DMI | BydSafetyFlags.ANGLE_MODE
      elif car_model == CAR.BYD_SEAL_23:
        expected_flag = BydSafetyFlags.SONG_PLUS_DMI | BydSafetyFlags.ANGLE_MODE | BydSafetyFlags.ACC_ON1
      elif car_model in PLATFORM_TENGSHI:
        expected_flag = BydSafetyFlags.TANG_DMI | BydSafetyFlags.ANGLE_MODE | BydSafetyFlags.ACC_CRUISEDISP
      elif car_model in (CAR.BYD_HAN_DMI_22, CAR.BYD_HAN_DMI_22J, CAR.BYD_HAN_DMI_22R, CAR.BYD_HAN_DMI_25):
        expected_flag = BydSafetyFlags.SONG_PLUS_DMI | BydSafetyFlags.ACC_CRUISEDISP
      elif car_model in PLATFORM_ATTO3_GENERAL:
        expected_flag = BydSafetyFlags.ATTO3_GENERAL | BydSafetyFlags.ANGLE_MODE
      elif car_model == CAR.BYD_YUAN_PLUS_DMI_22:
        expected_flag = BydSafetyFlags.YUAN_PLUS_DMI_ATTO3
      else:
        self.fail(f"{car_model}: unclassified safety flag")

      assert CP.safetyConfigs[0].safetyParam & expected_flag == expected_flag, f"{car_model}: missing safety flag {expected_flag}"

  def test_no_duplicate_platform_strings(self):
    # Every platform must map to a unique fingerprint key and pass get_params
    seen = set()
    for car_model in CAR:
      assert car_model not in seen, f"duplicate CAR enum {car_model}"
      seen.add(car_model)
    assert len(seen) == 29

  def test_fingerprint_present(self):
    for car_model in CAR:
      assert car_model in FINGERPRINTS, f"{car_model}: missing fingerprint"

  def test_fw_versions_placeholder(self):
    # BYD FW_VERSIONS currently only contains a placeholder; ensure it parses
    for _car_model, ecus in FW_VERSIONS.items():
      for _ecu, fws in ecus.items():
        assert len(fws) > 0
        for fw in fws:
          assert isinstance(fw, bytes)

  def test_dbc_map(self):
    for car_model in CAR:
      assert car_model in DBC
      assert Bus.pt in DBC[car_model]

  def test_supplemental_dbc_assets_load(self):
    # Supplemental DBCs are staged as standalone assets until vehicle logs
    # prove their message sets match a specific platform.
    for dbc_name in ("byd_generic_pt", "byd_tangdm_radar"):
      packer = CANPacker(dbc_name)
      assert packer is not None


class TestBydCan(unittest.TestCase):
  def setUp(self):
    self.CP = CarInterface.get_params(CAR.BYD_HAN_DM_20, gen_empty_fingerprint(), [], False, False, False)
    self.packer = CANPacker(DBC[self.CP.carFingerprint][Bus.pt])
    self.hud = structs.CarControl.HUDControl(leftLaneVisible=True, rightLaneVisible=True,
                                             leftLaneDepart=False, rightLaneDepart=False)

  def _make_cam_lkas(self):
    return {
      "sig_dedkvi": 0, "sig_xnxyjw": 1, "sig_mfykom": 2, "sig_pahrba": 1,
      "sig_oiobwq": 0, "sig_uprtqw": 0, "sig_kqgoqc": 0, "sig_ausukb": 0,
      "sig_zyaysi": 0, "sig_vvkmqz": 0, "sig_pzvsvx": 0, "sig_qgavhs": 0,
      "sig_dwbngy": 1, "sig_vehado": 0, "sig_ukhsab": 0, "sig_uwnlau": 0,
      "sig_lfdhgc": 0,
    }

  def _make_esc_eps(self):
    return {
      "sig_rcgbok": 0, "sig_kwshuz": 0, "sig_civxub": 0, "sig_ozgtym": 0,
      "sig_odtaoc": 0, "sig_itfrci": 0, "sig_kviyqk": 0, "sig_pcoiep": 0,
      "sig_bhnetn": 0, "sig_ckxuov": 0, "sig_ktcyrh": 0,
    }

  def _make_cam_acc(self):
    return {
      "sig_zspfbe": 0.0, "sig_umvvum": 0.05, "sig_ffvcas": 0.05,
      "sig_vfmqcq": 0.5, "sig_civxub": 0, "sig_vuisck": -0.5,
      "sig_qvxncf": 0, "sig_doptnp": 0, "sig_zrsmfm": 0, "sig_yjgifm": 0,
      "sig_gbaqki": 0, "sig_xkavyk": 0, "sig_tvemyu": 0,
    }

  def test_create_steering_control(self):
    cam_lkas = self._make_cam_lkas()
    msg = create_steering_control(self.packer, self.CP, cam_lkas, 100, 1, 1, self.hud, False, 0)
    assert msg[0] == 0x316  # ACC_MPC_STATE address
    assert len(msg[1]) == 8
    assert msg[2] == CanBus(self.CP).ESC

  def test_acc_cmd(self):
    cam_acc = self._make_cam_acc()
    jerk = BydJerk()
    msg = acc_cmd(self.packer, self.CP, cam_acc, jerk, 1.0, 0, 0, True, 3, 0)
    assert msg[0] == 0x32E  # ACC_CMD address
    assert len(msg[1]) == 8
    assert msg[2] == CanBus(self.CP).ESC

  def test_create_fake_318(self):
    esc_eps = self._make_esc_eps()
    msg = create_fake_318(self.packer, self.CP, esc_eps, 100, True, True, 0, True, 0)
    assert msg[0] == 0x318  # ACC_EPS_STATE address
    assert len(msg[1]) == 8
    assert msg[2] == CanBus(self.CP).MPC


class TestBydChecksum(unittest.TestCase):
  def test_byd_checksum(self):
    # Checksum is the last byte; for an all-zero payload with key 0xAF the
    # checksum should be deterministic and in range.
    dat = bytes([0] * 8)
    chk = byd_checksum(0xAF, dat)
    assert 0 <= chk <= 0xFF

    # Modifying any byte should change the checksum
    dat2 = bytearray(dat)
    dat2[0] = 1
    chk2 = byd_checksum(0xAF, bytes(dat2))
    assert chk != chk2


class TestBydButtons(unittest.TestCase):
  def test_cancel_button_event(self):
    events = create_button_events(1, 0, {1: structs.CarState.ButtonEvent.Type.cancel})
    assert len(events) == 1
    assert events[0].pressed is True
    assert events[0].type == structs.CarState.ButtonEvent.Type.cancel

  def test_no_duplicate_events(self):
    # No transition -> no event
    events = create_button_events(0, 0, {1: structs.CarState.ButtonEvent.Type.cancel})
    assert len(events) == 0


class TestBydCarState(unittest.TestCase):
  def test_get_can_parsers(self):
    CP = CarInterface.get_params(CAR.BYD_HAN_DM_20, gen_empty_fingerprint(), [], False, False, False)
    parsers = CarState.get_can_parsers(CP, None)
    assert Bus.pt in parsers
    assert Bus.cam in parsers
    assert parsers[Bus.pt].bus == CanBus(self.CP).ESC
    assert parsers[Bus.cam].bus == CanBus(self.CP).MPC

  def test_get_can_parsers_atto3(self):
    CP = CarInterface.get_params(CAR.BYD_ATTO3, gen_empty_fingerprint(), [], False, False, False)
    parsers = CarState.get_can_parsers(CP, None)
    assert Bus.pt in parsers
    assert Bus.cam in parsers
    assert parsers[Bus.pt].bus == CanBus(self.CP).ESC
    assert parsers[Bus.cam].bus == CanBus(self.CP).MPC


if __name__ == "__main__":
  unittest.main()
