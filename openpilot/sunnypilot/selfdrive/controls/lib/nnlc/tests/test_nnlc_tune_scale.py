"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of zoompilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

NNLC's models were trained on upstream's STEER_MAX; on the Mazda EPS envelope's 1200 counts
their torque is scaled by 800/1200 so the same counts reach the wire.
"""
from openpilot.common.test import OpenpilotTestCase
from opendbc.car.car_helpers import interfaces
from opendbc.car.mazda.values import CAR as MAZDA
from opendbc.car.structs import car
from opendbc.car.toyota.values import CAR as TOYOTA
from opendbc.car.vehicle_model import VehicleModel
from openpilot.cereal import log
from openpilot.common.mock.generators import generate_deviceMotion
from openpilot.common.params import Params
from openpilot.common.prefix import OpenpilotPrefix
from openpilot.common.realtime import DT_CTRL
from openpilot.selfdrive.car.helpers import convert_to_capnp
from openpilot.selfdrive.controls.lib.latcontrol_torque import LatControlTorque
from openpilot.selfdrive.locationd.helpers import Pose
from openpilot.sunnypilot.selfdrive.car import interfaces as sunnypilot_interfaces
from openpilot.sunnypilot.selfdrive.controls.lib.nnlc.tests.test_nnlc import generate_modelV2

NN_TORQUE = 0.3


def nnlc_controller(car_name):
  params = Params()
  params.put_bool("NeuralNetworkLateralControl", True, block=True)
  CarInterface = interfaces[car_name]
  CP = CarInterface.get_non_essential_params(car_name)
  CP_SP = CarInterface.get_non_essential_params_sp(CP, car_name)
  CI = CarInterface(CP, CP_SP)
  sunnypilot_interfaces.setup_interfaces(CI, params)
  CP_SP = convert_to_capnp(CP_SP)
  controller = LatControlTorque(CP.as_reader(), CP_SP.as_reader(), CI, DT_CTRL)
  return CP, controller


class TestNNLCTuneScale(OpenpilotTestCase):

  def test_nn_feedforward_on_steer_max_mazda(self):
    """Mazda EPS envelope: 800/1200 scale applied to NN torque."""
    with OpenpilotPrefix():
      CP, controller = nnlc_controller(MAZDA.MAZDA_CX5_2022)
      ext = controller.extension
      self.assertFalse(ext._nnlc_enabled)  # no model yet
      ext.update_model_v2(generate_modelV2().modelV2)
      self.assertTrue(ext._nnlc_enabled)
      ext.model.evaluate = lambda _: NN_TORQUE
      ext.model.friction_override = False

      CS = car.CarState.new_message(vEgo=30.0)
      pose = Pose.from_device_motion(generate_deviceMotion().deviceMotion)
      controller.update(True, CS, VehicleModel(CP),
                        log.VehicleParameters.new_message(), False, 0.0, pose, False, 0.2)
      self.assertAlmostEqual(ext._ff, NN_TORQUE * (800 / 1200), places=5)

  def test_nn_feedforward_on_steer_max_toyota(self):
    """Toyota: no EPS ceiling reduction, scale = 1.0."""
    with OpenpilotPrefix():
      CP, controller = nnlc_controller(TOYOTA.TOYOTA_RAV4)
      ext = controller.extension
      self.assertFalse(ext._nnlc_enabled)  # no model yet
      ext.update_model_v2(generate_modelV2().modelV2)
      self.assertTrue(ext._nnlc_enabled)
      ext.model.evaluate = lambda _: NN_TORQUE
      ext.model.friction_override = False

      CS = car.CarState.new_message(vEgo=30.0)
      pose = Pose.from_device_motion(generate_deviceMotion().deviceMotion)
      controller.update(True, CS, VehicleModel(CP),
                        log.VehicleParameters.new_message(), False, 0.0, pose, False, 0.2)
      self.assertAlmostEqual(ext._ff, NN_TORQUE * 1.0, places=5)
