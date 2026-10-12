#!/usr/bin/env python3
"""Independent RadarD using vision primary matching and physical dPath leadTwo."""

from __future__ import annotations

import time
from typing import Any

from opendbc.car.structs import car
from openpilot.cereal import log
import openpilot.cereal.messaging as messaging
from openpilot.common.params import Params
from openpilot.common.realtime import Priority, config_realtime_process
from openpilot.common.runtime_diagnostics import RuntimeDiagnostics
from openpilot.sunnypilot.carrot.radar_motion.native import BACKEND as MOTION_BACKEND
from openpilot.common.swaglog import cloudlog
from opendbc.car.hyundai.values import HyundaiExtFlags
from openpilot.sunnypilot.carrot.radar import effective_radar_track_mode
from openpilot.sunnypilot.carrot.radar_motion.coordinates import device_yaw_to_radar
from openpilot.sunnypilot.carrot.radar_motion.timing import front_radar_distance_delay_s
from openpilot.sunnypilot.carrot.radar_motion import (
  DPathRadarController,
)


CORNER_RADAR_FLAGS = int(
  HyundaiExtFlags.CORNER_RADAR_OBJECTS_235
  | HyundaiExtFlags.CORNER_RADAR_OBJECTS_180
  | HyundaiExtFlags.CORNER_RADAR_OBJECTS_430
)
PRODUCTION_CUT_IN_SENSITIVITY = 3
EMPTY_LEAD = {
  "dRel": 0.0,
  "yRel": 0.0,
  "vRel": 0.0,
  "aRel": 0.0,
  "vLead": 0.0,
  "aLead": 0.0,
  "dPath": 0.0,
  "vLat": 0.0,
  "vLeadK": 0.0,
  "aLeadK": 0.0,
  "fcw": False,
  "status": False,
  "aLeadTau": 0.0,
  "modelProb": 0.0,
  "radar": False,
  "radarTrackId": -1,
  "jLead": 0.0,
  "score": 0.0,
  "cutOutTime": 0.0,
  "cutOutConfidence": 0.0,
}


def empty_lead() -> dict[str, Any]:
  return EMPTY_LEAD.copy()


def _assign_lead(builder: Any, lead: dict[str, Any] | None) -> None:
  """Copy a lead dict into a capnp LeadData builder.

  The dPath output is built against the newer-upstream LeadData schema
  (status/jLead/score/cutOut*), but this fork's log.capnp still ships the
  # older field set (present, no jLead/score). Assign only fields the target
  builder actually declares so the daemon works on either schema.
  """
  data = lead or EMPTY_LEAD
  valid = set(builder.schema.fields.keys())
  # cp calls it `status`; this fork's LeadData renamed the same @11 field to `present`.
  aliases = {"status": "present"}
  for key, value in data.items():
    target = aliases.get(key, key)
    if target in valid:
      setattr(builder, target, value)


def corner_radar_enabled(CP: car.CarParams, enable_corner_radar: int) -> bool:
  return (
    CP.brand == "hyundai"
    and enable_corner_radar > 0
    and bool(int(CP.extFlags) & CORNER_RADAR_FLAGS)
  )


def _yaw_rate(live_pose: Any) -> float:
  angular_velocity = getattr(live_pose, "angularVelocityDevice", None)
  if (
    angular_velocity is not None
    and bool(getattr(angular_velocity, "valid", False))
    and bool(getattr(live_pose, "inputsOK", False))
    and bool(getattr(live_pose, "sensorsOK", False))
  ):
    value = float(getattr(angular_velocity, "z", 0.0))
    return device_yaw_to_radar(value)
  return 0.0


def _model_measurement_time_s(sm: messaging.SubMaster) -> float:
  """Use the camera exposure time, not model publication time."""
  timestamp_eof_ns = int(getattr(sm["modelV2"], "timestampEof", 0))
  model_log_ns = int(sm.logMonoTime["modelV2"])
  return float(timestamp_eof_ns if timestamp_eof_ns > 0 else model_log_ns) * 1e-9


class DPathRadarD:
  """Own and publish radarState without importing controls.radard."""

  def __init__(self, CP: car.CarParams) -> None:
    params = Params()
    enable_radar_tracks = effective_radar_track_mode(
      CP.brand,
      CP.radarUnavailable,
      params.get_int("EnableRadarTracks"),
    )
    self.controller = DPathRadarController(
      prefer_corner_radar=corner_radar_enabled(
        CP,
        params.get_int("EnableCornerRadar"),
      ),
      enable_radar_tracks=enable_radar_tracks,
      cut_in_sensitivity=PRODUCTION_CUT_IN_SENSITIVITY,
      front_radar_measurement_delay_s=front_radar_distance_delay_s(CP),
      production_live_tracks=True,
    )
    self.radar_state = log.RadarState.new_message()
    self.radar_state_valid = False

  def update(self, sm: messaging.SubMaster, rr: car.RadarData) -> None:
    self.radar_state_valid = sm.all_checks()
    # Reuse the builder like conventional radard. Reallocating every 20 Hz
    # frame is measurable on device and does not change any published field.
    self.radar_state.mdMonoTime = sm.logMonoTime["modelV2"]
    # carStateMonoTime and the extended lead lists only exist on newer-upstream
    # RadarState schemas; this fork's log.capnp still ships leadOne/leadTwo
    # only. Set them when present so the daemon runs on either schema.
    if hasattr(self.radar_state, "carStateMonoTime"):
      self.radar_state.carStateMonoTime = sm.logMonoTime["carState"]
    self.radar_state.radarErrors = rr.errors

    model_time_s = _model_measurement_time_s(sm)
    radar_time_s = float(sm.logMonoTime["liveTracks"]) * 1e-9
    time_s = (
      model_time_s
      if model_time_s > 0.0
      else 1e-9 * max(sm.logMonoTime.values())
    )
    output = self.controller.update(
      time_s=time_s,
      v_ego=float(sm["carState"].vEgo),
      radar_points=rr.points,
      model=sm["modelV2"],
      yaw_rate_rad_s=_yaw_rate(sm["deviceMotion"]),
      radar_to_model_time_s=model_time_s - radar_time_s,
    )
    _assign_lead(self.radar_state.leadOne, output.lead_one)
    _assign_lead(self.radar_state.leadTwo, output.lead_two)
    # Optional multi-lead fields from newer schemas; skip when not declared.
    optional_leads = (
      ("leadLeft", output.lead_left),
      ("leadRight", output.lead_right),
      ("leadCutInRisk", output.lead_cutin_risk),
    )
    for field_name, value in optional_leads:
      if hasattr(self.radar_state, field_name):
        _assign_lead(getattr(self.radar_state, field_name), value)
    optional_lead_lists = (
      ("leadsLeft", output.leads_left),
      ("leadsCenter", output.leads_center),
      ("leadsRight", output.leads_right),
      ("leadsCutIn", output.leads_cutin),
      ("leadsLeft2", output.leads_left2),
      ("leadsRight2", output.leads_right2),
    )
    for field_name, value in optional_lead_lists:
      if hasattr(self.radar_state, field_name):
        field = getattr(self.radar_state, field_name)
        field.init(len(value))
        for builder, lead_dict in zip(field, value, strict=False):
          _assign_lead(builder, lead_dict)

  def publish(self, pm: messaging.PubMaster) -> None:
    radar_msg = messaging.new_message("radarState")
    radar_msg.valid = self.radar_state_valid
    radar_msg.radarState = self.radar_state
    pm.send("radarState", radar_msg)


def main() -> None:
  config_realtime_process(5, Priority.CTRL_LOW)

  cloudlog.info("dPath radard is waiting for CarParams")
  CP = messaging.log_from_bytes(
    Params().get("CarParams", block=True),
    car.CarParams,
  )
  cloudlog.info("dPath radard got CarParams")

  # This fork has no livePose service/schema (newer-upstream): locationd still
  # publishes deviceMotion at 20Hz, which carries the same angularVelocityDevice
  # .z / inputsOK / sensorsOK fields _yaw_rate reads. controlsd/lagd subscribe to
  # deviceMotion too. ignore_alive/valid keeps a missing pose from failing checks.
  sm = messaging.SubMaster(
    ["modelV2", "carState", "liveTracks", "deviceMotion"],
    poll="modelV2",
    ignore_alive=["deviceMotion"],
    ignore_valid=["deviceMotion"],
  )
  pm = messaging.PubMaster(["radarState"])
  radar = DPathRadarD(CP)
  diagnostics = RuntimeDiagnostics('radard', cloudlog.event)

  while True:
    sm.update()
    if sm.updated["modelV2"]:
      start, cpu_start = time.monotonic(), time.thread_time()
      radar.update(sm, sm["liveTracks"])
      radar.publish(pm)
      diagnostics.record(context={'motion_backend': MOTION_BACKEND}, work_ms=(time.monotonic() - start) * 1000,
                         thread_cpu_ms=(time.thread_time() - cpu_start) * 1000,
                         model_age_ms=(start - sm.logMonoTime['modelV2'] * 1e-9) * 1000,
                         tracks_age_ms=(start - sm.logMonoTime['liveTracks'] * 1e-9) * 1000)


if __name__ == "__main__":
  main()
