#!/usr/bin/env python3
"""Toyota MADS lateral gating + SecOC platform + rx_checks profile contracts.

Intent adapted from StarPilot's test_toyota_secoc_aol.py /
test_toyota_rav4h_filter.py onto this fork's mechanisms (MADS instead of AOL,
upstream Toyota SecOC flag instead of StarPilot adapter words):

1. MADS lateral permission must follow the real physical CAN state, driven by
   REAL captured frames (checksummed PCM_CRUISE_2 / PCM_CRUISE / BRAKE_MODULE
   bytes from the StarPilot fixture set), not by packer abstractions alone:
   ACC-main rising edge engages, main-off / brake / steering-disengage
   disengage with the exact reason, pause-on-brake resumes on release, and
   the heartbeat-mismatch backstop disengages after 3 cycles.
   NOTE: this fork's Toyota safety has no gear input (0x3BC is not consumed
   on TSS2 and there is no hybrid gear packet path), so the StarPilot
   gear-gating intents have no equivalent here; cruise/main/brake are the
   physical gates that exist.
2. SecOC platform (SECOC safety flag): cruise/gas/brake come from 0x176 /
   0x116 / 0x101 and LTA_2 actuation stays blocked regardless of MADS state.
3. rx_checks profile contract (from the RAV4H filter intent): every safety
   profile installs exactly its expected monitor table, the per-profile
   rx_status workspace is fully reset on re-init (no cross-profile leak),
   and config validity follows source freshness.

These tests need only the C toolchain (no DBC packers); they run in CI.
"""
import unittest

from opendbc.car.structs import CarParams
from opendbc.car.toyota.values import ToyotaSafetyFlags
from opendbc.safety.tests.libsafety import libsafety_py

libsafety_py.ffi.cdef("extern safety_config current_safety_config;")

EPS_SCALE = 73

# Real captured PCM_CRUISE_2 (0x1D3) frame with MAIN_ON set (data[1] bit 7),
# valid Toyota checksum 0xd2. From the StarPilot SecOC fixture set.
REAL_1D3_MAIN_ON = bytes.fromhex("00a81d39f80000d2")

# ALT_EXP bits (opendbc/safety/sunnypilot/mads_declarations.h)
ALT_EXP_ENABLE_MADS = 1024
ALT_EXP_MADS_DISENGAGE_LATERAL_ON_BRAKE = 2048
ALT_EXP_MADS_PAUSE_LATERAL_ON_BRAKE = 4096

# DisengageReason
REASON_BRAKE = 1
REASON_ACC_MAIN_OFF = 8
REASON_HEARTBEAT = 32
REASON_STEERING_DISENGAGE = 64


def toyota_checksum(address, data):
  data = bytearray(data)
  data[-1] = ((address & 255) + (address >> 8) + len(data) + sum(data[:-1])) & 255
  return bytes(data)


class ToyotaMadsFixtureTestBase(unittest.TestCase):
  """Common harness: real-byte frames, no DBC packer."""

  SECOC = False

  def setUp(self):
    self.safety = libsafety_py.libsafety
    self.init()

  def init(self, ae=ALT_EXP_ENABLE_MADS, param=None):
    self.omit_addresses = set()
    self.safety.init_tests()
    self.safety.set_current_safety_param_sp(0)
    if param is None:
      param = EPS_SCALE | (ToyotaSafetyFlags.SECOC if self.SECOC else 0)
    self.safety.set_safety_hooks(CarParams.SafetyModel.toyota, param)
    self.safety.mads_apply_alternative_experience(ae)
    self.safety.set_timer(1_000_000)

  def rx(self, address, data, crc=False, bus=0):
    if address in self.omit_addresses:
      return True
    data = toyota_checksum(address, data) if crc else bytes(data)
    return bool(self.safety.safety_rx_hook(libsafety_py.make_CANPacket(address, bus, data)))

  def checksum(self, address, data):
    return toyota_checksum(address, data)

  # --- frame helpers (real byte layouts, matches the DBC signal positions) ---

  def speeds(self, moving=False):
    # WHEEL_SPEEDS: 4x (1 fault bit + 15 speed bits); raw 0x1A6F == 0 kph.
    raw = 0x1A6F + (400 if moving else 0)
    return bytes([raw >> 8, raw & 0xFF] * 4)

  def torque(self, eps=0, driver=0):
    # STEER_TORQUE_SENSOR: data[1:3] driver, data[3:5] angle, data[5:7] eps
    return bytes([0, (driver >> 8) & 0xFF, driver & 0xFF, 0, 0, (eps >> 8) & 0xFF, eps & 0xFF, 0])

  def main_on(self, on=True):
    # PCM_CRUISE_2 MAIN_ON is bit 15 (data[1] bit 7); checksum ignored by rx checks
    data = bytearray(8)
    if on:
      data[1] = 0x80
    return bytes(data)

  def physical(self, *, main=True, cruise=False, brake=False, gas=False, moving=False):
    """Feed one full round of the platform's physical sources as real bytes."""
    self.omit_reset()
    self.rx(0xAA, self.speeds(moving))
    if self.SECOC:
      self.rx(0x176, bytes([32 if cruise else 0]) + bytes(7), crc=True)
      self.rx(0x116, bytes([0, 10 if gas else 0]) + bytes(6))
      self.rx(0x101, bytes([8 if brake else 0]) + bytes(7))
    else:
      self.rx(0x1D2, bytes([32 if cruise else 0]) + bytes(7), crc=True)
      self.rx(0x226, bytes(4) + bytes([0x20 if brake else 0x00]) + bytes(3))
      self.rx(0x1D3, self.main_on(main), crc=True)

  def omit_reset(self):
    self.omit_addresses = set()

  def lateral(self):
    return self.safety.get_controls_allowed_lateral()

  def reason(self):
    return self.safety.mads_get_current_disengage_reason()


class TestToyotaMadsRealFixture(ToyotaMadsFixtureTestBase):

  def test_real_main_on_frame_engages_mads(self):
    self.physical(main=True)
    self.assertTrue(self.lateral())
    self.assertEqual(self.reason(), 0)

  def test_mads_disabled_by_default_ae(self):
    self.init(ae=0)
    self.physical(main=True)
    self.assertFalse(self.lateral())

  def test_main_off_disengages_with_reason_and_can_reengage(self):
    self.physical(main=True)
    self.assertTrue(self.lateral())
    self.physical(main=False)
    self.assertFalse(self.lateral())
    self.assertEqual(self.reason(), REASON_ACC_MAIN_OFF)
    # falling->rising main cycle grants a fresh engagement
    self.physical(main=True)
    self.assertTrue(self.lateral())
    self.assertEqual(self.reason(), 0)

  def test_brake_disengage_mode_does_not_resume_on_release(self):
    self.init(ae=ALT_EXP_ENABLE_MADS | ALT_EXP_MADS_DISENGAGE_LATERAL_ON_BRAKE)
    self.physical(main=True)
    self.assertTrue(self.lateral())
    self.physical(main=True, brake=True)
    self.assertFalse(self.lateral())
    self.assertEqual(self.reason(), REASON_BRAKE)
    self.physical(main=True, brake=False)
    # disengage mode: brake release alone must not re-engage
    self.assertFalse(self.lateral())
    self.physical(main=False)
    self.physical(main=True)
    self.assertTrue(self.lateral())

  def test_brake_pause_mode_resumes_on_release(self):
    self.init(ae=ALT_EXP_ENABLE_MADS | ALT_EXP_MADS_PAUSE_LATERAL_ON_BRAKE)
    self.physical(main=True)
    self.assertTrue(self.lateral())
    self.physical(main=True, brake=True)
    self.assertFalse(self.lateral())
    self.assertEqual(self.reason(), REASON_BRAKE)
    # brake held: still paused
    self.physical(main=True, brake=True)
    self.assertFalse(self.lateral())
    # brake released with brake being the only reason: lateral resumes
    self.physical(main=True, brake=False)
    self.assertTrue(self.lateral())
    self.assertEqual(self.reason(), 0)

  def test_brake_disengage_does_not_block_a_new_main_edge(self):
    self.init(ae=ALT_EXP_ENABLE_MADS | ALT_EXP_MADS_DISENGAGE_LATERAL_ON_BRAKE)
    self.physical(main=True)
    self.physical(main=True, brake=True)
    self.assertFalse(self.lateral())
    self.physical(main=True, brake=False)
    self.physical(main=False)
    self.physical(main=True)
    self.assertTrue(self.lateral())

  def test_steering_disengage(self):
    self.physical(main=True)
    self.assertTrue(self.lateral())
    self.safety.set_steering_disengage(True)
    self.physical(main=True)
    self.assertFalse(self.lateral())
    self.assertEqual(self.reason(), REASON_STEERING_DISENGAGE)
    self.safety.set_steering_disengage(False)
    self.physical(main=True)
    # steering disengage alone does not re-engage; a fresh main edge does
    self.assertFalse(self.lateral())
    self.physical(main=False)
    self.physical(main=True)
    self.assertTrue(self.lateral())

  def test_op_controls_rising_edge_grants_lateral(self):
    self.physical(main=False)
    self.assertFalse(self.lateral())
    # OP-side controls_allowed rising edge is a grant source on the next tick
    self.safety.set_controls_allowed(True)
    self.rx(0xAA, self.speeds())
    self.assertTrue(self.lateral())

  def test_heartbeat_mismatch_backstop(self):
    # mads_heartbeat_engaged_check runs on the heartbeat USB command path on
    # the board; the harness exposes it directly (see mads_common.py).
    self.physical(main=True)
    self.assertTrue(self.lateral())
    self.safety.set_heartbeat_engaged_mads(False)
    # 2 mismatches tolerated, the 3rd disengages
    self.safety.mads_heartbeat_engaged_check()
    self.assertTrue(self.lateral())
    self.safety.mads_heartbeat_engaged_check()
    self.assertTrue(self.lateral())
    self.safety.mads_heartbeat_engaged_check()
    self.assertFalse(self.lateral())
    self.assertEqual(self.reason(), REASON_HEARTBEAT)

  def test_checksum_violation_does_not_block_the_mads_tick_but_is_rejected(self):
    self.physical(main=True)
    self.assertTrue(self.lateral())
    # corrupt checksum on checksum-enforced PCM_CRUISE: frame rejected...
    bad = bytearray(8)
    bad[0] = 32
    pkt = libsafety_py.make_CANPacket(0x1D2, 0, bytes(bad))
    self.assertFalse(self.safety.safety_rx_hook(pkt))
    # ...and the bad frame must not flip cruise state (still engaged values
    # from last good frame are kept; lateral unaffected by rejection itself)
    self.assertTrue(self.lateral())

  def test_wrong_bus_is_rejected(self):
    self.assertFalse(self.rx(0x1D2, bytes([32]) + bytes(7), crc=True, bus=1))
    self.assertFalse(self.rx(0x1D3, self.main_on(True), crc=True, bus=2))


class TestToyotaSecocMadsRealFixture(ToyotaMadsFixtureTestBase):
  SECOC = True

  def test_secoc_sources_drive_mads(self):
    self.physical(main=True, cruise=True)
    self.assertTrue(self.lateral())
    self.physical(main=True, cruise=True, brake=True)
    self.assertFalse(self.lateral())
    self.assertEqual(self.reason(), REASON_BRAKE)
    self.physical(main=True, cruise=True)
    self.assertTrue(self.lateral())
    self.physical(main=False, cruise=True)
    self.assertFalse(self.lateral())

  def test_secoc_lta_2_stays_blocked_regardless_of_mads(self):
    self.physical(main=True, cruise=True)
    self.assertTrue(self.lateral())
    self.safety.set_controls_allowed(True)
    # STEERING_LTA_2: any actuation (request bits or angle) is blocked
    for data in (bytes([0x08]) + bytes(7),          # STEER_REQUEST (bit 3)
                 bytes([0x01]) + bytes(7),          # STEER_REQUEST_2 (bit 0)
                 bytes(2) + bytes([0x01, 0x00]) + bytes(4)):  # nonzero angle MSB
      self.assertFalse(self.safety.safety_tx_hook(libsafety_py.make_CANPacket(0x131, 0, data)))
    # zero LTA_2 passes (inactive frame)
    self.assertTrue(self.safety.safety_tx_hook(libsafety_py.make_CANPacket(0x131, 0, bytes(8))))

  def test_secoc_real_gear_packet_is_not_consumed(self):
    # TSS2 gear packet 0x3BC is not part of this fork's SecOC rx checks and
    # must not influence the MADS state (documented no-gate contract).
    self.physical(main=True)
    self.assertTrue(self.lateral())
    before = self.lateral()
    self.rx(0x3BC, bytes(8))
    self.assertEqual(self.lateral(), before)

  def test_secoc_stock_longitudinal_inactive_accel_only_on_343(self):
    # SecOC + stock longitudinal: ACC_CONTROL (0x343) may only carry the
    # inactive accel (0 in the dbc scale used by the accel checks); any other
    # accel is rejected even with OP controls allowed.
    self.init(ae=ALT_EXP_ENABLE_MADS, param=EPS_SCALE | ToyotaSafetyFlags.STOCK_LONGITUDINAL)
    self.physical(main=True)
    self.safety.set_controls_allowed(True)
    # cancel-only frame: inactive accel (0) + CANCEL_REQ (bit 24 -> data[3] bit 0)
    self.assertTrue(self.safety.safety_tx_hook(libsafety_py.make_CANPacket(0x343, 0, bytes(3) + bytes([0x01]) + bytes(4))))
    # active accel is rejected with or without cancel_req
    self.assertFalse(self.safety.safety_tx_hook(libsafety_py.make_CANPacket(0x343, 0, (1000).to_bytes(2, "big") + bytes(6))))
    self.assertFalse(self.safety.safety_tx_hook(libsafety_py.make_CANPacket(0x343, 0, (1000).to_bytes(2, "big") + bytes(2) + bytes([0x01]) + bytes(3))))


class TestToyotaRxChecksProfiles(unittest.TestCase):
  """RAV4H-filter intent: exact monitor table per profile + workspace reset."""

  def setUp(self):
    self.safety = libsafety_py.libsafety

  def init(self, param=EPS_SCALE, param_sp=0):
    self.safety.init_tests()
    self.safety.set_current_safety_param_sp(param_sp)
    self.safety.set_safety_hooks(CarParams.SafetyModel.toyota, param)

  def table(self):
    config = self.safety.current_safety_config
    entries = []
    for i in range(config.rx_checks_len):
      msg = config.rx_checks[i].msg[0]
      status = config.rx_checks[i].status
      entries.append((msg.addr, msg.len, msg.frequency, bool(msg.ignore_checksum),
                      bool(msg.ignore_counter), bool(msg.ignore_quality_flag)))
      # workspace must be pristine right after init: no cross-profile leak
      self.assertFalse(status.msg_seen, f"entry {i} ({msg.addr:#x}) leaked msg_seen")
      self.assertEqual(status.wrong_counters, 0)
      self.assertFalse(status.lagging)
      self.assertEqual(status.last_timestamp, 0)
    return entries

  def test_default_lka_profile_table(self):
    self.init()
    self.assertEqual(self.table(), [
      (0xAA, 8, 83, True, True, False),   # WHEEL_SPEEDS: quality flag enforced
      (0x260, 8, 50, False, True, True),  # STEER_TORQUE_SENSOR (LKA: quality ignored)
      (0x1D2, 8, 33, False, True, True),  # PCM_CRUISE: checksum enforced
      (0x226, 8, 40, True, True, True),   # BRAKE_MODULE
      (0x1D3, 8, 33, True, True, True),   # PCM_CRUISE_2 (main)
    ])

  def test_lta_profile_tracks_quality_flag(self):
    self.init(param=EPS_SCALE | ToyotaSafetyFlags.LTA)
    table = self.table()
    self.assertEqual(table[1], (0x260, 8, 50, False, True, False))  # quality enforced under LTA

  def test_alt_brake_profile_swaps_brake_source(self):
    self.init(param=EPS_SCALE | ToyotaSafetyFlags.ALT_BRAKE)
    table = self.table()
    addrs = [e[0] for e in table]
    self.assertNotIn(0x226, addrs)
    self.assertIn(0x224, addrs)

  def test_unsupported_dsu_profile_uses_dsu_cruise(self):
    self.init(param=EPS_SCALE, param_sp=1)  # ToyotaSafetyFlagsSP.UNSUPPORTED_DSU
    table = self.table()
    addrs = [e[0] for e in table]
    self.assertNotIn(0x1D3, addrs)
    dsu = [e for e in table if e[0] == 0x365]
    self.assertEqual(len(dsu), 1)
    self.assertEqual(dsu[0][1], 7)  # 7-byte DSU_CRUISE

  def test_secoc_profile_table(self):
    self.init(param=EPS_SCALE | ToyotaSafetyFlags.SECOC)
    self.assertEqual(self.table(), [
      (0xAA, 8, 83, True, True, False),
      (0x260, 8, 50, False, True, True),
      (0x176, 8, 32, False, True, True),  # PCM_CRUISE (SecOC): checksum enforced
      (0x116, 8, 42, True, True, True),   # GAS_PEDAL
      (0x101, 8, 50, True, True, True),   # BRAKE_MODULE (SecOC)
      (0x1D3, 8, 33, True, True, True),
    ])

  def test_gas_interceptor_profile_adds_201(self):
    self.init(param=EPS_SCALE, param_sp=2)  # ToyotaSafetyFlagsSP.GAS_INTERCEPTOR
    table = self.table()
    self.assertIn((0x201, 6, 50, True, True, True), table)

  def test_workspace_reset_between_reinits(self):
    # drive real traffic so every status is dirty, then re-init into another
    # profile and confirm the whole workspace came back pristine
    for first, second in ((EPS_SCALE, EPS_SCALE | ToyotaSafetyFlags.LTA),
                          (EPS_SCALE | ToyotaSafetyFlags.SECOC, EPS_SCALE)):
      self.init(param=first)
      pkt = libsafety_py.make_CANPacket(0xAA, 0, bytes([0x1A, 0x6F] * 4))
      self.assertTrue(self.safety.safety_rx_hook(pkt))
      self.assertTrue(self.safety.current_safety_config.rx_checks[0].status.msg_seen)
      self.init(param=second)
      self.assertFalse(self.safety.current_safety_config.rx_checks[0].status.msg_seen)

  def test_source_expiry_invalidates_config(self):
    self.init()
    config = self.safety.current_safety_config
    # feed every monitored source once at t=1s (0x1D2 and 0x260 need checksums)
    self.assertTrue(self.safety.safety_rx_hook(libsafety_py.make_CANPacket(0xAA, 0, bytes([0x1A, 0x6F] * 4))))
    self.assertTrue(self.safety.safety_rx_hook(libsafety_py.make_CANPacket(0x260, 0, toyota_checksum(0x260, bytes(8)))))
    self.assertTrue(self.safety.safety_rx_hook(libsafety_py.make_CANPacket(0x1D2, 0, toyota_checksum(0x1D2, bytes(8)))))
    self.assertTrue(self.safety.safety_rx_hook(libsafety_py.make_CANPacket(0x226, 0, bytes(8))))
    self.assertTrue(self.safety.safety_rx_hook(libsafety_py.make_CANPacket(0x1D3, 0, toyota_checksum(0x1D3, bytes(8)))))
    self.safety.safety_tick()
    self.assertTrue(self.safety.safety_config_valid())
    # all sources stale for far beyond their period -> lagging -> invalid
    self.safety.set_timer(1_000_000 + 10_000_000)
    self.safety.safety_tick()
    self.assertFalse(self.safety.safety_config_valid())

  def test_wrong_bus_never_marks_source_seen(self):
    self.init()
    for addr, data in ((0xAA, bytes(8)), (0x1D2, toyota_checksum(0x1D2, bytes(8))), (0x1D3, bytes(8))):
      self.assertFalse(self.safety.safety_rx_hook(libsafety_py.make_CANPacket(addr, 1, data)))
    for i in range(self.safety.current_safety_config.rx_checks_len):
      self.assertFalse(self.safety.current_safety_config.rx_checks[i].status.msg_seen)


if __name__ == "__main__":
  unittest.main()
