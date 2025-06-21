import pytest
from cereal import car, log

from openpilot.sunnypilot.livedelay.lagd_toggle import LagdToggle


class TestLagdToggle:
  def setup_method(self):
    self.lagd_toggle = LagdToggle()

  @pytest.mark.parametrize("toggle_on,lateral_delay,lat_smooth,expected", [
    (True, 0.3, 0.2, 0.5),   # toggle_on, lateral_delay, lat_smooth, expected
    (False, 0.1, 0.2, 0.454), # toggle_off case: 0.15 + 0.104 + 0.2
    (True, 0.25, 0.1, 0.35),   # different values
    (False, 0.104, 0.3, 0.554), # random toggle_off values
  ])
  def test_lagd_main(self, toggle_on, lateral_delay, lat_smooth, expected, mocker):
    """Test lagd_main with various parameter combinations"""
    mock_params = mocker.Mock()
    mock_params.get_bool.return_value = toggle_on
    mocker.patch('openpilot.sunnypilot.livedelay.lagd_toggle.Params', return_value=mock_params)

    lagd_toggle = LagdToggle()

    # CarParams
    CP = car.CarParams.new_message()
    CP.steerActuatorDelay = 0.15

    # SubMaster
    sm = {"liveDelay": log.LiveDelayData.new_message()}
    sm["liveDelay"].lateralDelay = lateral_delay

    # Create model with LAT_SMOOTH_SECONDS
    class MockModel:
      def __init__(self, lat_smooth):
        self.LAT_SMOOTH_SECONDS = lat_smooth

    model = MockModel(lat_smooth)

    result = lagd_toggle.lagd_main(CP, sm, model)

    assert abs(result - expected) < 1e-6
    mock_params.get_bool.assert_called_with("LagdToggle")


  @pytest.mark.parametrize("toggle_on,lateral_delay,expected", [
    (True, 0.12, 0.12),    # toggle_on, lateral_delay, expected
    (False, 0.12, 0.254),  # toggle_off case: 0.15 + 0.104 = 0.254
    (True, 0.09, 0.09),    # different values
    (False, 0.15, 0.254),  # different toggle_off values: 0.15 + 0.104 = 0.254
  ])
  def test_lagd_torqued_main(self, toggle_on, lateral_delay, expected, mocker):
    """Test lagd_torqued_main with various parameter combinations"""
    mock_params = mocker.Mock()
    mock_params.get_bool.return_value = toggle_on
    mocker.patch('openpilot.sunnypilot.livedelay.lagd_toggle.Params', return_value=mock_params)

    lagd_toggle = LagdToggle()

    # CarParams
    CP = car.CarParams.new_message()
    CP.steerActuatorDelay = 0.15

    # liveDelayMessage
    msg = log.LiveDelayData.new_message()
    msg.lateralDelay = lateral_delay

    result = lagd_toggle.lagd_torqued_main(CP, msg)

    assert abs(result - expected) < 1e-6
    assert abs(lagd_toggle.lag - expected) < 1e-6
    mock_params.get_bool.assert_called_with("LagdToggle")


  def test_software_delay_constant(self):
    """Test that software_delay constant is properly set"""
    assert self.lagd_toggle.software_delay == 0.104

  def test_initial_lag_value(self):
    lagd = LagdToggle()
    assert lagd.lag == 0.0

  @pytest.mark.parametrize("steer_delay,lat_smooth", [
    (0.123456, 0.987654),
    (0.05, 0.1),
    (0.2, 0.3),
  ])
  def test_delay_calculation_precision(self, steer_delay, lat_smooth, mocker):
    mock_params = mocker.Mock()
    mocker.patch('openpilot.sunnypilot.livedelay.lagd_toggle.Params', return_value=mock_params)

    # Test toggle on path precision
    mock_params.get_bool.return_value = True
    lagd_toggle = LagdToggle()

    CP = car.CarParams.new_message()
    CP.steerActuatorDelay = steer_delay

    sm = {"liveDelay": log.LiveDelayData.new_message()}
    sm["liveDelay"].lateralDelay = steer_delay

    class MockModel:
      def __init__(self, lat_smooth):
        self.LAT_SMOOTH_SECONDS = lat_smooth

    model = MockModel(lat_smooth)

    result = lagd_toggle.lagd_main(CP, sm, model)
    expected = steer_delay + lat_smooth
    assert abs(result - expected) < 1e-6

    # Test toggle off path precision
    mock_params.get_bool.return_value = False
    lagd_toggle = LagdToggle()
    result = lagd_toggle.lagd_main(CP, sm, model)
    expected = (steer_delay + 0.104) + lat_smooth
    assert abs(result - expected) < 1e-6

  def test_params_integration(self, mocker):
    mock_params = mocker.Mock()
    mock_params.get_bool.return_value = True
    mocker.patch('openpilot.sunnypilot.livedelay.lagd_toggle.Params', return_value=mock_params)

    lagd_toggle = LagdToggle()

    CP = car.CarParams.new_message()
    msg = log.LiveDelayData.new_message()

    lagd_toggle.lagd_torqued_main(CP, msg)
    mock_params.get_bool.assert_called_with("LagdToggle")
