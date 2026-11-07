#!/usr/bin/env python3
"""BYD vehicle platform definitions.

Merged implementation:
  - Base: the 28-platform port from 高阶Python源码_v2 (byd_generic_pt.dbc,
    BydFlags per-model config, CID_* obfuscated signal names).
  - Kept from the previous local port: BYD_ATTO3 (byd_general.dbc angle control,
    validated on real vehicles) and BYD_SONG_PLUS_DMI_23.
"""
from dataclasses import dataclass, field
from enum import IntFlag

from opendbc.car import Bus, CanBusBase, CarSpecs, DbcDict, PlatformConfig, Platforms
from opendbc.car.docs_definitions import CarDocs, CarHarness, CarParts
from opendbc.car.fw_query_definitions import FwQueryConfig, Request
from opendbc.car.lateral import AngleSteeringLimits
from opendbc.car.structs import CarParams

Ecu = CarParams.Ecu


@dataclass
class BydCarDocs(CarDocs):
  package: str = "All"
  car_parts: CarParts = field(default_factory=CarParts.common([CarHarness.custom]))


@dataclass
class BydPlatformConfig(PlatformConfig):
  dbc_dict: DbcDict = field(default_factory=lambda: {Bus.pt: "byd_generic_pt"})


class BydFlags(IntFlag):
  """Per-model config flags (from 高阶源码 v2)."""
  CANFD = 1
  ANGLE_CONTROL = 2
  ALT_INDICATOR = 4
  SETSPEED_X10 = 8
  BCM_SEAL = 16
  ALT_ACC_EPS = 32
  ALT_ACC_EPS_SEAL = 64
  ALT_ACC_CURISE_MODE = 128
  ALT_ACC_ACCON1 = 256
  ALT_PCM_BTN = 512
  ACC_STOP_FIX = 1024
  ANGLE_DRIVER_OVERRIDE_RELEASE = 2048


class BydSafetyFlags(IntFlag):
  """Safety mode flags for safety/modes/byd.h.

  Low 6 bits keep the platform flags already validated in the local panda
  port (HAN_TANG_DMEV .. ATTO3_GENERAL). Upper bits are the control-mode /
  ACC-behaviour flags required by the 28-platform port.
  """
  # platform flags (low byte) — must match safety/modes/byd.h
  HAN_TANG_DMEV = 0x1
  TANG_DMI = 0x2
  SONG_PLUS_DMI = 0x4
  QIN_PLUS_DMI = 0x8
  YUAN_PLUS_DMI_ATTO3 = 0x10
  ATTO3_GENERAL = 0x20
  # control-mode flags (upper bits)
  ANGLE_MODE = 0x100
  ACC_ON1 = 0x200
  ACC_CRUISEDISP = 0x400
  N3 = 0x800


class CarControllerParams:
  STEER_MAX = 300
  STEER_DELTA_UP = 17
  STEER_DELTA_DOWN = 17
  STEER_DRIVER_ALLOWANCE = 68
  STEER_DRIVER_MULTIPLIER = 3
  STEER_DRIVER_FACTOR = 1
  STEER_ERROR_MAX = 80
  MAX_STEER_ANGLE = 640
  ACCEL_MAX = 3.0
  ACCEL_MIN = -4.5
  K_DASHSPEED = 0.0719088
  K_accel_jerk_upper = 0.1
  K_accel_jerk_lower = 0.5
  K_jerk_xp = [4, 10, 20, 40, 80]
  K_jerk_base_lower_fp = [-2.0, -1.8, -1.4, -1.0, -0.4]
  K_jerk_base_upper_fp = [0.8, 0.7, 0.6, 0.3, 0.2]

  # ATTO3 (byd_general.dbc) angle-control limits — kept from the validated local port
  ANGLE_LIMITS: AngleSteeringLimits = AngleSteeringLimits(
    90.,  # deg
    ([0., 5., 25.], [2.5, 1.5, 0.4]),
    ([0., 5., 25.], [2.5, 1.5, 0.6]),
  )
  MAX_ANGLE_ERROR = 12.0  # deg
  STEER_DRIVER_ALLOWANCE_ANGLE = 80

  def __init__(self, CP):
    pass


class LKASConfig:
  DISABLE = 0
  ALARM = 1
  LKA = 2
  ALARM_AND_LKA = 3


class CanBus(CanBusBase):
  """Bus addressing for BYD.

  Dual-panda CAN mode convention (safetyConfigs carries one entry per panda):
  - primary panda (active, runs safety + control): camera/control segment, buses 0-2
  - secondary panda (aux, e.g. internal dos): OBD/powertrain segment, buses 4-6
    (CanBusBase.offset = 4 per extra panda; equals buses 0-2 with a single panda)
  """

  def __init__(self, CP=None, fingerprint=None) -> None:
    super().__init__(CP, fingerprint)

  # ESC / MRR are on the powertrain side: they move to the secondary panda's
  # bus block in dual-panda mode
  @property
  def ESC(self) -> int:
    return self.offset

  @property
  def MRR(self) -> int:
    return self.offset + 1

  # the ADAS camera is only reachable through the primary (active) panda,
  # so this bus never shifts
  @property
  def MPC(self) -> int:
    return 2

  # src markers, not real buses
  LOOPBACK = 128
  DROPPED = 192


class CAR(Platforms):
  BYD_HAN_DM_20 = BydPlatformConfig(
    [BydCarDocs("BYD HAN DM 2020")],
    CarSpecs(wheelbase=2.920, steerRatio=15.0, centerToFrontRatio=0.44, tireStiffnessFactor=1.0),
  )
  BYD_HAN_EV_20 = BydPlatformConfig(
    [BydCarDocs("BYD HAN EV 2020")],
    CarSpecs(wheelbase=2.959, steerRatio=15.0, centerToFrontRatio=0.44, tireStiffnessFactor=1.0),
  )
  BYD_HAN_DMI_22 = BydPlatformConfig(
    [BydCarDocs("BYD HAN DMI 2022")],
    CarSpecs(wheelbase=2.920, steerRatio=15.0, centerToFrontRatio=0.44, tireStiffnessFactor=1.0),
  )
  BYD_HAN_DMI_22J = BydPlatformConfig(
    [BydCarDocs("BYD Han DMI 22J 2022")],
    CarSpecs(wheelbase=2.920, steerRatio=15.0, centerToFrontRatio=0.44, tireStiffnessFactor=1.0),
  )
  BYD_HAN_DMI_22R = BydPlatformConfig(
    [BydCarDocs("BYD Han DMI 22R 2022")],
    CarSpecs(wheelbase=2.920, steerRatio=15.0, centerToFrontRatio=0.44, tireStiffnessFactor=1.0),
  )
  BYD_HAN_DMI_25 = BydPlatformConfig(
    [BydCarDocs("BYD HAN DMI 2025")],
    CarSpecs(wheelbase=2.920, steerRatio=15.0, centerToFrontRatio=0.44, tireStiffnessFactor=1.0),
  )
  BYD_TANG_DM = BydPlatformConfig(
    [BydCarDocs("BYD Tang DM 2021")],
    CarSpecs(wheelbase=2.820, steerRatio=15.0, centerToFrontRatio=0.44, tireStiffnessFactor=1.0),
  )
  BYD_TANG_DMI_21 = BydPlatformConfig(
    [BydCarDocs("BYD TANG DMI 2021")],
    CarSpecs(wheelbase=2.820, steerRatio=15.0, centerToFrontRatio=0.44, tireStiffnessFactor=1.0),
  )
  BYD_TANG_DMI_24 = BydPlatformConfig(
    [BydCarDocs("BYD TANG DMI 2024")],
    CarSpecs(wheelbase=2.820, steerRatio=15.0, centerToFrontRatio=0.44, tireStiffnessFactor=1.0),
  )
  BYD_TANG_DMP_22 = BydPlatformConfig(
    [BydCarDocs("BYD TANG DMP 2022")],
    CarSpecs(wheelbase=2.820, steerRatio=15.0, centerToFrontRatio=0.60, tireStiffnessFactor=1.0),
  )
  BYD_TANG_DMP_23 = BydPlatformConfig(
    [BydCarDocs("BYD TANG DMP 2023")],
    CarSpecs(wheelbase=2.820, steerRatio=15.0, centerToFrontRatio=0.60, tireStiffnessFactor=1.0),
  )
  BYD_SONG_PLUS_DMI_21 = BydPlatformConfig(
    [BydCarDocs("BYD SONG PLUS DMI 2021")],
    CarSpecs(wheelbase=2.765, steerRatio=15.0, centerToFrontRatio=0.44, tireStiffnessFactor=1.0),
  )
  BYD_SONG_PLUS_DMI_22 = BydPlatformConfig(
    [BydCarDocs("BYD SONG PLUS DMI 2022")],
    CarSpecs(wheelbase=2.765, steerRatio=15.0, centerToFrontRatio=0.44, tireStiffnessFactor=1.0),
  )
  BYD_SONG_PLUS_DMI_23 = BydPlatformConfig(
    [BydCarDocs("BYD SONG PLUS DMI 2023")],
    CarSpecs(wheelbase=2.765, steerRatio=15.0, centerToFrontRatio=0.44, tireStiffnessFactor=1.0),
  )
  BYD_SONG_PRO_DMI_22 = BydPlatformConfig(
    [BydCarDocs("BYD SONG PRO DMI 2022")],
    CarSpecs(wheelbase=2.712, steerRatio=15.0, centerToFrontRatio=0.44, tireStiffnessFactor=1.0),
  )
  BYD_SONG_L_DMI_24 = BydPlatformConfig(
    [BydCarDocs("BYD SONG L DMI 2024")],
    CarSpecs(wheelbase=2.782, steerRatio=15.0, centerToFrontRatio=0.44, tireStiffnessFactor=1.0),
  )
  BYD_QIN_PLUS_DMI_23 = BydPlatformConfig(
    [BydCarDocs("BYD QIN PLUS DMI 2023")],
    CarSpecs(wheelbase=2.718, steerRatio=15.0, centerToFrontRatio=0.44, tireStiffnessFactor=1.0),
  )
  BYD_QIN_L_DMI = BydPlatformConfig(
    [BydCarDocs("BYD Qin L DMI 2024")],
    CarSpecs(wheelbase=2.900, steerRatio=19.0, centerToFrontRatio=0.44, tireStiffnessFactor=1.0),
  )
  BYD_QIN_PRO = BydPlatformConfig(
    [BydCarDocs("BYD Qin Pro 2021")],
    CarSpecs(wheelbase=2.820, steerRatio=15.0, centerToFrontRatio=0.44, tireStiffnessFactor=1.0),
  )
  BYD_SEAL_06_DMI = BydPlatformConfig(
    [BydCarDocs("BYD Seal 06 DMI 2024")],
    CarSpecs(wheelbase=2.782, steerRatio=15.0, centerToFrontRatio=0.44, tireStiffnessFactor=1.0),
  )
  BYD_SEAL_07_DMI = BydPlatformConfig(
    [BydCarDocs("BYD Seal 07 DMI 2025")],
    CarSpecs(wheelbase=3.110, steerRatio=17.0, centerToFrontRatio=0.60, tireStiffnessFactor=1.0),
  )
  BYD_SEAL_23 = BydPlatformConfig(
    [BydCarDocs("BYD SEAL 2023")],
    CarSpecs(wheelbase=2.920, steerRatio=15.0, centerToFrontRatio=0.60, tireStiffnessFactor=1.0),
  )
  BYD_SEAL_EV_22 = BydPlatformConfig(
    [BydCarDocs("BYD SEAL EV 2022")],
    CarSpecs(wheelbase=3.110, steerRatio=17.0, centerToFrontRatio=0.60, tireStiffnessFactor=1.0),
  )
  BYD_FRIGATE_07_DMI = BydPlatformConfig(
    [BydCarDocs("BYD Frigate 07 DMI 2024")],
    CarSpecs(wheelbase=2.820, steerRatio=19.0, centerToFrontRatio=0.44, tireStiffnessFactor=1.0),
  )
  BYD_TENGSHI_D9_22 = BydPlatformConfig(
    [BydCarDocs("BYD TENGSHI D9 2022")],
    CarSpecs(wheelbase=3.110, steerRatio=17.0, centerToFrontRatio=0.60, tireStiffnessFactor=1.0),
  )
  BYD_TENGSHI_D9_22R = BydPlatformConfig(
    [BydCarDocs("BYD Tengshi D9 22R 2022")],
    CarSpecs(wheelbase=3.110, steerRatio=17.0, centerToFrontRatio=0.60, tireStiffnessFactor=1.0),
  )
  BYD_TENGSHI_D9_24 = BydPlatformConfig(
    [BydCarDocs("BYD TENGSHI D9 2024")],
    CarSpecs(wheelbase=3.110, steerRatio=17.0, centerToFrontRatio=0.60, tireStiffnessFactor=1.0),
  )
  BYD_YUAN_PLUS_DMI_22 = BydPlatformConfig(
    [BydCarDocs("BYD Yuan Plus DMI 2022")],
    CarSpecs(wheelbase=2.720, steerRatio=14.8, centerToFrontRatio=0.44, tireStiffnessFactor=0.7983),
  )
  # Local validated angle-control platform on byd_general.dbc (kept from the
  # previous port; shares logic with YUAN_PLUS_DMI_22 but keeps its own string).
  BYD_ATTO3 = BydPlatformConfig(
    [BydCarDocs("BYD ATTO3 2022-24")],
    CarSpecs(wheelbase=2.720, steerRatio=14.8, centerToFrontRatio=0.44, tireStiffnessFactor=0.7983),
    dbc_dict={Bus.pt: "byd_general", Bus.cam: "byd_general"},
  )
  # BYD N3 platform (SA6 / N3A1, wangchao). Derived from the ADC V2.8.0
  # 20251225 CAN FD platform matrices; wheelbase/steerRatio are placeholders
  # until confirmed on a real car.
  BYD_SA6_N3 = BydPlatformConfig(
    [BydCarDocs("BYD SA6 (N3) 2025-26")],
    CarSpecs(wheelbase=2.750, steerRatio=15.0, centerToFrontRatio=0.44, tireStiffnessFactor=1.0),
    dbc_dict={Bus.pt: "byd_n3_pt"},
  )


class DBC(dict):
  """DBC map that defaults to byd_generic_pt for every platform."""
  def __missing__(self, key):
    return {Bus.pt: "byd_generic_pt"}


DBC = DBC({car: {Bus.pt: "byd_generic_pt"} for car in CAR})
# ATTO3 keeps its own validated DBC set.
DBC[CAR.BYD_ATTO3] = {Bus.pt: "byd_general", Bus.cam: "byd_general"}
# N3 (SA6) uses the CAN FD platform matrix subset.
DBC[CAR.BYD_SA6_N3] = {Bus.pt: "byd_n3_pt"}

FW_QUERY_CONFIG = FwQueryConfig(
  fw_version_regex=br"[\x00-\xff]+",
  requests=[
    Request([b'>\x00', b'"\xf1\x81'], [b'~\x00', b'b\xf1\x81'], whitelist_ecus=[Ecu.eps], rx_offset=0x8, bus=0),
    Request([b'>\x00', b'"\xf1\x81'], [b'~\x00', b'b\xf1\x81'], whitelist_ecus=[Ecu.adas, Ecu.fwdCamera], rx_offset=0x8, bus=2),
  ],
)

# --- platform groups -------------------------------------------------------
PLATFORM_HAN_DMEV = {CAR.BYD_HAN_DM_20, CAR.BYD_HAN_EV_20}
PLATFORM_HAN_DMI = {CAR.BYD_HAN_DMI_22, CAR.BYD_HAN_DMI_22R, CAR.BYD_HAN_DMI_22J, CAR.BYD_HAN_DMI_25,
                    CAR.BYD_TANG_DMP_22, CAR.BYD_TANG_DMP_23, CAR.BYD_YUAN_PLUS_DMI_22}
PLATFORM_TANG_DM = {CAR.BYD_QIN_PRO, CAR.BYD_TANG_DM}
PLATFORM_TANG_DMI = {CAR.BYD_SONG_PLUS_DMI_22, CAR.BYD_TANG_DMI_21, CAR.BYD_TANG_DMI_24}
PLATFORM_SONG_PRO = {CAR.BYD_SONG_PRO_DMI_22}
PLATFORM_SONG_PLUS_DMI = {CAR.BYD_SONG_PLUS_DMI_21}
PLATFORM_QIN_PLUS_DMI = {CAR.BYD_QIN_PLUS_DMI_23}
PLATFORM_QIN_SEAL06 = {CAR.BYD_QIN_L_DMI}
PLATFORM_YUAN_PLUS_DMI_ATTO3 = set()
PLATFORM_SEAL = {CAR.BYD_SEAL_23}
PLATFORM_TENGSHI = {CAR.BYD_FRIGATE_07_DMI, CAR.BYD_HAN_DMI_22J, CAR.BYD_SEAL_06_DMI, CAR.BYD_SEAL_07_DMI,
                    CAR.BYD_SEAL_EV_22, CAR.BYD_SONG_L_DMI_24, CAR.BYD_TENGSHI_D9_22, CAR.BYD_TENGSHI_D9_22R,
                    CAR.BYD_TENGSHI_D9_24}
PLATFORM_ATTO3_GENERAL = {CAR.BYD_ATTO3}
# BYD N3 CAN FD platform (SA6/N3A1)
PLATFORM_N3 = {CAR.BYD_SA6_N3}
# 通用 DBC（byd_generic_pt.dbc）下的角度控制平台：发送 0x1E2 角度命令，C 层须走角度校验
PLATFORM_ANGLE_GENERIC = (PLATFORM_SEAL | PLATFORM_TENGSHI | PLATFORM_QIN_SEAL06)

# --- radar groups ----------------------------------------------------------
PT_RADAR_100 = {CAR.BYD_HAN_DMI_22, CAR.BYD_HAN_DMI_22R, CAR.BYD_HAN_DMI_25, CAR.BYD_TANG_DMP_22,
                CAR.BYD_TANG_DMP_23, CAR.BYD_TENGSHI_D9_22, CAR.BYD_TENGSHI_D9_22R, CAR.BYD_YUAN_PLUS_DMI_22}
PT_RADAR_80 = {CAR.BYD_SEAL_07_DMI, CAR.BYD_SEAL_EV_22, CAR.BYD_TENGSHI_D9_24}
PT_RADAR_CAR = {CAR.BYD_HAN_DMI_22, CAR.BYD_HAN_DMI_22R, CAR.BYD_HAN_DMI_25, CAR.BYD_HAN_DM_20,
                CAR.BYD_HAN_EV_20, CAR.BYD_TANG_DMP_22, CAR.BYD_TANG_DMP_23, CAR.BYD_TENGSHI_D9_22,
                CAR.BYD_TENGSHI_D9_22R, CAR.BYD_YUAN_PLUS_DMI_22}
RADAR_CAR = {CAR.BYD_QIN_PRO, CAR.BYD_TANG_DM}
TORQUE_LAT_CAR = {CAR.BYD_HAN_DMI_22, CAR.BYD_HAN_DMI_22R, CAR.BYD_HAN_DMI_25, CAR.BYD_HAN_DM_20,
                  CAR.BYD_HAN_EV_20, CAR.BYD_QIN_PRO, CAR.BYD_QIN_PLUS_DMI_23, CAR.BYD_SONG_PLUS_DMI_21,
                  CAR.BYD_SONG_PLUS_DMI_22, CAR.BYD_SONG_PRO_DMI_22, CAR.BYD_TANG_DM, CAR.BYD_TANG_DMI_21,
                  CAR.BYD_TANG_DMI_24, CAR.BYD_TANG_DMP_22, CAR.BYD_TANG_DMP_23, CAR.BYD_YUAN_PLUS_DMI_22}
EXP_LONG_CAR = {CAR.BYD_FRIGATE_07_DMI, CAR.BYD_HAN_DMI_22, CAR.BYD_HAN_DMI_22J, CAR.BYD_HAN_DMI_22R,
                CAR.BYD_HAN_DMI_25, CAR.BYD_HAN_DM_20, CAR.BYD_HAN_EV_20, CAR.BYD_QIN_L_DMI, CAR.BYD_QIN_PRO,
                CAR.BYD_SEAL_06_DMI, CAR.BYD_SEAL_07_DMI, CAR.BYD_SEAL_23, CAR.BYD_SEAL_EV_22,
                CAR.BYD_SONG_L_DMI_24, CAR.BYD_SONG_PLUS_DMI_21, CAR.BYD_SONG_PLUS_DMI_22, CAR.BYD_SONG_PRO_DMI_22,
                CAR.BYD_TANG_DM, CAR.BYD_TANG_DMI_21, CAR.BYD_TANG_DMI_24, CAR.BYD_TANG_DMP_22,
                CAR.BYD_TANG_DMP_23, CAR.BYD_TENGSHI_D9_22, CAR.BYD_TENGSHI_D9_22R, CAR.BYD_TENGSHI_D9_24,
                CAR.BYD_YUAN_PLUS_DMI_22}
# SONG_PLUS_DMI_23 (kept from local port): same family as SONG_PLUS_DMI_21/22
PLATFORM_SONG_PLUS_DMI |= {CAR.BYD_SONG_PLUS_DMI_23}
TORQUE_LAT_CAR |= {CAR.BYD_SONG_PLUS_DMI_23}
EXP_LONG_CAR |= {CAR.BYD_SONG_PLUS_DMI_23}
# N3: angle control (0x1E2) + openpilot longitudinal (0x32E rewrite)
EXP_LONG_CAR |= PLATFORM_N3