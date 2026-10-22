"""
Gated per-vehicle lateral tune dispatch (StarPilot latcontrol_vehicle_tunes port).

Maps a CarParams fingerprint onto a VehicleTuneSpec whose callables all share
the standard signature (setpoint, measurement, jerk, v_ego). The controller
only applies a spec when the VehicleTunesEnabled param is set; an unmatched
platform resolves to None so stock behavior is untouched.
"""
from dataclasses import dataclass

from opendbc.car.honda.values import CAR as HONDA_CAR

from openpilot.selfdrive.controls.lib import latcontrol_vehicle_tunes as tunes


@dataclass(frozen=True)
class VehicleTuneSpec:
  ff_scale: object = None          # (setpoint, measurement, jerk, v_ego) -> float
  friction_threshold: object = None
  friction_scale: object = None
  output_scale: object = None      # applied to the signed output torque magnitude


def _accord_ff(setpoint, measurement, jerk, v_ego):
  return tunes.get_honda_accord_ff_scale(setpoint)


def _gv70_ff(setpoint, measurement, jerk, v_ego):
  return tunes.get_genesis_gv70_unwind_ff_scale(setpoint, measurement, jerk, v_ego)


def _civic_bosch_ff(setpoint, measurement, jerk, v_ego):
  return tunes.get_civic_bosch_modified_b_ff_scale(setpoint, jerk, v_ego)


def _civic_bosch_friction_threshold(setpoint, measurement, jerk, v_ego):
  return tunes.CIVIC_BOSCH_MODIFIED_B_FIXED_FRICTION_THRESHOLD


def _civic_bosch_friction_scale(setpoint, measurement, jerk, v_ego):
  return tunes.get_civic_bosch_modified_b_friction_scale(v_ego, setpoint, jerk)


def _bolt_2017_output(setpoint, measurement, jerk, v_ego):
  return tunes.get_bolt_2017_torque_scale(setpoint, jerk, v_ego)


def _bolt_2018_2021_output(setpoint, measurement, jerk, v_ego):
  return tunes.get_bolt_2018_2021_dynamic_torque_scale(setpoint, jerk, v_ego)


def _genesis_g70_output(setpoint, measurement, jerk, v_ego):
  # StarPilot reuses the Bolt 2017 torque map for the G70 output taper.
  return tunes.get_bolt_2017_torque_scale(setpoint, jerk, v_ego)


_REGISTRY: dict = {}
for _fp in tunes.BOLT_2017_CARS:
  _REGISTRY[_fp] = VehicleTuneSpec(output_scale=_bolt_2017_output)
for _fp in tunes.BOLT_2018_2021_CARS:
  _REGISTRY[_fp] = VehicleTuneSpec(output_scale=_bolt_2018_2021_output)
_REGISTRY[HONDA_CAR.HONDA_ACCORD] = VehicleTuneSpec(ff_scale=_accord_ff)
for _fp in tunes.GENESIS_GV70_CARS:
  _REGISTRY[_fp] = VehicleTuneSpec(ff_scale=_gv70_ff)
for _fp in tunes.GENESIS_G70_CARS:
  _REGISTRY.setdefault(_fp, VehicleTuneSpec(output_scale=_genesis_g70_output))


def resolve_vehicle_tune(CP) -> VehicleTuneSpec | None:
  # Note: StarPilot's Civic Bosch EPS-modified tune is not wired here — this
  # fork's opendbc has no EPS_MODIFIED flag. Add it if the variant is ported.
  return _REGISTRY.get(CP.carFingerprint)
