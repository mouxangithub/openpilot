#!/usr/bin/env python3
import unittest
from types import SimpleNamespace

from opendbc.car.honda.values import CAR as HONDA_CAR

from openpilot.sunnypilot.selfdrive.controls.lib.vehicle_tune_dispatch import (
  VehicleTuneSpec,
  resolve_vehicle_tune,
)
from openpilot.selfdrive.controls.lib import latcontrol_vehicle_tunes as tunes


def _cp(fingerprint, brand="honda", flags=0):
  return SimpleNamespace(brand=brand, carFingerprint=fingerprint, flags=flags)


class TestVehicleTuneDispatch(unittest.TestCase):
  def test_unknown_platform_resolves_none(self):
    self.assertIsNone(resolve_vehicle_tune(_cp("TOYOTA_WILANDER_PHEV", brand="toyota")))

  def test_accord_resolves_ff_scale(self):
    spec = resolve_vehicle_tune(_cp(HONDA_CAR.HONDA_ACCORD))
    self.assertIsInstance(spec, VehicleTuneSpec)
    self.assertIsNotNone(spec.ff_scale)
    self.assertIsNone(spec.output_scale)
    # StarPilot bookmark: the Accord FF gain dips slightly below 1.0 mid-speed.
    self.assertAlmostEqual(spec.ff_scale(2.0, 0.0, 0.0, 30.0), tunes.get_honda_accord_ff_scale(2.0))

  def test_bolt_2017_resolves_output_scale(self):
    self.assertGreater(len(tunes.BOLT_2017_CARS), 0)
    spec = resolve_vehicle_tune(_cp(tunes.BOLT_2017_CARS[0], brand="gm"))
    self.assertIsNotNone(spec.output_scale)
    self.assertEqual(spec.output_scale(5.0, 0.0, 1.0, 20.0), tunes.get_bolt_2017_torque_scale(5.0, 1.0, 20.0))

  def test_civic_bosch_modified_not_wired_without_flag(self):
    # StarPilot's EPS-modified Civic tune needs a flag this fork's opendbc
    # lacks; the stock Civic Bosch platform must resolve to nothing.
    self.assertIsNone(resolve_vehicle_tune(_cp(HONDA_CAR.HONDA_CIVIC_BOSCH)))

  def test_platform_aliases_keep_groups_populated(self):
    # Aliased StarPilot platforms must map onto this fork's opendbc enums.
    self.assertEqual(len(tunes.BOLT_2017_CARS), 1)
    self.assertEqual(len(tunes.BOLT_2022_2023_CARS), 3)
    self.assertGreater(len(tunes.GENESIS_GV70_CARS), 0)


if __name__ == "__main__":
  unittest.main()
