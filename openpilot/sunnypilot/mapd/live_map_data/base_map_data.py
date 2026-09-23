"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from abc import abstractmethod, ABC

import openpilot.cereal.messaging as messaging
from openpilot.common.params import Params
from openpilot.common.constants import CV
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.car.cruise import V_CRUISE_UNSET
from openpilot.sunnypilot.navd.helpers import coordinate_from_param

MAX_SPEED_LIMIT = V_CRUISE_UNSET * CV.KPH_TO_MS


class BaseMapData(ABC):
  def __init__(self):
    self.params = Params()

    self.sm = messaging.SubMaster(['liveLocationKalman'])
    self.pm = messaging.PubMaster(['liveMapDataSP'])

    self.localizer_valid = False
    self.last_bearing = None
    self.last_position = coordinate_from_param("LastGPSPositionLLK", self.params)

  @abstractmethod
  def update_location(self) -> None:
    pass

  @abstractmethod
  def get_current_speed_limit(self) -> float:
    pass

  @abstractmethod
  def get_next_speed_limit_and_distance(self) -> tuple[float, float]:
    pass

  @abstractmethod
  def get_current_road_name(self) -> str:
    pass

  def publish(self) -> None:
    speed_limit = self.get_current_speed_limit()
    next_speed_limit, next_speed_limit_distance = self.get_next_speed_limit_and_distance()

    mapd_sp_send = messaging.new_message('liveMapDataSP')
    mapd_sp_send.valid = self.sm['liveLocationKalman'].gpsOK
    live_map_data = mapd_sp_send.liveMapDataSP

    live_map_data.speedLimitValid = bool(MAX_SPEED_LIMIT > speed_limit > 0)
    live_map_data.speedLimit = speed_limit
    live_map_data.speedLimitAheadValid = bool(MAX_SPEED_LIMIT > next_speed_limit > 0)
    live_map_data.speedLimitAhead = next_speed_limit
    live_map_data.speedLimitAheadDistance = next_speed_limit_distance
    live_map_data.roadName = self.get_current_road_name()

    # Curve speed is an optional provider capability - the offline OSM provider has
    # no route geometry and does not implement it - so probe rather than declaring it
    # abstract. A provider that lacks it publishes "no constraint", which is the same
    # thing it would publish on a straight road. `valid` is the flag consumers read;
    # a zero speed with valid=False must never be treated as a stop.
    curve_speed, curve_distance = 0.0, 0.0
    get_curve = getattr(self, "get_curve_speed_and_distance", None)
    if get_curve is not None:
      try:
        curve_speed, curve_distance = get_curve()
      except Exception as e:
        cloudlog.warning(f"map_data: failed to read curve speed: {e}")
        curve_speed, curve_distance = 0.0, 0.0
    live_map_data.curveSpeedValid = bool(MAX_SPEED_LIMIT > curve_speed > 0 and curve_distance > 0)
    live_map_data.curveSpeed = curve_speed
    live_map_data.curveSpeedDistance = curve_distance

    self.pm.send('liveMapDataSP', mapd_sp_send)

  def tick(self) -> None:
    self.sm.update(0)
    self.update_location()
    self.publish()
