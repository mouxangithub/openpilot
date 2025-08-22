"""
Copyright (c) 2025, Rick Lan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, and/or sublicense, 
for non-commercial purposes only, subject to the following conditions:

- The above copyright notice and this permission notice shall be included in 
  all copies or substantial portions of the Software.
- Commercial use (e.g. use in a product, service, or activity intended to 
  generate revenue) is prohibited without explicit written permission from 
  the copyright holder.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

from opendbc.car.interfaces import RadarInterfaceBase
from opendbc.can.parser import CANParser
from opendbc.car.structs import RadarData
from typing import List, Tuple

# car head to radar
DREL_OFFSET = -1.35

# max object amount will process
MAX_OBJECTS = 100

# lat distance, typically max lane width is 3.7m
MAX_LAT_DIST = 3.6

# objects to ignore thats really close to the vehicle (after DREL_OFFSET applied)
MIN_DIST = 2.5

# when a object has really large negative v_rel means its stationary / standstill
# so with the values below (v_rel = -10, lat_dist = 2.), we are trying to ignore:
# when the ego vehicle is driving above 36 km/h (22.37 mph), we will ignore objects that lateral distance is above 2m on left or right.
STATIONARY_OBJ_VREL = -10.
STATIONARY_OBJ_LAT_DIST = 2.

# when we detect an object that's really closed to the ego vehicle
# we ignore the objects that's away from left or right
CLOSED_OBJ_DREL = 10
CLOSED_OBJ_YREL = 2.

# ignore objects that has small radar cross sections (-64 ~ 63.5)
MIN_RCS = -5.

# ignore oncoming objects
IGNORE_OBJ_STATE = 2

# ignore objects that we haven't seen for 5 secs
NOT_SEEN_INIT = 33*5

def _create_radar_parser():
  messages = [("Status", 0), ("ObjectData", 0)]
  messages += [(f"ObjectData_{i}", 0) for i in range(MAX_OBJECTS)]
  return CANParser('u_radar', messages, 1)

class RadarInterface(RadarInterfaceBase):
  def __init__(self, CP):
    super().__init__(CP)

    self.updated_messages = set()

    self.rcp = _create_radar_parser()

    self._pts_cache = dict()
    self._pts_not_seen = {key: 0 for key in range(255)}
    self._should_clear_cache = False

  def _create_parsable_object_can_strings(self, can_strings: List[Tuple]) -> Tuple[List[Tuple], int]:
    """Optimized object string parsing with minimal allocations."""
    if not can_strings or not isinstance(can_strings[0], tuple) or len(can_strings[0]) < 2:
      return [], 0

    # Pre-allocate list with known maximum size
    new_list = []
    new_list_append = new_list.append  # Local reference for faster access

    records = can_strings[0][1]
    id_num = 1

    for record in records:
      if id_num > MAX_OBJECTS:
        break

      if record[0] == 0x60B:
        new_list_append((id_num + 383, record[1], record[2]))
        id_num += 1

    return [(can_strings[0][0], new_list)], len(new_list)

  # called by card.py, 100hz
  def update(self, can_strings):
    vls = self.rcp.update_strings(can_strings)
    self.updated_messages.update(vls)

    if 1546 in self.updated_messages:
      self._should_clear_cache = True

    if 1547 in self.updated_messages:
      parsable_can_string, size = self._create_parsable_object_can_strings(can_strings)
      self.rcp.update_strings(parsable_can_string)

      # clean cache when we see a 0x60a then a 0x60b
      if self._should_clear_cache:
        self._pts_cache.clear()
        self._should_clear_cache = False

      for i in range(size):
        cpt = self.rcp.vl[f'ObjectData_{i}']
        track_id = cpt['ID']

        d_rel = float(cpt['DistLong']) + DREL_OFFSET
        y_rel = -float(cpt['DistLat'])

        # ignore oncoming objects
        if int(cpt['DynProp']) == IGNORE_OBJ_STATE:
          continue

        # only apply filters below when object is a point (0) not a vehicle (1)
        if int(cpt['Class']) == 0:
          # ignore really closed objects
          if d_rel < MIN_DIST:
            continue

          # ignore objects with really small radar cross sections
          if float(cpt['RCS']) < MIN_RCS:
            continue

          # ignore far left/right objects
          if abs(y_rel) > MAX_LAT_DIST:
            continue

          # ignore closed left/right objects when closed
          if d_rel < CLOSED_OBJ_DREL and abs(y_rel) > CLOSED_OBJ_YREL:
            continue

        # add to cache
        if track_id not in self._pts_cache:
          self._pts_cache[track_id] = RadarData.RadarPoint()
          self._pts_cache[track_id].trackId = track_id

        self._pts_not_seen[track_id] = NOT_SEEN_INIT
        self._pts_cache[track_id].yvRel = float(cpt['VRelLat'])
        self._pts_cache[track_id].dRel = d_rel
        self._pts_cache[track_id].yRel = y_rel
        self._pts_cache[track_id].vRel = float(cpt['VRelLong'])
        self._pts_cache[track_id].aRel = float('nan')
        self._pts_cache[track_id].measured = True

    self.updated_messages.clear()

    if self.frame % 3 == 0:
      keys_to_remove = [key for key in self.pts if key not in self._pts_cache]
      for key in keys_to_remove:
        self._pts_not_seen[key] -= 1
        if self._pts_not_seen[key] <= 0:
          del self.pts[key]

      self.pts.update(self._pts_cache)

      ret = RadarData()
      if not self.rcp.can_valid:
        ret.errors.canError = True

      ret.points = list(self.pts.values())
      return ret

    return None
