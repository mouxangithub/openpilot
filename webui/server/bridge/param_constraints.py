"""Mirror UIStateSP._enforce_constraints after WebUI param writes."""

from __future__ import annotations

from typing import Any


def _refresh_ctx() -> Any:
  from webui.server.bridge.car_context import get_car_context, refresh_car_context

  try:
    from webui.server.bridge.state_hub import get_shared_sm

    sm = get_shared_sm()
    started = False
    if sm is not None and sm.valid.get("deviceState"):
      started = bool(sm["deviceState"].started)
    refresh_car_context(sm, started)
  except Exception:
    pass
  return get_car_context()


def enforce_param_constraints(p: Any | None = None) -> None:
  """Clear invalid param combinations (matches sunnypilot native UI)."""
  try:
    from opendbc.car.structs import car

    if p is None:
      from openpilot.common.params import Params
      p = Params()

    ctx = _refresh_ctx()
    CP = ctx.CP
    CP_SP = ctx.CP_SP
    has_long = ctx.has_longitudinal_control
    has_icbm = ctx.has_icbm

    if CP is not None:
      if p.get_bool("EnforceTorqueControl") and p.get_bool("NeuralNetworkLateralControl"):
        p.put_bool("EnforceTorqueControl", False, block=True)
        p.put_bool("NeuralNetworkLateralControl", False, block=True)

      if p.get_bool("LateralJerkTorqueController") and p.get_bool("NeuralNetworkLateralControl"):
        p.put_bool("LateralJerkTorqueController", False, block=True)
        p.put_bool("NeuralNetworkLateralControl", False, block=True)

      if CP.steerControlType == car.CarParams.SteerControlType.angle:
        p.remove("EnforceTorqueControl")
        p.remove("NeuralNetworkLateralControl")
        p.remove("LateralJerkTorqueController")

      if not CP.alphaLongitudinalAvailable:
        p.remove("AlphaLongitudinalEnabled")

      if not CP.enableBsm:
        p.remove("AutoLaneChangeBsmDelay")
    else:
      p.remove("EnforceTorqueControl")
      p.remove("NeuralNetworkLateralControl")
      p.remove("LateralJerkTorqueController")
      p.remove("AlphaLongitudinalEnabled")

    if not has_long:
      p.remove("ExperimentalMode")
      p.remove("DynamicExperimentalControl")

    if CP_SP is not None:
      if not CP_SP.intelligentCruiseButtonManagementAvailable or has_long:
        p.remove("IntelligentCruiseButtonManagement")
        has_icbm = False
    else:
      p.remove("IntelligentCruiseButtonManagement")
      has_icbm = False

    if not (has_long or has_icbm):
      p.remove("CustomAccIncrementsEnabled")
      p.remove("SmartCruiseControlVision")
      p.remove("SmartCruiseControlMap")

    if not ctx.sla_available:
      try:
        mode = int(p.get("SpeedLimitMode", return_default=True) or 0)
        if mode == 3:
          p.put("SpeedLimitMode", 2, block=True)
      except Exception:
        pass
  except Exception:
    pass
