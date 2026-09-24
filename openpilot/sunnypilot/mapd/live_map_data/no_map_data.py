"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from openpilot.sunnypilot.mapd.live_map_data.base_map_data import BaseMapData


class NoMapData(BaseMapData):
  """A map-data provider that supplies nothing.

  Used when the user has turned off both online (Amap) and offline (OSM) map data. It
  exists so that "no provider" is an explicit, well-defined state rather than a special
  case threaded through the manager: the rest of the pipeline keeps receiving
  liveMapDataSP, with every "valid" flag false, which is exactly the same thing it sees
  on a road where the provider simply has no data.

  This matters because consumers key off the validity flags, not off the provider type.
  The speed-limit resolver already requires `speedLimitValid`, and the map controller
  requires `curveSpeedValid`, so a provider that reports nothing is inert without any
  consumer needing to know about it.
  """

  def update_location(self) -> None:
    pass

  def get_current_speed_limit(self) -> float:
    return 0.

  def get_next_speed_limit_and_distance(self) -> tuple[float, float]:
    return 0., 0.

  def get_current_road_name(self) -> str:
    return ""
