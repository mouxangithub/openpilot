#!/usr/bin/env python3
from openpilot.cereal import custom
from opendbc.car.structs import car
from openpilot.common.gps import get_gps_location_service
from openpilot.common.params import Params
from openpilot.common.realtime import Priority, config_realtime_process
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.controls.lib.ldw import LaneDepartureWarning
from openpilot.selfdrive.controls.lib.longitudinal_planner import LongitudinalPlanner
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_stopping_lead import StoppingLeadFilter
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_fast_radar import FastRadarOverlay, RadarStateOverride
from openpilot.sunnypilot.carrot.radar import effective_radar_track_mode
from openpilot.sunnypilot.carrot.radar_motion.timing import front_radar_distance_delay_s
import openpilot.cereal.messaging as messaging


def main():
  config_realtime_process(5, Priority.CTRL_LOW)

  cloudlog.info("plannerd is waiting for CarParams")
  params = Params()
  CP = messaging.log_from_bytes(params.get("CarParams", block=True), car.CarParams)
  cloudlog.info("plannerd got CarParams: %s", CP.brand)

  cloudlog.info("plannerd is waiting for CarParamsSP")
  CP_SP = messaging.log_from_bytes(params.get("CarParamsSP", block=True), custom.CarParamsSP)
  cloudlog.info("plannerd got CarParamsSP")

  gps_location_service = get_gps_location_service(params)
  # carrotManSP / carrotNaviSP / navInstructionCarrotSP are only
  # published while CarrotEnabled is on, so they must not fail all_checks
  # when that daemon is absent.
  ignore_services = ["liveMapDataSP", "carStateSP", "selfdriveStateSP", "carrotManSP", "carrotNaviSP",
                     "navInstructionCarrotSP", gps_location_service]

  ldw = LaneDepartureWarning()
  longitudinal_planner = LongitudinalPlanner(CP, CP_SP)
  stopping_lead_filter = StoppingLeadFilter()
  # Carrot follow refinement (default off): require range evidence before a
  # stopped lead counts as departing. Read once at startup like cp does; the
  # stock ACC path is unchanged while the param stays "0".
  stopping_lead_enabled = params.get_bool("CarrotStoppingLeadEnabled")
  # Carrot fast-radar (default off): refresh an already-selected lead's
  # kinematics from a newer liveTracks frame without promoting a new track.
  # CarrotPilot keeps this Hyundai-only; the brand check is preserved here.
  fast_radar_enabled = params.get_bool("CarrotFastRadarEnabled")
  radar_track_mode = effective_radar_track_mode(CP.brand, CP.radarUnavailable, params.get_int("EnableRadarTracks"))
  live_tracks_longitudinal = fast_radar_enabled and CP.brand == "hyundai" and radar_track_mode >= 1
  fast_radar = FastRadarOverlay(front_radar_delay_s=front_radar_distance_delay_s(CP))
  live_tracks_services = ['liveTracks'] if fast_radar_enabled else []
  pm = messaging.PubMaster(['longitudinalPlan', 'driverAssistance', 'longitudinalPlanSP'])
  sm = messaging.SubMaster(['carControl', 'carState', 'controlsState', 'vehicleParameters', 'radarState', 'modelV2', 'selfdriveState',
                            'liveMapDataSP', 'carStateSP', 'selfdriveStateSP', 'carrotManSP', 'carrotNaviSP',
                            'navInstructionCarrotSP', gps_location_service] + live_tracks_services,
                           poll='modelV2', ignore_alive=ignore_services + live_tracks_services,
                           ignore_avg_freq=ignore_services + live_tracks_services,
                           ignore_valid=ignore_services + live_tracks_services)

  while True:
    sm.update()
    longitudinal_planner.sla.update_buttons(sm['selfdriveStateSP'].buttonsReleaseToggle)
    if fast_radar_enabled and sm.updated.get('radarState'):
      fast_radar.observe_radar_state(
        sm['radarState'], sm.logMonoTime['radarState'],
        sm.valid.get('radarState', False) and sm.alive.get('radarState', False),
      )
    if sm.updated['modelV2']:
      planner_sm = sm
      # Carrot fast-radar (default off): only replaces the selected lead's
      # kinematics with a newer same-track liveTracks observation. It never
      # promotes a new track and is Hyundai-only, matching CarrotPilot.
      if live_tracks_longitudinal and sm.seen.get('liveTracks', False) and sm.valid.get('liveTracks', False):
        if fast_radar.lead_one_ready(sm['radarState']):
          fast_result = fast_radar.build(
            sm['radarState'], sm['liveTracks'], sm['carState'].vEgo,
            sm.logMonoTime['radarState'], sm.logMonoTime['liveTracks'],
            radar_state_valid=sm.valid['radarState'] and sm.alive['radarState'],
            live_tracks_valid=sm.valid['liveTracks'] and sm.alive['liveTracks'],
          )
          planner_sm = RadarStateOverride(planner_sm, fast_result.radar_state)

      # Carrot stopping-lead conditioning (default off). Freezes a stopped lead's
      # dynamics on the planner input copy until range evidence shows departure,
      # so a quantized range step cannot be read as the lead moving off. Only the
      # planner's view of radarState is substituted; raw radar is untouched.
      if stopping_lead_enabled and CP.openpilotLongitudinalControl:
        stopping_radar_state = stopping_lead_filter.update(
          planner_sm['radarState'],
          stopping=(sm['controlsState'].longControlState == car.CarControl.Actuators.LongControlState.stopping
                    and not sm['selfdriveState'].experimentalMode
                    and not sm['carState'].gasPressed),
          v_ego=sm['carState'].vEgo,
          mono_time_ns=sm.logMonoTime['radarState'],
          valid=(sm.valid['radarState'] and sm.alive['radarState']
                 and sm.valid['carState'] and sm.alive['carState']),
        )
        planner_sm = RadarStateOverride(planner_sm, stopping_radar_state)

      longitudinal_planner.update(planner_sm)
      longitudinal_planner.publish(planner_sm, pm)

      ldw.update(sm.frame, sm['modelV2'], sm['carState'], sm['carControl'])
      msg = messaging.new_message('driverAssistance')
      msg.valid = sm.all_checks()
      msg.driverAssistance.leftLaneDeparture = ldw.left
      msg.driverAssistance.rightLaneDeparture = ldw.right
      pm.send('driverAssistance', msg)


if __name__ == "__main__":
  main()
