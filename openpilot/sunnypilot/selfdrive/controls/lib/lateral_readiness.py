"""Startup lateral-readiness gate, ported from CarrotPilot.

CarrotPilot blocks steering during the first startup until lateral inputs and
CAN transmission are ready. This fork does not publish livePose/lateralPlan
(the cp lateral stack), so the checks are adapted to the services sunnypilot
actually publishes: vehicleParameters (learned geometry), deviceMotion (pose),
modelV2, selfdriveState and onroadEvents.
"""
import math
from dataclasses import dataclass


LATERAL_SERVICES = ('modelV2', 'vehicleParameters', 'deviceMotion', 'selfdriveState', 'onroadEvents')


@dataclass
class LateralStartupGate:
  # One-way, process-lifetime latch. Engagement changes and later input failures
  # do not rearm this startup check; existing runtime safety policy owns those.
  ready: bool = False

  def update(self, sm, CS, boundary_service):
    if not self.ready:
      self.ready = service_ready(sm, boundary_service) and lateral_inputs_ready(sm, CS)
    return self.ready


def service_ready(sm, service):
  # A default SubMaster message is not an input, even during startup grace.
  if service == 'onroadEvents':
    # selfdrived publishes a 1 Hz heartbeat AND every event change. Pedal or
    # steering-override transitions legitimately exceed the fixed rate's upper
    # bound. Keep receipt, validity and liveness checks without rejecting bursts.
    return sm.seen[service] and sm.valid[service] and sm.alive[service]
  return sm.seen[service] and sm.all_checks([service])


def vehicle_parameters_ready(sm):
  vp = sm['vehicleParameters']
  return (service_ready(sm, 'vehicleParameters') and vp.valid and vp.sensorValid and vp.posenetValid and
          all(math.isfinite(x) for x in (vp.steerRatio, vp.stiffnessFactor, vp.angleOffsetDeg, vp.roll)) and
          vp.steerRatio > 1.0 and vp.stiffnessFactor > 0.0)


@dataclass(frozen=True)
class NominalVehicleParameters:
  steerRatio: float
  stiffnessFactor: float = 1.0
  angleOffsetDeg: float = 0.0
  roll: float = 0.0


def lateral_vehicle_parameters(sm, CP):
  # Keep nominal geometry while live inputs are absent/invalid. This fallback
  # is for inactive calculations; it does not grant permission to steer. (cp
  # parity, adapted from liveParameters to the vehicleParameters service.)
  return sm['vehicleParameters'] if vehicle_parameters_ready(sm) else NominalVehicleParameters(CP.steerRatio)


def lateral_inputs_ready(sm, CS):
  if not all(service_ready(sm, s) for s in LATERAL_SERVICES):
    return False

  if not vehicle_parameters_ready(sm):
    return False

  if not CS.canValid or CS.steerFaultTemporary or CS.steerFaultPermanent:
    return False
  if not all(math.isfinite(x) for x in (CS.vEgo, CS.steeringAngleDeg, CS.steeringRateDeg, CS.steeringTorque)):
    return False

  if any(e.name == 'selfdriveInitializing' for e in sm['onroadEvents']):
    return False

  pose = sm['deviceMotion']
  if not (pose.inputsOK and pose.posenetOK and pose.sensorsOK):
    return False
  if not math.isfinite(sm['modelV2'].action.desiredCurvature):
    return False

  # This fork does not publish the cp lateralPlan stack; model-only control
  # needs exactly the common lateral inputs checked above.
  return True
