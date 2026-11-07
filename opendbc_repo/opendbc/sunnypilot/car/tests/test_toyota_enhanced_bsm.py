#!/usr/bin/env python3
# Enhanced BSM on SecOC platforms: the flag gate and the reply decoding.
import types

from opendbc.car import gen_empty_fingerprint, structs
from opendbc.car.toyota.interface import CarInterface
from opendbc.car.toyota.values import CAR, TSS2_CAR
from opendbc.sunnypilot.car.interfaces import _initialize_toyota
from opendbc.sunnypilot.car.toyota.enhanced_bsm import BLINDSPOT_NOISE_FLOOR, EnhancedBsmCarState
from opendbc.sunnypilot.car.toyota.values import ToyotaFlagsSP


def toyota_cp(platform) -> structs.CarParams:
  return CarInterface.get_params(platform, gen_empty_fingerprint(), list(), alpha_long=False, is_release=False, docs=False)


def enabled(cp, cp_sp) -> bool:
  return bool(cp_sp.flags & ToyotaFlagsSP.SP_ENHANCED_BSM)


class TestEnhancedBsmGate:
  def test_secoc_platform_can_enable(self):
    # TOYOTA_WILDLANDER_PHEV is a ToyotaSecOCPlatformConfig platform; the enhanced BSM path used to
    # be hard-excluded for those, which left them without any working blind spot signal.
    cp = toyota_cp(CAR.TOYOTA_WILDLANDER_PHEV)
    assert cp.carFingerprint in TSS2_CAR

    cp_sp = structs.CarParamsSP()
    _initialize_toyota(cp, cp_sp, {"ToyotaEnhancedBsm": "1"})
    assert enabled(cp, cp_sp)

  def test_still_opt_in(self):
    cp = toyota_cp(CAR.TOYOTA_WILDLANDER_PHEV)

    cp_sp = structs.CarParamsSP()
    _initialize_toyota(cp, cp_sp, {"ToyotaEnhancedBsm": "0"})
    assert not enabled(cp, cp_sp)

    cp_sp = structs.CarParamsSP()
    _initialize_toyota(cp, cp_sp, {})
    assert not enabled(cp, cp_sp)

  def test_non_tss2_platform_stays_off(self):
    cp = toyota_cp(CAR.TOYOTA_PRIUS)
    assert cp.carFingerprint not in TSS2_CAR

    cp_sp = structs.CarParamsSP()
    _initialize_toyota(cp, cp_sp, {"ToyotaEnhancedBsm": "1"})
    assert not enabled(cp, cp_sp)


def debug_cp(side: int, d1: int, d2: int) -> types.SimpleNamespace:
  return types.SimpleNamespace(vl={"DEBUG": {"BLINDSPOTSIDE": side, "BLINDSPOTD1": d1, "BLINDSPOTD2": d2}})


def bsm_state() -> EnhancedBsmCarState:
  cp = toyota_cp(CAR.TOYOTA_WILDLANDER_PHEV)
  cp_sp = structs.CarParamsSP()
  cp_sp.flags = ToyotaFlagsSP.SP_ENHANCED_BSM
  return EnhancedBsmCarState(cp, cp_sp)


class TestEnhancedBsmDecoding:
  def test_occupied_zone_sets_the_matching_side(self):
    bsm = bsm_state()
    left, right = bsm.update(debug_cp(0x41, 50, 0), 200)
    assert left and not right

    bsm = bsm_state()
    left, right = bsm.update(debug_cp(0x42, 0, 47), 200)
    assert right and not left

  def test_idle_and_noise_do_not_report(self):
    bsm = bsm_state()
    for d in (0, 1, BLINDSPOT_NOISE_FLOOR):
      left, right = bsm.update(debug_cp(0x41, d, d), 200)
      assert not left and not right

  def test_other_uds_sub_addresses_are_ignored(self):
    # 0x40 with byte 5 == 50 is real traffic on these cars: the ACC/radar tester handshake answers
    # 0x758 with "40 06 50 03 00 32 01 f4", and byte 5 reads like an occupied zone code. Only the
    # 0x41/0x42 sub-addresses are blind spot replies, so this must not report a detection.
    bsm = bsm_state()
    for side in (0x40, 0x00, 0xFF):
      left, right = bsm.update(debug_cp(side, 50, 53), 200)
      assert not left and not right

  def test_silence_clears_the_detection(self):
    bsm = bsm_state()
    left, _ = bsm.update(debug_cp(0x41, 50, 0), 200)
    assert left

    # a side that stops answering entirely clears after the timeout, matching the original behaviour
    for frame in range(300):
      bsm.update(debug_cp(0x40, 0, 0), 201 + frame)
    left, _ = bsm.update(debug_cp(0x40, 0, 0), 600)
    assert not left
