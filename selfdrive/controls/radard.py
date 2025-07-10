#!/usr/bin/env python3
import math
import numpy as np
from collections import deque
from typing import Any

import capnp
from cereal import messaging, log, car
from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.common.params import Params
from openpilot.common.realtime import DT_MDL, Priority, config_realtime_process
from openpilot.common.swaglog import cloudlog
from openpilot.common.simple_kalman import KF1D


# Default lead acceleration decay set to 50% at 1s
_LEAD_ACCEL_TAU = 1.5

# radar tracks
SPEED, ACCEL = 0, 1     # Kalman filter states enum

# stationary qualification parameters
V_EGO_STATIONARY = 4.   # no stationary object flag below this speed

RADAR_TO_CENTER = 2.7   # (deprecated) RADAR is ~ 2.7m ahead from center of car
RADAR_TO_CAMERA = 1.52  # RADAR is ~ 1.5m ahead from center of mesh frame


class Track:
  def __init__(self, identifier: int):
    self.identifier = identifier
    self.cnt = 0
    self.aLeadTau = FirstOrderFilter(_LEAD_ACCEL_TAU, 0.45, DT_MDL)

    self.radar_reaction_factor = Params().get_float("RadarReactionFactor") * 0.01

  def update(self, d_rel: float, y_rel: float, v_rel: float, v_lead: float, a_lead: float, j_lead: float, measured: float):

    self.dRel = d_rel   # LONG_DIST
    self.yRel = y_rel   # -LAT_DIST
    self.vRel = v_rel   # REL_SPEED

    self.vLead = self.vLeadK = v_lead
    self.aLead = self.aLeadK = a_lead
    self.jLead = j_lead
    
    self.measured = measured   # measured or estimate
    a_lead_threshold = 0.5 * self.radar_reaction_factor
    if abs(self.aLead) < a_lead_threshold and abs(j_lead) < 0.5:
      self.aLeadTau.x = _LEAD_ACCEL_TAU * self.radar_reaction_factor
    else:
      self.aLeadTau.update(0.0)

    self.cnt += 1

  def get_RadarState(self, md, model_prob: float = 0.0, vision_y_rel = 0.0):
    yRel = vision_y_rel if vision_y_rel != 0.0 else float(self.yRel)
    dPath = yRel + np.interp(self.dRel, md.position.x, md.position.y)
    return {
      "dRel": float(self.dRel),
      "yRel": float(self.yRel) if vision_y_rel == 0.0 else vision_y_rel,
      "dPath" : float(dPath),
      "vRel": float(self.vRel),
      "vLead": float(self.vLead),
      "vLeadK": float(self.vLeadK),
      "aLead": float(self.aLead),
      "aLeadK": float(self.aLeadK),
      "aLeadTau": float(self.aLeadTau.x),
      "jLead": float(self.jLead),
      "status": True,
      "fcw": self.is_potential_fcw(model_prob),
      "modelProb": model_prob,
      "radar": True,
      "radarTrackId": self.identifier,
    }

  def potential_low_speed_lead(self, v_ego: float):
    # stop for stuff in front of you and low speed, even without model confirmation
    # Radar points closer than 0.75, are almost always glitches on toyota radars
    return abs(self.yRel) < 1.0 and (v_ego < V_EGO_STATIONARY) and (0.75 < self.dRel < 25)

  def is_potential_fcw(self, model_prob: float):
    return model_prob > .9

  def __str__(self):
    ret = f"x: {self.dRel:4.1f}  y: {self.yRel:4.1f}  v: {self.vRel:4.1f}  a: {self.aLeadK:4.1f}"
    return ret

def laplacian_pdf(x: float, mu: float, b: float):
  diff = abs(x - mu) / max(b, 1e-4)
  return 0.0 if diff > 50.0 else math.exp(-diff)

def match_vision_to_track(v_ego: float, lead: capnp._DynamicStructReader, tracks: dict[int, Track]):
  offset_vision_dist = lead.x[0] - RADAR_TO_CAMERA
  vel_tolerance = 25.0 if lead.prob > 0.99 else 10.0
  max_offset_vision_dist = max(offset_vision_dist * 0.35, 5.0)    

  def prob(c):
    if abs(c.dRel - offset_vision_dist) > max_offset_vision_dist:
      return -1e6
    if not ((abs(c.vLead - lead.v[0]) < vel_tolerance) or (c.vLead > 3)):
      return -1e6
    prob_d = laplacian_pdf(c.dRel, offset_vision_dist, lead.xStd[0])
    prob_y = laplacian_pdf(c.yRel, -lead.y[0], lead.yStd[0])
    prob_v = laplacian_pdf(c.vLead, lead.v[0], lead.vStd[0])

    weight_v = np.interp(c.vLead, [0, 10], [0.3, 1])

    return prob_d * prob_y * prob_v * weight_v

  track = max(tracks.values(), key=prob, default=None)
  return track if track and prob(track) > -1e6 else None


def get_RadarState_from_vision(md, lead_msg: capnp._DynamicStructReader, v_ego: float, model_v_ego: float):
  lead_v_rel_pred = lead_msg.v[0] - model_v_ego
  dRel = float(lead_msg.x[0] - RADAR_TO_CAMERA)
  yRel = float(-lead_msg.y[0])
  dPath = yRel + np.interp(dRel, md.position.x, md.position.y)
  return {
    "dRel": float(dRel),
    "yRel": yRel,
    "dPath" : float(dPath),
    "vRel": float(lead_v_rel_pred),
    "vLead": float(v_ego + lead_v_rel_pred),
    "vLeadK": float(v_ego + lead_v_rel_pred),
    "aLead": float(lead_msg.a[0]),
    "aLeadK": float(lead_msg.a[0]),
    "aLeadTau": 0.3,
    "jLead": 0.0,
    "fcw": False,
    "modelProb": float(lead_msg.prob),
    "status": True,
    "radar": False,
    "radarTrackId": -1,
  }

def get_lead_side(v_ego, tracks, md, lane_width, model_v_ego):
  lead_msg = md.leadsV3[0]
  leadCenter = {'status': False}
  leadLeft = {'status': False}
  leadRight = {'status': False}

  ## SCC레이더는 일단 보관하고 리스트에서 삭제...
  track_scc = tracks.get(0)
  #if track_scc is not None:
  #  del tracks[0]

  #if len(tracks) == 0:
  #  return [[],[],[],leadLeft,leadRight]
  if md is not None and len(md.position.x) == 33: #ModelConstants.IDX_N:
    md_y = md.position.y
    md_x = md.position.x
  else:
    return [[],[],[],leadCenter,leadLeft,leadRight]

  leads_center = {}
  leads_left = {}
  leads_right = {}
  next_lane_y = lane_width / 2 + lane_width * 0.8
  for c in tracks.values():
    # d_y :  path_y - traks_y 의 diff값
    # yRel값은 왼쪽이 +값, lead.y[0]값은 왼쪽이 -값
    d_y = c.yRel + np.interp(c.dRel, md_x, md_y)
    if abs(d_y) < lane_width/2:
      ld = c.get_RadarState(md, lead_msg.prob, float(-lead_msg.y[0]))
      leads_center[c.dRel] = ld
    elif -next_lane_y < d_y < 0:
      ld = c.get_RadarState(md, 0, 0)
      leads_right[c.dRel] = ld
    elif 0 < d_y < next_lane_y:
      ld = c.get_RadarState(md, 0, 0)
      leads_left[c.dRel] = ld

  if lead_msg.prob > 0.5:
    ld = get_RadarState_from_vision(md, lead_msg, v_ego, model_v_ego)
    leads_center[ld['dRel']] = ld
  #ll,lr = [[l[k] for k in sorted(list(l.keys()))] for l in [leads_left,leads_right]]
  #lc = sorted(leads_center.values(), key=lambda c:c["dRel"])
  ll = list(leads_left.values())
  lr = list(leads_right.values())

  if leads_center:
    dRel_min = min(leads_center.keys())
    lc = [leads_center[dRel_min]]
  else:
    lc = {}

  leadLeft = min((lead for dRel, lead in leads_left.items() if lead['dRel'] > 5.0), key=lambda x: x['dRel'], default=leadLeft)
  leadRight = min((lead for dRel, lead in leads_right.items() if lead['dRel'] > 5.0), key=lambda x: x['dRel'], default=leadRight)
  leadCenter = min((lead for dRel, lead in leads_center.items() if lead['vLead'] > 10 / 3.6 and lead['radar']), key=lambda x: x['dRel'], default=leadCenter)

  #filtered_leads_left = {dRel: lead for dRel, lead in leads_left.items() if lead['dRel'] > 5.0}
  #if filtered_leads_left:
  #  dRel_min = min(filtered_leads_left.keys())
  #  leadLeft = filtered_leads_left[dRel_min]

  #filtered_leads_right = {dRel: lead for dRel, lead in leads_right.items() if lead['dRel'] > 5.0}
  #if filtered_leads_right:
  #  dRel_min = min(filtered_leads_right.keys())
  #  leadRight = filtered_leads_right[dRel_min]

  return [ll, lc, lr, leadCenter, leadLeft, leadRight]

def get_lead(v_ego: float, ready: bool, tracks: dict[int, Track], lead_msg: capnp._DynamicStructReader,
             model_v_ego: float, low_speed_override: bool = True) -> dict[str, Any]:
  # Determine leads, this is where the essential logic happens
  if len(tracks) > 0 and ready and lead_msg.prob > .5:
    track = match_vision_to_track(v_ego, lead_msg, tracks)
  else:
    track = None

  lead_dict = {'status': False}
  if track is not None:
    lead_dict = track.get_RadarState(lead_msg.prob)
  elif (track is None) and ready and (lead_msg.prob > .5):
    lead_dict = get_RadarState_from_vision(lead_msg, v_ego, model_v_ego)

  if low_speed_override:
    low_speed_tracks = [c for c in tracks.values() if c.potential_low_speed_lead(v_ego)]
    if len(low_speed_tracks) > 0:
      closest_track = min(low_speed_tracks, key=lambda c: c.dRel)

      # Only choose new track if it is actually closer than the previous one
      if (not lead_dict['status']) or (closest_track.dRel < lead_dict['dRel']):
        lead_dict = closest_track.get_RadarState()

  return lead_dict


class VisionTrack:
  def __init__(self, radar_ts):
    self.radar_ts = radar_ts
    self.dRel = 0.0
    self.vRel = 0.0
    self.yRel = 0.0
    self.vLead = 0.0
    self.aLead = 0.0
    self.vLeadK = 0.0
    self.aLeadK = 0.0
    self.aLeadTau = _LEAD_ACCEL_TAU
    self.prob = 0.0
    self.status = False

    self.dRel_last = 0.0
    self.vLead_last = 0.0
    self.alpha = 0.02
    self.alpha_a = 0.02

    self.vLat = 0.0

    self.v_ego = 0.0
    self.cnt = 0

    self.dPath = 0.0

  def get_lead(self, md):
    #aLeadK = 0.0 if self.mixRadarInfo in [3] else clip(self.aLeadK, self.aLead - 1.0, self.aLead + 1.0)
    return {
      "dRel": self.dRel,
      "yRel": self.yRel,
      #"dPath": self.dPath,
      "vRel": self.vRel,
      "vLead": self.vLead,
      "vLeadK": self.vLeadK,    ## TODO: 아직 vLeadK는 엉망인듯...
      "aLead": self.aLead,
      "aLeadK": self.aLeadK,
      "aLeadTau": self.aLeadTau,
      "jLead": 0.0,
      "fcw": False,
      "modelProb": self.prob,
      "status": self.status,
      "radar": False,
      "radarTrackId": -1,
      #"aLead": self.aLead,
      #"vLat": self.vLat,
    }

  def reset(self):
    self.status = False
    self.aLeadTau = _LEAD_ACCEL_TAU

    self.vRel = 0.0
    self.vLead = self.vLeadK = self.v_ego
    self.aLead = self.aLeadK = 0.0
    self.vLat = 0.0

  def update(self, lead_msg, model_v_ego, v_ego, md):

    lead_v_rel_pred = lead_msg.v[0] - model_v_ego
    self.prob = lead_msg.prob
    self.v_ego = v_ego
    if self.prob > .5:
      dRel = float(lead_msg.x[0]) - RADAR_TO_CAMERA
      if abs(self.dRel - dRel) > 5.0:
        self.cnt = 0
      self.dRel = dRel

      self.yRel = float(-lead_msg.y[0])
      dPath = self.yRel + np.interp(self.dRel, md.position.x, md.position.y)
      a_lead_vision = lead_msg.a[0]
      if self.cnt < 20 or self.prob < 0.97: # 레이더측정시 cnt는 0, 레이더사라지고 1초간 비젼데이터 그대로 사용
        self.vRel = lead_v_rel_pred
        self.vLead = float(v_ego + lead_v_rel_pred)
        self.aLead = a_lead_vision
        self.vLat = 0.0
      else:
        v_rel = (self.dRel - self.dRel_last) / self.radar_ts
        v_rel = self.vRel * (1. - self.alpha) + v_rel * self.alpha

        #self.vRel = lead_v_rel_pred if self.mixRadarInfo == 3 else (lead_v_rel_pred + self.vRel) / 2
        model_weight = np.interp(self.prob, [0.97, 1.0], [0.4, 0.0])  # prob가 높으면 v_rel(dRel미분값)에 가중치를 줌.
        self.vRel = float(lead_v_rel_pred * model_weight + v_rel * (1. - model_weight))
        #self.vRel = (lead_v_rel_pred + v_rel) / 2
        self.vLead = float(v_ego + self.vRel)

        a_lead = (self.vLead - self.vLead_last) / self.radar_ts * 0.2 #0.5 -> 0.2 vel 미분적용을 줄임.
        self.aLead = self.aLead * (1. - self.alpha_a) + a_lead * self.alpha_a
        if abs(a_lead_vision) > abs(self.aLead): # or self.mixRadarInfo == 3:
          self.aLead = a_lead_vision

        vLat_alpha = 0.002
        self.vLat = self.vLat * (1. - vLat_alpha) + (dPath - self.dPath) / self.radar_ts * vLat_alpha

      self.dPath = dPath

      self.vLeadK= self.vLead
      self.aLeadK = self.aLead

      self.status = True
      self.cnt += 1
    else:
      self.reset()
      self.cnt = 0
      self.dPath = self.yRel + np.interp(v_ego ** 2 / (2 * 2.5), md.position.x, md.position.y)

    self.dRel_last = self.dRel
    self.vLead_last = self.vLead

    # Learn if constant acceleration
    #aLeadTauValue = self.aLeadTauPos if self.aLead > self.aLeadTauThreshold else self.aLeadTauNeg
    if abs(self.aLead) < 0.3: #self.aLeadTauThreshold:
      self.aLeadTau = 0.2 #aLeadTauValue
    else:
      #self.aLeadTau = min(self.aLeadTau * 0.9, aLeadTauValue)
      self.aLeadTau *= 0.9

class RadarD:
  def __init__(self, delay: float = 0.0):
    self.current_time = 0.0

    self.tracks: dict[int, Track] = {}

    self.v_ego = 0.0
    print("###RadarD.. : delay = ", delay, int(round(delay / DT_MDL))+1)
    self.v_ego_hist = deque([0.0], maxlen=int(round(delay / DT_MDL))+1)
    self.last_v_ego_frame = -1

    self.radar_state: capnp._DynamicStructBuilder | None = None
    self.radar_state_valid = False

    self.ready = False

    self.vision_tracks = [VisionTrack(DT_MDL), VisionTrack(DT_MDL)]

    self.params = Params()
    self.enable_radar_tracks = self.params.get_int("EnableRadarTracks")
    self.enable_corner_radar = self.params.get_int("EnableCornerRadar")

    self.radar_detected = False


  def update(self, sm: messaging.SubMaster, rr: car.RadarData):
    self.ready = sm.seen['modelV2']
    self.current_time = 1e-9*max(sm.logMonoTime.values())

    self.enable_radar_tracks = self.params.get_int("EnableRadarTracks")
    self.enable_corner_radar = self.params.get_int("EnableCornerRadar")


    leads_v3 = sm['modelV2'].leadsV3
    if sm.recv_frame['carState'] != self.last_v_ego_frame:
      self.v_ego = sm['carState'].vEgo
      self.v_ego_hist.append(self.v_ego)
      self.last_v_ego_frame = sm.recv_frame['carState']

    ar_pts = {}
    for pt in rr.points:
      pt_yRel = pt.yRel
      if pt.trackId == 0 and pt.yRel == 0: # scc radar for HKG
        if self.ready and leads_v3[0].prob > 0.5:
          pt_yRel = -leads_v3[0].y[0]
      ar_pts[pt.trackId] = [pt.dRel, pt_yRel, pt.vRel, pt.measured, pt.vLead, pt.aLead, pt.jLead]

    # *** remove missing points from meta data ***
    for ids in list(self.tracks.keys()):
      if ids not in ar_pts:
        self.tracks.pop(ids, None)

    # *** compute the tracks ***
    for ids in ar_pts:
      rpt = ar_pts[ids]

      # align v_ego by a fixed time to align it with the radar measurement
      #v_lead = rpt[2] + self.v_ego_hist[0]
      v_lead = rpt[4] # carrot
      a_lead = rpt[5]
      j_lead = rpt[6]

      # create the track if it doesn't exist or it's a new track
      if ids not in self.tracks:
        self.tracks[ids] = Track(ids)
      self.tracks[ids].update(rpt[0], rpt[1], rpt[2], v_lead, a_lead, j_lead, rpt[3])

    # *** publish radarState ***
    self.radar_state_valid = sm.all_checks()
    self.radar_state = log.RadarState.new_message()

    model_updated = False if self.radar_state.mdMonoTime == sm.logMonoTime['modelV2'] else True

    self.radar_state.mdMonoTime = sm.logMonoTime['modelV2']
    self.radar_state.radarErrors = rr.errors
    self.radar_state.carStateMonoTime = sm.logMonoTime['carState']

    if len(sm['modelV2'].velocity.x):
      model_v_ego = sm['modelV2'].velocity.x[0]
    else:
      model_v_ego = self.v_ego
    #leads_v3 = sm['modelV2'].leadsV3
    if len(leads_v3) > 1:

      if model_updated:
        if self.radar_detected:
          self.vision_tracks[0].cnt = 0
          self.vision_tracks[1].cnt = 0
        self.vision_tracks[0].update(leads_v3[0], model_v_ego, self.v_ego, sm['modelV2'])
        self.vision_tracks[1].update(leads_v3[1], model_v_ego, self.v_ego, sm['modelV2'])

      #self.radar_state.leadOne = get_lead(self.v_ego, self.ready, self.tracks, leads_v3[0], model_v_ego, low_speed_override=False)
      #self.radar_state.leadTwo = get_lead(self.v_ego, self.ready, self.tracks, leads_v3[1], model_v_ego, low_speed_override=False)
      self.radar_state.leadOne, self.radar_detected = self.get_lead(sm['carState'], sm['modelV2'], self.tracks, 0, leads_v3[0], model_v_ego, low_speed_override=False)
      self.radar_state.leadTwo, _ = self.get_lead(sm['carState'], sm['modelV2'], self.tracks, 1, leads_v3[1], model_v_ego, low_speed_override=False)

      # ll, lc, lr, leadCenter, self.radar_state.leadLeft, self.radar_state.leadRight = get_lead_side(self.v_ego, self.tracks, sm['modelV2'],
      #                                                                                               sm['lateralPlan'].laneWidth, model_v_ego)
      ll, lc, lr, leadCenter, self.radar_state.leadLeft, self.radar_state.leadRight = get_lead_side(self.v_ego, self.tracks, sm['modelV2'], 3.2, model_v_ego)
      self.radar_state.leadsLeft = list(ll)
      self.radar_state.leadsCenter = list(lc)
      self.radar_state.leadsRight = list(lr)


  def publish(self, pm: messaging.PubMaster):
    assert self.radar_state is not None

    radar_msg = messaging.new_message("radarState")
    radar_msg.valid = self.radar_state_valid
    radar_msg.radarState = self.radar_state
    pm.send("radarState", radar_msg)

  def get_lead(self, CS, md, tracks: dict[int, Track], index: int, lead_msg: capnp._DynamicStructReader,
               model_v_ego: float, low_speed_override: bool = True) -> dict[str, Any]:

    v_ego = self.v_ego
    ready = self.ready
    ## SCC레이더는 일단 보관하고 리스트에서 삭제... (SCC Track은 0,1번으로 들어옴)
    track_scc = tracks.get(0)
    if track_scc is None:
      track_scc = tracks.get(1)
    #if track_scc is not None:
    #  del tracks[0]            ## tracks에서 삭제하면안됨... ㅠㅠ

    # Determine leads, this is where the essential logic happens
    if len(tracks) > 0 and ready and lead_msg.prob > .5:
      track = match_vision_to_track(v_ego, lead_msg, tracks)
    else:
      track = None

    # vision match후 발견된 track이 없으면
    #  track_scc 가 있는 지 확인하고
    #    비전과의 차이가 35%(5M)이상 차이나면 scc가 발견못한것이기 때문에 비전것으로 처리함.

    ### 240807, SCC레이더가 옆차선의것을 많이 가져옴... 사용하지 말아야겠다...
    # 250415: scc radar정보가 있지만.. vision 미검출시, 오류
    if self.enable_radar_tracks in [-1, 2]:  
      if track_scc is not None and track is None:
        track = track_scc
    #  if self.vision_tracks[index].prob > .5:
    #    if self.vision_tracks[index].dRel < track.dRel - 10.0: #끼어드는 차량이 있는 경우 처리..  5-> 10M바꿔보자... 240427
    #      track = None

    lead_dict = {'status': False}
    radar = False
    if track is not None:
      #lead_dict = track.get_RadarState(md, lead_msg.prob, self.vision_tracks[0].yRel, self.vision_tracks[0].vLat)
      lead_dict = track.get_RadarState(md, lead_msg.prob, self.vision_tracks[0].yRel)
      radar = True
    elif (track is None) and ready and (lead_msg.prob > .8):
      #if self.mixRadarInfo == 4 and v_ego * 3.6 > 30 and lead_msg.prob < 0.99: ##
      #  pass
      #else:
        lead_dict = self.vision_tracks[index].get_lead(md)

    if self.enable_corner_radar > 0:
      lead_dict = self.corner_radar(CS, lead_dict)

    if low_speed_override:
      low_speed_tracks = [c for c in tracks.values() if c.potential_low_speed_lead(v_ego)]
      if len(low_speed_tracks) > 0:
        closest_track = min(low_speed_tracks, key=lambda c: c.dRel)

        # Only choose new track if it is actually closer than the previous one
        if (not lead_dict['status']) or (closest_track.dRel < lead_dict['dRel']):
          #lead_dict = closest_track.get_RadarState(md, lead_msg.prob, self.vision_tracks[0].yRel, self.vision_tracks[0].vLat)
          lead_dict = closest_track.get_RadarState(md, lead_msg.prob, self.vision_tracks[0].yRel)

    return lead_dict, radar
  
  def corner_radar(self, CS, lead_dict):
    lat_dist = 1e6
    long_dist = 1e6
    if 0 < CS.leftLatDist < 2.5:
      lat_dist = CS.leftLatDist
      long_dist = CS.leftLongDist
    if 0 < CS.rightLatDist < 2.5 and CS.rightLongDist < long_dist:
      lat_dist = CS.rightLatDist
      long_dist = CS.rightLongDist

    if lat_dist == 0.0 or lat_dist >= 2.5 or long_dist == 1e6:
      return lead_dict
    
    if lead_dict['status']:
      if lead_dict['dRel'] > long_dist:
        lead_dict['dRel'] = long_dist
        lead_dict['yRel'] = lat_dist
        lead_dict['vRel'] = 0.0
        lead_dict['vLead'] = CS.vEgo if CS.vEgo < lead_dict['vLead'] else lead_dict['vLead']
        lead_dict['vLeadK'] = lead_dict['vLead']
        lead_dict['aLead'] = CS.aEgo if CS.aEgo < lead_dict['aLead'] else lead_dict['aLead']
        lead_dict['aLeadK'] = lead_dict['aLead']
        lead_dict['aLeadTau'] = _LEAD_ACCEL_TAU
        lead_dict['jLead'] = 0.0
        lead_dict['modelProb'] = 1.0
        lead_dict['radarTrackId'] = -1
        lead_dict['radar'] = True
    else:
      lead_dict['status'] = True
      lead_dict['dRel'] = long_dist
      lead_dict['yRel'] = lat_dist
      lead_dict['vRel'] = 0.0
      lead_dict['vLead'] = CS.vEgo
      lead_dict['vLeadK'] = CS.vEgo
      lead_dict['aLead'] = CS.aEgo
      lead_dict['aLeadK'] = CS.aEgo
      lead_dict['aLeadTau'] = _LEAD_ACCEL_TAU
      lead_dict['jLead'] = 0.0
      lead_dict['modelProb'] = 1.0
      lead_dict['radarTrackId'] = -1
      lead_dict['radar'] = True

    return lead_dict

# fuses camera and radar data for best lead detection
def main() -> None:
  config_realtime_process(5, Priority.CTRL_LOW)

  # wait for stats about the car to come in from controls
  cloudlog.info("radard is waiting for CarParams")
  CP = messaging.log_from_bytes(Params().get("CarParams", block=True), car.CarParams)
  cloudlog.info("radard got CarParams")

  # *** setup messaging
  sm = messaging.SubMaster(['modelV2', 'carState', 'liveTracks'], poll='modelV2')
  #sm = messaging.SubMaster(['modelV2', 'carState', 'liveTracks'], poll='liveTracks')
  pm = messaging.PubMaster(['radarState'])

  RD = RadarD(CP.radarDelay)

  while 1:
    sm.update()

    RD.update(sm, sm['liveTracks'])
    RD.publish(pm)


if __name__ == "__main__":
  main()
