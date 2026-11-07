"""Tests for param_constraints.py — mutual exclusion and write-time validation."""

import sys
import unittest
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, '..')

from webui.server.bridge.param_constraints import enforce_param_constraints


class TestParamConstraints(unittest.TestCase):
  """Test the constraint enforcement logic."""

  def setUp(self):
    self.params = MagicMock()
    self.params.get_bool = MagicMock(return_value=False)
    self.params.put_bool = MagicMock()
    self.params.put = MagicMock()
    self.params.remove = MagicMock()
    self.params.get = MagicMock(return_value=None)

  def _ctx(self, **overrides):
    """Build a mock car context."""
    ctx = MagicMock()
    ctx.CP = None
    ctx.CP_SP = None
    ctx.has_longitudinal_control = False
    ctx.has_icbm = False
    ctx.brand = ""
    ctx.mads_limited = False
    ctx.sla_available = True
    for k, v in overrides.items():
      setattr(ctx, k, v)
    return ctx

  def _assert_put_bool(self, key, value):
    """Assert that put_bool was called with the given key and value."""
    for c in self.params.put_bool.call_args_list:
      if len(c[0]) >= 2 and c[0][0] == key and c[0][1] == value:
        return
    self.fail(f"Expected put_bool({key}, {value}) not found in {self.params.put_bool.call_args_list}")

  def _assert_put(self, key, value):
    """Assert that put was called with the given key and value."""
    for c in self.params.put.call_args_list:
      if len(c[0]) >= 2 and c[0][0] == key and c[0][1] == value:
        return
    self.fail(f"Expected put({key}, {value}) not found in {self.params.put.call_args_list}")

  @patch('webui.server.bridge.param_constraints._refresh_ctx')
  def test_nnlc_enforce_torque_mutual_exclusion(self, mock_ctx):
    """NNLC and EnforceTorqueControl cannot both be on."""
    mock_ctx.return_value = self._ctx()
    self.params.get_bool.side_effect = lambda k: {
      "NeuralNetworkLateralControl": True,
      "EnforceTorqueControl": True,
      "LateralJerkTorqueController": False,
    }.get(k, False)

    enforce_param_constraints(self.params)

    self._assert_put_bool("EnforceTorqueControl", False)
    self._assert_put_bool("NeuralNetworkLateralControl", False)

  @patch('webui.server.bridge.param_constraints._refresh_ctx')
  def test_nnlc_lateral_jerk_mutual_exclusion(self, mock_ctx):
    """NNLC and LateralJerkTorqueController cannot both be on."""
    mock_ctx.return_value = self._ctx()
    self.params.get_bool.side_effect = lambda k: {
      "NeuralNetworkLateralControl": True,
      "EnforceTorqueControl": False,
      "LateralJerkTorqueController": True,
    }.get(k, False)

    enforce_param_constraints(self.params)

    self._assert_put_bool("LateralJerkTorqueController", False)
    self._assert_put_bool("NeuralNetworkLateralControl", False)

  @patch('webui.server.bridge.param_constraints._refresh_ctx')
  def test_enforce_torque_lateral_jerk_mutual_exclusion(self, mock_ctx):
    """EnforceTorqueControl and LateralJerkTorqueController cannot both be on."""
    mock_ctx.return_value = self._ctx()
    self.params.get_bool.side_effect = lambda k: {
      "NeuralNetworkLateralControl": False,
      "EnforceTorqueControl": True,
      "LateralJerkTorqueController": True,
    }.get(k, False)

    enforce_param_constraints(self.params)

    self._assert_put_bool("LateralJerkTorqueController", False)
    self._assert_put_bool("EnforceTorqueControl", False)

  @patch('webui.server.bridge.param_constraints._refresh_ctx')
  def test_alpha_long_icbm_mutual_exclusion(self, mock_ctx):
    """AlphaLongitudinalEnabled and IntelligentCruiseButtonManagement cannot both be on."""
    mock_ctx.return_value = self._ctx()
    self.params.get_bool.side_effect = lambda k: {
      "AlphaLongitudinalEnabled": True,
      "IntelligentCruiseButtonManagement": True,
    }.get(k, False)

    enforce_param_constraints(self.params)

    self._assert_put_bool("IntelligentCruiseButtonManagement", False)

  @patch('webui.server.bridge.param_constraints._refresh_ctx')
  def test_mads_limited_platform_rewrite(self, mock_ctx):
    """MADS limited platforms force specific MADS params."""
    mock_ctx.return_value = self._ctx(mads_limited=True)
    self.params.get_bool.side_effect = lambda k: {
      "MadsMainCruiseAllowed": True,
      "MadsUnifiedEngagementMode": False,
    }.get(k, False)
    self.params.get.side_effect = lambda k, **kw: {"MadsSteeringMode": 2}.get(k)

    enforce_param_constraints(self.params)

    self._assert_put_bool("MadsMainCruiseAllowed", False)
    self._assert_put_bool("MadsUnifiedEngagementMode", True)
    self._assert_put("MadsSteeringMode", 0)

  @patch('webui.server.bridge.param_constraints._refresh_ctx')
  def test_toyota_enforce_stock_clears_others(self, mock_ctx):
    """ToyotaEnforceStockLongitudinal clears AlphaLongitudinal and other Toyota hacks."""
    mock_ctx.return_value = self._ctx(brand="toyota")
    self.params.get_bool.side_effect = lambda k: {
      "ToyotaEnforceStockLongitudinal": True,
      "AlphaLongitudinalEnabled": True,
      "ToyotaStopAndGoHack": True,
      "ToyotaTSS2Smooth": True,
    }.get(k, False)

    enforce_param_constraints(self.params)

    self._assert_put_bool("AlphaLongitudinalEnabled", False)
    self._assert_put_bool("ToyotaStopAndGoHack", False)
    self._assert_put_bool("ToyotaTSS2Smooth", False)

  @patch('webui.server.bridge.param_constraints._refresh_ctx')
  def test_live_torque_toggle_off_clears_relaxed(self, mock_ctx):
    """LiveTorqueParamsToggle off clears LiveTorqueParamsRelaxedToggle."""
    mock_ctx.return_value = self._ctx()
    self.params.get_bool.side_effect = lambda k: {
      "LiveTorqueParamsToggle": False,
      "LiveTorqueParamsRelaxedToggle": True,
    }.get(k, False)

    enforce_param_constraints(self.params)

    self._assert_put_bool("LiveTorqueParamsRelaxedToggle", False)

  @patch('webui.server.bridge.param_constraints._refresh_ctx')
  def test_joystick_clears_maneuvers(self, mock_ctx):
    """JoystickDebugMode clears both maneuver modes."""
    mock_ctx.return_value = self._ctx()
    self.params.get_bool.side_effect = lambda k: {
      "JoystickDebugMode": True,
      "LongitudinalManeuverMode": True,
      "LateralManeuverMode": True,
    }.get(k, False)

    enforce_param_constraints(self.params)

    self._assert_put_bool("LongitudinalManeuverMode", False)
    self._assert_put_bool("LateralManeuverMode", False)

  @patch('webui.server.bridge.param_constraints._refresh_ctx')
  def test_maneuvers_clear_joystick(self, mock_ctx):
    """Maneuver modes clear JoystickDebugMode."""
    mock_ctx.return_value = self._ctx()
    self.params.get_bool.side_effect = lambda k: {
      "JoystickDebugMode": True,
      "LongitudinalManeuverMode": True,
    }.get(k, False)

    enforce_param_constraints(self.params)

    self._assert_put_bool("JoystickDebugMode", False)

  @patch('webui.server.bridge.param_constraints._refresh_ctx')
  def test_chevron_info_no_long_control(self, mock_ctx):
    """ChevronInfo forced to 0 when no longitudinal control."""
    mock_ctx.return_value = self._ctx(has_longitudinal_control=False)
    self.params.get_bool.side_effect = lambda k: False
    self.params.get.side_effect = lambda k, **kw: {"ChevronInfo": 4}.get(k)

    enforce_param_constraints(self.params)

    self._assert_put("ChevronInfo", 0)

  @patch('webui.server.bridge.param_constraints._refresh_ctx')
  def test_speed_limit_mode_assist_downgrade(self, mock_ctx):
    """SpeedLimitMode=Assist forced to Warning when SLA unavailable."""
    mock_ctx.return_value = self._ctx(sla_available=False)
    self.params.get_bool.side_effect = lambda k: False
    self.params.get.side_effect = lambda k, **kw: {"SpeedLimitMode": 3}.get(k)

    enforce_param_constraints(self.params)

    self._assert_put("SpeedLimitMode", 2)


if __name__ == '__main__':
  unittest.main()
