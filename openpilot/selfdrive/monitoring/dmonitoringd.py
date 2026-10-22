#!/usr/bin/env python3
import math
import time

import openpilot.cereal.messaging as messaging
from opendbc.car.structs import car
from openpilot.common.params import Params
from openpilot.common.realtime import config_realtime_process
from openpilot.selfdrive.monitoring.policy import DriverMonitoring

# A soft hold is the vehicle's own standstill brake (e.g. waiting at a light).
# The driver is expected to look away from the road there, so driver monitoring
# must not count that against them.
SOFT_HOLD_SPEED_MPS = 0.1
SOFT_HOLD_MAX_AGE_S = 0.25


def soft_hold_pause_eligible(sm, now, demo=False):
  """True only for a current, stationary soft hold in a driving gear.

  Assessment pauses, not the monitor: the camera keeps running and publication
  continues at the normal cadence, so consumer health checks and the UI still
  see a fresh packet. Every uncertain input fails closed.
  """
  services = ['carState', 'selfdriveState']
  if demo:
    return False
  if not sm.all_checks(services):
    return False
  if not all(0 <= now - sm.recv_time[s] <= SOFT_HOLD_MAX_AGE_S for s in services):
    return False
  cs = sm['carState']
  soft_hold = int(getattr(cs, 'softHoldActive', 0) or 0)
  v_ego, v_ego_raw = float(cs.vEgo), float(cs.vEgoRaw)
  return (
    cs.canValid and soft_hold > 0 and cs.standstill and not cs.gasPressed and
    cs.gearShifter in (car.CarState.GearShifter.drive, car.CarState.GearShifter.low) and
    math.isfinite(v_ego) and math.isfinite(v_ego_raw) and
    abs(v_ego) < SOFT_HOLD_SPEED_MPS and abs(v_ego_raw) < SOFT_HOLD_SPEED_MPS
  )


def soft_hold_state_packet(monitor, valid=True):
  """Publish a normal-cadence packet that carries no DM penalty.

  alertLevel stays 'none' and every lockout/count is zeroed, so the alert
  manager and forced deceleration cannot act on a hold. Driver-facing evidence
  (pose, RHD calibration, camera health) is left intact: this is a pause, not a
  loss of monitoring.
  """
  dat = monitor.get_state_packet(valid=valid)
  state = dat.driverMonitoringState
  state.lockout = False
  state.alertCountLockoutPercent = 0
  state.alertTimeLockoutPercent = 0
  state.lockoutRecoveryPercent = 0
  state.alert3Count = 0
  state.noResponseCount = 0
  state.noResponseForceDecel = False
  state.alwaysOnLockout = False
  state.alertLevel = 'none'
  state.visionPolicyState.awarenessPercent = 100
  state.visionPolicyState.awarenessStep = 0
  state.visionPolicyState.isDistracted = False
  state.visionPolicyState.distractedTypes.pose = False
  state.visionPolicyState.distractedTypes.eye = False
  state.visionPolicyState.distractedTypes.phone = False
  return dat


def dmonitoringd_thread():
  config_realtime_process([0, 1, 2, 3], 5)

  params = Params()
  pm = messaging.PubMaster(['driverMonitoringState'])
  sm = messaging.SubMaster(['driverStateV2', 'extrinsicsCalibration', 'carState', 'selfdriveState', 'modelV2',
                            'carControl'], poll='driverStateV2')

  DM = DriverMonitoring(
    rhd_saved=params.get_bool("IsRhdDetected"),
    always_on=params.get_bool("AlwaysOnDM"),
    distraction_detection_level=int(params.get("DistractionDetectionLevel") or 1),
  )
  demo_mode = False

  # 20Hz <- dmonitoringmodeld
  while True:
    sm.update()
    if not sm.updated['driverStateV2']:
      # iterate when model has new output
      continue

    valid = sm.all_checks()
    if soft_hold_pause_eligible(sm, time.monotonic(), demo_mode):
      # Normal cadence, no run_step(): awareness and the alert/lockout counters
      # stay frozen. Neither enable Param is written and the parked state is
      # not reset, so leaving the hold resumes exactly where it stopped.
      pm.send('driverMonitoringState', soft_hold_state_packet(DM, valid=valid))
      continue
    if DM.always_on and demo_mode and sm.valid['driverStateV2']:
      DM.run_step(sm, demo=True)
      DM.set_distract_level_params()
    elif DM.always_on and valid:
      DM.run_step(sm, demo=demo_mode)
      DM.set_distract_level_params()

    # publish
    dat = DM.get_state_packet(valid=valid)
    pm.send('driverMonitoringState', dat)

    # load live always-on toggle
    if sm['driverStateV2'].frameId % 40 == 1:
      DM.always_on = params.get_bool("AlwaysOnDM")
      demo_mode = params.get_bool("IsDriverViewEnabled")
      DM.distraction_detection_level = int(params.get("DistractionDetectionLevel") or 0)

    # save rhd virtual toggle every 5 mins
    if (sm['driverStateV2'].frameId % 6000 == 0 and not demo_mode and
     DM.wheelpos_offsetter.filtered_stat.n > DM.settings._WHEELPOS_FILTER_MIN_COUNT and
     DM.wheel_on_right == (DM.wheelpos_offsetter.filtered_stat.M > DM.settings._WHEELPOS_THRESHOLD)):
      params.put_bool("IsRhdDetected", DM.wheel_on_right)

def main():
  dmonitoringd_thread()


if __name__ == '__main__':
  main()
