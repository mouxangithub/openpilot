"""Lateral geometry (CG ratio) tests for sunnypilot's PerMass vehicle model.

Run directly: python opendbc/car/tests/test_lateral_geometry.py

The opendbc.car package __init__ loads capnp schemas, and this machine's
pycapnp build aborts on capnp.load, so the modules under test are loaded
from their real source files with a minimal opendbc.car stub instead of a
package import. lateral_geometry.py and vehicle_model.py only depend on
math/numpy plus structs.CarParams for typing.
"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

CAR_DIR = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
  spec = importlib.util.spec_from_file_location(name, path)
  mod = importlib.util.module_from_spec(spec)
  sys.modules[name] = mod
  spec.loader.exec_module(mod)
  return mod


def _install_stub():
  if 'opendbc.car' in sys.modules:
    return
  stub_car = types.ModuleType('opendbc.car')
  stub_car.__path__ = []
  stub_car.ACCELERATION_DUE_TO_GRAVITY = 9.81
  stub_structs = types.ModuleType('opendbc.car.structs')
  stub_structs.CarParams = object
  stub_car.structs = stub_structs
  sys.modules['opendbc.car'] = stub_car
  sys.modules['opendbc.car.structs'] = stub_structs


_install_stub()
lateral_geometry = _load('opendbc.car.lateral_geometry', CAR_DIR / 'lateral_geometry.py')
vehicle_model = _load('opendbc.car.vehicle_model', CAR_DIR / 'vehicle_model.py')
LateralGeometry = lateral_geometry.LateralGeometry
requested_center_to_front_ratio = lateral_geometry.requested_center_to_front_ratio
VehicleModel = vehicle_model.VehicleModel


def make_mock_cp(wheelbase=2.895, ratio=0.4, front=0.001, rear=0.0012):
  """CP stand-in with sunnypilot's mass-normalized (PerMass) stiffness fields."""
  return SimpleNamespace(
    wheelbase=wheelbase,
    centerToFront=wheelbase * ratio,
    tireStiffnessFrontPerMass=front,
    tireStiffnessRearPerMass=rear,
    rotationalInertiaPerMass=2500.0 / 1462.0,
    steerRatio=13.27,
  )


class TestRequestedRatio(unittest.TestCase):
  def setUp(self):
    self.cp = make_mock_cp()

  def test_valid_percent_range(self):
    for percent in (31, 40, 50, 60, 69):
      params = SimpleNamespace(get_int=lambda key, p=percent: p)
      self.assertAlmostEqual(requested_center_to_front_ratio(params, self.cp), percent * 0.01)

  def test_invalid_or_absent_falls_back_to_default(self):
    for stored in (0, -1, 30, 70, 100):
      params = SimpleNamespace(get_int=lambda key, s=stored: s)
      self.assertAlmostEqual(requested_center_to_front_ratio(params, self.cp), self.cp.centerToFront / self.cp.wheelbase)

    def raising_get_int(key):
      raise ValueError('bad param')

    self.assertAlmostEqual(requested_center_to_front_ratio(SimpleNamespace(get_int=raising_get_int), self.cp),
                           self.cp.centerToFront / self.cp.wheelbase)


class TestLateralGeometry(unittest.TestCase):
  def setUp(self):
    self.cp = make_mock_cp()

  def test_default_geometry_matches_cp(self):
    geometry = LateralGeometry(self.cp)
    self.assertAlmostEqual(geometry.ratio, 0.4)
    self.assertAlmostEqual(geometry.center_to_front, self.cp.centerToFront)
    self.assertAlmostEqual(geometry.stiffness_front, self.cp.tireStiffnessFrontPerMass)
    self.assertAlmostEqual(geometry.stiffness_rear, self.cp.tireStiffnessRearPerMass)

  def test_update_scales_per_mass_stiffness_by_ratio(self):
    geometry = LateralGeometry(self.cp)
    self.assertTrue(geometry.update(0.6))
    self.assertAlmostEqual(geometry.center_to_front, self.cp.wheelbase * 0.6)
    self.assertAlmostEqual(geometry.stiffness_front, self.cp.tireStiffnessFrontPerMass * 0.4 / 0.6)
    self.assertAlmostEqual(geometry.stiffness_rear, self.cp.tireStiffnessRearPerMass * 0.6 / 0.4)

  def test_update_back_to_default_restores_baseline(self):
    geometry = LateralGeometry(self.cp)
    geometry.update(0.6)
    self.assertTrue(geometry.update(0.4))
    self.assertAlmostEqual(geometry.center_to_front, self.cp.centerToFront)
    self.assertAlmostEqual(geometry.stiffness_front, self.cp.tireStiffnessFrontPerMass)
    self.assertAlmostEqual(geometry.stiffness_rear, self.cp.tireStiffnessRearPerMass)

  def test_invalid_and_legacy_values_are_rejected(self):
    geometry = LateralGeometry(self.cp)
    geometry.update(0.6)
    for invalid in (0.0, -1.0, 0.1, 0.9, float('nan'), float('inf')):
      self.assertFalse(geometry.update(invalid))
      self.assertAlmostEqual(geometry.ratio, 0.6)

  def test_step_is_rate_limited(self):
    geometry = LateralGeometry(self.cp)
    # 0.1 ratio/s: after one 0.01 s step the ratio may move at most 0.001
    self.assertTrue(geometry.step(0.6, 0.01))
    self.assertAlmostEqual(geometry.ratio, 0.401)
    # exactly reaching the target takes several steps
    for _ in range(199):
      geometry.step(0.6, 0.01)
    self.assertAlmostEqual(geometry.ratio, 0.6)

  def test_step_rejects_invalid_input(self):
    geometry = LateralGeometry(self.cp)
    self.assertFalse(geometry.step(0.6, 0.0))
    self.assertFalse(geometry.step(0.6, -0.01))
    self.assertFalse(geometry.step(float('nan'), 0.01))
    self.assertFalse(geometry.step(0.9, 0.01))
    self.assertAlmostEqual(geometry.ratio, 0.4)


class TestVehicleModelGeometry(unittest.TestCase):
  def setUp(self):
    self.cp = make_mock_cp()

  def test_default_ratio_is_noop_for_model_values(self):
    before = VehicleModel(self.cp)
    after = VehicleModel(self.cp)
    before.update_params(0.8, 17.0)
    after.update_params(0.8, 17.0)
    after.update_geometry(self.cp.centerToFront / self.cp.wheelbase)
    self.assertAlmostEqual(after.aF, before.aF)
    self.assertAlmostEqual(after.cF, before.cF)
    self.assertAlmostEqual(after.cR, before.cR)
    self.assertEqual(after.sR, 17.0)

  def test_update_geometry_moves_cg_and_keeps_stiffness_factor(self):
    before = VehicleModel(self.cp)
    after = VehicleModel(self.cp)
    before.update_params(0.8, 17.0)
    after.update_params(0.8, 17.0)
    after.update_geometry(0.6)
    self.assertAlmostEqual(after.aF, self.cp.wheelbase * 0.6)
    self.assertAlmostEqual(after.aR, self.cp.wheelbase * 0.4)
    self.assertAlmostEqual(after.cF, after.cF_orig * 0.8)
    self.assertAlmostEqual(after.cF_orig, self.cp.tireStiffnessFrontPerMass * 0.4 / 0.6)
    self.assertEqual(after.sR, 17.0)

  def test_steer_from_curvature_round_trip_survives_geometry_change(self):
    before = VehicleModel(self.cp)
    after = VehicleModel(self.cp)
    before.update_params(0.8, 17.0)
    after.update_params(0.8, 17.0)
    after.update_geometry(0.6)
    for u in (3., 10., 20., 30.):
      self.assertAlmostEqual(after.get_steer_from_curvature(0.002, u, 0.02),
                             before.get_steer_from_curvature(0.002, u, 0.02), places=5)

  def test_invalid_messages_hold_last_geometry(self):
    vm = VehicleModel(self.cp)
    vm.update_geometry(0.6)
    for invalid in (0.0, 0.1, 0.9, float('nan'), float('inf')):
      vm.update_geometry(invalid)
      self.assertAlmostEqual(vm.geometry.ratio, 0.6)

  def test_zero_ratio_never_reaches_default_state(self):
    # Hard requirement: an absent/legacy 0 ratio must be a complete no-op.
    vm = VehicleModel(self.cp)
    before = (vm.aF, vm.aR, vm.cF_orig, vm.cR_orig)
    vm.update_geometry(0.0)
    self.assertEqual((vm.aF, vm.aR, vm.cF_orig, vm.cR_orig), before)


if __name__ == '__main__':
  unittest.main()
