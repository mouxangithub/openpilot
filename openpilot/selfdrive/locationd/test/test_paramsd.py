import random
import numpy as np

from openpilot.common.test import OpenpilotTestCase
from openpilot.cereal import log, messaging
from opendbc.car.structs import car
from openpilot.selfdrive.locationd.paramsd import retrieve_initial_vehicle_params, VehicleParamsLearner
from openpilot.selfdrive.locationd.models.car_kf import CarKalman
from openpilot.selfdrive.locationd.test.test_locationd_scenarios import TEST_ROUTE
from openpilot.selfdrive.test.process_replay.migration import migrate, migrate_carParams
from openpilot.common.params import Params
from openpilot.tools.lib.logreader import LogReader


def get_random_vehicle_parameters(CP):
  msg = messaging.new_message("vehicleParameters")
  msg.vehicleParameters.steerRatio = (random.random() + 0.5) * CP.steerRatio
  msg.vehicleParameters.stiffnessFactor = random.random()
  msg.vehicleParameters.angleOffsetAverageDeg = random.random()
  msg.vehicleParameters.debugFilterState.std = [random.random() for _ in range(CarKalman.P_initial.shape[0])]
  return msg


class TestParamsd(OpenpilotTestCase):
  def test_read_saved_params(self):
    params = Params()

    lr = migrate(LogReader(TEST_ROUTE), [migrate_carParams])
    CP = next(m for m in lr if m.which() == "carParams").carParams

    msg = get_random_vehicle_parameters(CP)
    params.put("LiveParametersV2", msg.to_bytes(), block=True)
    params.put("CarParamsPrevRoute", CP.as_builder().to_bytes(), block=True)

    sr, sf, offset, p_init = retrieve_initial_vehicle_params(params, CP, replay=True, debug=True)
    np.testing.assert_allclose(sr, msg.vehicleParameters.steerRatio)
    np.testing.assert_allclose(sf, msg.vehicleParameters.stiffnessFactor)
    np.testing.assert_allclose(offset, msg.vehicleParameters.angleOffsetAverageDeg)
    np.testing.assert_equal(p_init.shape, CarKalman.P_initial.shape)
    np.testing.assert_allclose(np.diagonal(p_init), msg.vehicleParameters.debugFilterState.std)

  def test_freeze_learning_until_imu_calibration_complete(self):
    """paramsd must not learn vehicle parameters while IMU calibration is incomplete."""
    lr = migrate(LogReader(TEST_ROUTE), [migrate_carParams])
    CP = next(m for m in lr if m.which() == "carParams").carParams

    learner = VehicleParamsLearner(CP, CP.steerRatio, 1.0, 0.0)

    # Uncalibrated extrinsics (dynamic collecting) must keep the learner inactive.
    ec = messaging.new_message("extrinsicsCalibration").extrinsicsCalibration
    ec.calStatus = log.ExtrinsicsCalibration.Status.uncalibrated
    ec.rpyCalib = [0.0, 0.0, 0.0]
    learner.handle_log(0.0, "extrinsicsCalibration", ec)

    cs = messaging.new_message("carState").carState
    cs.vEgo = 15.0
    cs.steeringAngleDeg = 0.0
    cs.gearShifter = car.CarState.GearShifter.drive
    learner.handle_log(1.0, "carState", cs)
    self.assertFalse(learner.active)

    # Completed calibration with a valid matrix allows learning to resume.
    ec2 = messaging.new_message("extrinsicsCalibration").extrinsicsCalibration
    ec2.calStatus = log.ExtrinsicsCalibration.Status.calibrated
    ec2.rpyCalib = [0.0, 0.0, 0.0]
    ec2.imuCalibMatrix = np.eye(3, dtype=np.float32).flatten().tolist()
    learner.handle_log(2.0, "extrinsicsCalibration", ec2)

    learner.handle_log(3.0, "carState", cs)
    self.assertTrue(learner.active)
