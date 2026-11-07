import math

from opendbc.can import CANParser
from opendbc.car import Bus, structs
from openpilot.common.params import Params
from opendbc.car.interfaces import RadarInterfaceBase
from opendbc.car.hyundai.values import DBC, HyundaiFlags, HyundaiExtFlags

from opendbc.sunnypilot.car.hyundai.radar_interface_ext import RadarInterfaceExt
from opendbc.car.hyundai.hyundaicanfd import CanBus
from opendbc.car.hyundai.radar_group3 import Group3Object, Group3TrackIds

RADAR_START_ADDR = 0x500
RADAR_MSG_COUNT = 32
RADAR_REQUIRED_MSG_COUNT = 32
RADAR_MSG_COUNT4 = 8

# CAN-FD radar groups. Which one a car broadcasts is detected at fingerprint time
# (HyundaiExtFlags) because it varies by platform and ECU part number.
RADAR_START_ADDR_CANFD1 = 0x210  # group 1, two objects per message
RADAR_MSG_COUNT1 = 16
RADAR_START_ADDR_CANFD2 = 0x3A5  # group 2, one object per message
RADAR_MSG_COUNT2 = 32
RADAR_START_ADDR_CANFD3 = 0x400  # group 3, one object per message
RADAR_MSG_COUNT3 = 30
RADAR_GROUP3_DBC = "hyundai_canfd_radar_generated"

# Corner radar objects. 0x235 is a status message plus twenty single-object payloads;
# 0x180 carries two slots per message across five messages. Which of them a car has is
# detected at fingerprint time.
CORNER_OBJECT_235_START_ADDR = 0x235
CORNER_OBJECT_235_MSG_COUNT = 20
CORNER_OBJECT_235_TRACK_ID_OFFSET = 200
CORNER_OBJECT_235_DBC = "hyundai_canfd_corner_radar_235_generated"
CORNER_OBJECT_180_START_ADDR = 0x180
CORNER_OBJECT_180_MSG_COUNT = 5
CORNER_OBJECT_180_SLOTS_PER_MSG = 2
CORNER_OBJECT_180_TRACK_ID_OFFSET = 240
CORNER_OBJECT_180_DBC = "hyundai_canfd_corner_radar_180_generated"

# Object identity. Corner-radar IDs are not globally unique - two distant objects can
# carry the same ID in the same cycle - so identity is resolved from ID *plus* physical
# continuity, and a slot handoff is only merged when the copies are close together.
CORNER_OBJECT_STABLE_TRACK_ID_START = 1000
CORNER_OBJECT_IDENTITY_STALE_CYCLES = 3
CORNER_OBJECT_IDENTITY_MAX_DREL_DELTA = 7.0
CORNER_OBJECT_IDENTITY_MAX_YREL_DELTA = 3.2
CORNER_OBJECT_HANDOFF_MAX_DREL_DELTA = 2.0
CORNER_OBJECT_HANDOFF_MAX_YREL_DELTA = 1.0
CORNER_OBJECT_HANDOFF_MAX_VREL_DELTA = 3.0
CORNER_SIDE_OBJECT_MAX_DREL = 0.2
CORNER_SIDE_OBJECT_MIN_ABS_YREL = 1.4
CORNER_SIDE_OBJECT_MAX_ABS_YREL = 4.5

# POC for parsing corner radars: https://github.com/commaai/openpilot/pull/24221/


def get_corner_object_can_parser(CP, enabled):
  """Parser for the 0x235 corner object payloads (one object per message)."""
  if not enabled or not (CP.flags & HyundaiFlags.CANFD):
    return None
  CAN = CanBus(CP)
  messages = [(f"CORNER_RADAR_235_OBJECTS_{a:x}", 33)
              for a in range(CORNER_OBJECT_235_START_ADDR, CORNER_OBJECT_235_START_ADDR + CORNER_OBJECT_235_MSG_COUNT)]
  return CANParser(CORNER_OBJECT_235_DBC, messages, CAN.ACAN)


def get_corner_object_180_can_parser(CP, enabled):
  """Parser for the 0x180 corner object payloads (two slots per message)."""
  if not enabled or not (CP.flags & HyundaiFlags.CANFD):
    return None
  CAN = CanBus(CP)
  messages = [(f"CORNER_RADAR_180_OBJECTS_{a:x}", 33)
              for a in range(CORNER_OBJECT_180_START_ADDR, CORNER_OBJECT_180_START_ADDR + CORNER_OBJECT_180_MSG_COUNT)]
  return CANParser(CORNER_OBJECT_180_DBC, messages, CAN.ACAN)


def get_radar_can_parser(CP, radar_tracks, msg_start_addr, msg_count, required_msg_count):
  """CAN parser for the radar track messages.

  CAN-FD cars read the grouped DBC (``hyundai_canfd_radar_generated``), which carries the
  group-1/2/3 layouts; the Mando path reads the car's own radar DBC. Ported from cp.
  """
  if not radar_tracks:
    return None

  if CP.flags & HyundaiFlags.CANFD:
    CAN = CanBus(CP)
    messages = [(f"RADAR_TRACK_{addr:x}", 20) for addr in range(msg_start_addr, msg_start_addr + msg_count)]
    return CANParser(RADAR_GROUP3_DBC, messages, CAN.ACAN)

  # Legacy Mando radars expose either 32 or 64 consecutive slots. Keep the first 32
  # mandatory for timing/CAN validity and accept the upper bank when present, so a
  # 32-slot radar stays compatible.
  if Bus.radar not in DBC[CP.carFingerprint]:
    return None
  messages = [(f"RADAR_TRACK_{addr:x}", 20 if index < required_msg_count else math.nan)
              for index, addr in enumerate(range(msg_start_addr, msg_start_addr + msg_count))]
  return CANParser(DBC[CP.carFingerprint][Bus.radar], messages, 1)


class CornerObjectTrackIdManager:
  """Resolve a stable track ID per corner-radar object.

  The corner radar sends objects in CAN slots, and an object moves between slots. The
  native object ID cannot be used as the identity on its own because it is not globally
  unique, so a match requires the same ID *and* a physically continuous position, with
  the previous slot preferred over a handoff. Ported from cp.
  """

  def __init__(self):
    self.next_track_id = CORNER_OBJECT_STABLE_TRACK_ID_START
    self.source_cycles: dict[str, int] = {}
    self.track_states: dict[tuple[str, int], tuple[int, int, int, float, float, int]] = {}

  def clear_source(self, source: str):
    self.track_states = {k: v for k, v in self.track_states.items() if k[0] != source}
    self.source_cycles.pop(source, None)

  def get_track_ids(self, source: str, candidates) -> dict[int, int]:
    cycle = self.source_cycles.get(source, 0) + 1
    self.source_cycles[source] = cycle
    previous = {
      track_id: state for (state_source, track_id), state in self.track_states.items()
      if state_source == source and cycle - state[5] <= CORNER_OBJECT_IDENTITY_STALE_CYCLES
    }
    used_track_ids: set[int] = set()
    assignments: dict[int, int] = {}

    for candidate in candidates:
      slot_id, object_id, age, _, d_rel, y_rel, *_ = candidate
      matches = []
      for track_id, state in previous.items():
        prev_slot, prev_object_id, prev_age, prev_d_rel, prev_y_rel, _ = state
        if track_id in used_track_ids or object_id != prev_object_id or age < prev_age:
          continue
        d_delta = abs(d_rel - prev_d_rel)
        y_delta = abs(y_rel - prev_y_rel)
        if (d_delta > CORNER_OBJECT_IDENTITY_MAX_DREL_DELTA
            or y_delta > CORNER_OBJECT_IDENTITY_MAX_YREL_DELTA):
          continue
        matches.append((prev_slot != slot_id, d_delta + y_delta * 1.5, track_id))

      if matches:
        track_id = min(matches)[2]
      else:
        track_id = self.next_track_id
        self.next_track_id += 1
      assignments[slot_id] = track_id
      used_track_ids.add(track_id)
      self.track_states[(source, track_id)] = (slot_id, object_id, age, d_rel, y_rel, cycle)

    self.track_states = {
      k: v for k, v in self.track_states.items()
      if k[0] != source or cycle - v[5] <= CORNER_OBJECT_IDENTITY_STALE_CYCLES
    }
    return assignments


def deduplicate_corner_candidates(candidates):
  """Merge physically close copies of the same object from a slot handoff.

  Only close copies are merged: one object ID can legitimately be on two distant objects
  at once, so ID alone would collapse unrelated targets.
  """
  objects = []
  for candidate in candidates:
    _, object_id, age, quality, d_rel, y_rel, v_rel, *_ = candidate
    duplicate_index = None
    for index, previous in enumerate(objects):
      if object_id != previous[1]:
        continue
      if (abs(d_rel - previous[4]) <= CORNER_OBJECT_HANDOFF_MAX_DREL_DELTA
          and abs(y_rel - previous[5]) <= CORNER_OBJECT_HANDOFF_MAX_YREL_DELTA
          and abs(v_rel - previous[6]) <= CORNER_OBJECT_HANDOFF_MAX_VREL_DELTA):
        duplicate_index = index
        break
    if duplicate_index is None:
      objects.append(candidate)
    elif (age, quality) > (objects[duplicate_index][2], objects[duplicate_index][3]):
      objects[duplicate_index] = candidate
  return objects


def corner_object_position_valid(d_rel: float, y_rel: float) -> bool:
  """Corners clip side objects to x=0, so the normal range test alone would drop them."""
  normal_object = 0.2 < d_rel < 180.0
  clipped_side_object = (
    0.0 <= d_rel <= CORNER_SIDE_OBJECT_MAX_DREL
    and CORNER_SIDE_OBJECT_MIN_ABS_YREL <= abs(y_rel) <= CORNER_SIDE_OBJECT_MAX_ABS_YREL
  )
  return (normal_object or clipped_side_object) and abs(y_rel) < 40.0


class RadarInterface(RadarInterfaceBase, RadarInterfaceExt):
  def __init__(self, CP, CP_SP):
    RadarInterfaceBase.__init__(self, CP, CP_SP)
    RadarInterfaceExt.__init__(self, CP, CP_SP)
    self.updated_messages = set()

    self.canfd = bool(CP.flags & HyundaiFlags.CANFD)
    self.radar_group1 = False
    self.radar_group3 = False
    self.radar_group4 = not self.canfd and bool(CP.extFlags & HyundaiExtFlags.RADAR_GROUP4.value)

    # Which CAN-FD radar group this car broadcasts. Detected at fingerprint time because
    # it varies by platform and ECU part number; the decoding differs per group, so this
    # has to be settled before any parser is built. Legacy CAN always uses the Mando
    # layout. Ported from cp.
    if self.canfd:
      if CP.extFlags & HyundaiExtFlags.RADAR_GROUP1.value:
        self.radar_start_addr = RADAR_START_ADDR_CANFD1
        self.radar_msg_count = RADAR_MSG_COUNT1
        self.radar_group1 = True
      elif CP.extFlags & HyundaiExtFlags.RADAR_GROUP3.value:
        self.radar_start_addr = RADAR_START_ADDR_CANFD3
        self.radar_msg_count = RADAR_MSG_COUNT3
        self.radar_group3 = True
      else:
        # Group 2 is the default: it is what a CAN-FD car with no recognised group
        # broadcasts, and decoding it the Mando way is the previous behaviour.
        self.radar_start_addr = RADAR_START_ADDR_CANFD2
        self.radar_msg_count = RADAR_MSG_COUNT2
    else:
      self.radar_start_addr = RADAR_START_ADDR
      self.radar_msg_count = RADAR_MSG_COUNT4 if self.radar_group4 else RADAR_MSG_COUNT

    self.radar_required_msg_count = self.radar_msg_count
    if not self.canfd and not self.radar_group4:
      self.radar_required_msg_count = RADAR_REQUIRED_MSG_COUNT

    self.trigger_msg = self.radar_start_addr + self.radar_required_msg_count - 1

    self.radar_off_can = CP.radarUnavailable
    # EnableRadarTracks gates whether raw tracks are decoded at all. Read through Params
    # rather than CP so it can be toggled without a re-fingerprint; >= 1 matches cp.
    self.radar_tracks = Params().get_int("EnableRadarTracks") >= 1
    self.rcp = get_radar_can_parser(CP, self.radar_tracks, self.radar_start_addr,
                                    self.radar_msg_count, self.radar_required_msg_count)
    self.group3_track_ids = Group3TrackIds()

    # Corner objects. Only decoded when the fingerprint says the car broadcasts them and
    # EnableRadarTracks is on; the 0x430 family is left out entirely (unvalidated layout).
    self.corner_object_tracks = (bool(CP.extFlags & HyundaiExtFlags.CORNER_RADAR_OBJECTS_235.value)
                                 and self.radar_tracks)
    self.corner_object_180_tracks = (bool(CP.extFlags & HyundaiExtFlags.CORNER_RADAR_OBJECTS_180.value)
                                     and self.radar_tracks)
    self.corner_object_track_ids = CornerObjectTrackIdManager()
    self.rcp_corner_objects = get_corner_object_can_parser(CP, self.corner_object_tracks)
    self.rcp_corner_objects_180 = get_corner_object_180_can_parser(CP, self.corner_object_180_tracks)
    self.trigger_msg_corner_objects = CORNER_OBJECT_235_START_ADDR + CORNER_OBJECT_235_MSG_COUNT - 1
    self.trigger_msg_corner_objects_180 = CORNER_OBJECT_180_START_ADDR + CORNER_OBJECT_180_MSG_COUNT - 1
    self.updated_corner_objects: set[int] = set()
    self.updated_corner_objects_180: set[int] = set()
    self.corner_objects_available = (self.rcp_corner_objects is not None
                                     or self.rcp_corner_objects_180 is not None)

    if self.rcp is None:
      self.initialize_radar_ext(self.trigger_msg)

  def update(self, can_strings):
    if self.radar_off_can and not self.corner_objects_available:
      return super().update(None)

    if self.rcp is not None:
      vls = self.rcp.update(can_strings)
      self.updated_messages.update(vls)

    if self.rcp_corner_objects is not None:
      self.updated_corner_objects.update(self.rcp_corner_objects.update(can_strings))
    if self.rcp_corner_objects_180 is not None:
      self.updated_corner_objects_180.update(self.rcp_corner_objects_180.update(can_strings))

    # Corner objects are merged on every frame that carries any of them; the track groups
    # only update when the last address of the group arrives, because a partial group
    # would publish a half-populated object list.
    self._update_corner_objects(self.updated_corner_objects)
    self._update_corner_objects_180(self.updated_corner_objects_180)

    track_group_ready = self.rcp is not None and self.trigger_msg in self.updated_messages
    if track_group_ready:
      ret = self._update(self.updated_messages)
      self.updated_messages.clear()
    elif self.corner_objects_available:
      # Corner objects arrive at their own rate; publish them even on frames where the
      # track group has not completed, otherwise they would appear only at the track rate.
      ret = structs.RadarData()
      if self.rcp is not None:
        ret.errors.canError = not self.rcp.can_valid
      ret.points = [p for p in self.pts.values() if p.measured]
    else:
      return None

    self.updated_corner_objects.clear()
    self.updated_corner_objects_180.clear()
    return ret

  def _update(self, updated_messages):
    ret = structs.RadarData()
    if self.rcp is None:
      return ret

    if not self.rcp.can_valid:
      ret.errors.canError = True

    if self.use_radar_interface_ext:
      return self.update_ext(ret)

    if self.radar_group3:
      return self._update_group3(ret, updated_messages)

    if self.canfd:
      return self._update_group12(ret, updated_messages)

    for addr in range(self.radar_start_addr, self.radar_start_addr + self.radar_msg_count):
      msg = self.rcp.vl[f"RADAR_TRACK_{addr:x}"]

      if addr not in self.pts:
        self.pts[addr] = structs.RadarData.RadarPoint()
        self.pts[addr].trackId = self.track_id
        self.track_id += 1

      valid = msg['STATE'] in (3, 4)
      if valid:
        azimuth = math.radians(msg['AZIMUTH'])
        self.pts[addr].dRel = math.cos(azimuth) * msg['LONG_DIST']
        self.pts[addr].yRel = 0.5 * -math.sin(azimuth) * msg['LONG_DIST']
        self.pts[addr].vRel = msg['REL_SPEED']

      else:
        del self.pts[addr]

    ret.points = list(self.pts.values())
    return ret

  def _update_group12(self, ret, updated_messages):
    """Decode the CAN-FD radar groups 1 and 2.

    Group 2 carries one object per message with VALID/VALID_CNT gating; group 1 carries
    two (the *_1 and *_2 signal families, the second half of the address range). They
    share LONG_DIST/LAT_DIST/REL_SPEED/LAT_SPEED/REL_ACCEL signal names, so unlike the
    Mando path there is no AZIMUTH to project through - the lateral offset is already
    in metres.

    Slots beyond radar_required_msg_count are optional: they do not participate in CAN
    validity, so a stale frame must not be kept as if it were current. Ported from cp.
    """
    t_id = 32
    for addr in range(self.radar_start_addr, self.radar_start_addr + self.radar_msg_count):
      msg = self.rcp.vl[f"RADAR_TRACK_{addr:x}"]
      if addr not in self.pts:
        self.pts[addr] = structs.RadarData.RadarPoint()
        self.pts[addr].trackId = t_id

      stale = (addr >= self.radar_start_addr + self.radar_required_msg_count
               and addr not in updated_messages)

      if self.radar_group1:
        valid, track_state, d_rel, y_rel, v_rel, a_rel, yv_rel = (
          msg['VALID_CNT1'] > 10, 0, msg['LONG_DIST1'], msg['LAT_DIST1'],
          msg['REL_SPEED1'], msg['REL_ACCEL1'], msg['LAT_SPEED1'])
      else:
        valid, track_state, d_rel, y_rel, v_rel, a_rel, yv_rel = (
          msg['VALID_CNT'] > 10, int(msg['VALID']), msg['LONG_DIST'], msg['LAT_DIST'],
          msg['REL_SPEED'], msg['REL_ACCEL'], msg['LAT_SPEED'])

      valid = bool(valid) and not stale
      point = self.pts[addr]
      point.measured = valid
      if not valid:
        point.dRel, point.yRel, point.vRel = 0., 0., 0.
        point.vLead = self.v_ego
        point.aRel, point.yvRel = float('nan'), 0.
      else:
        point.dRel, point.yRel, point.vRel = float(d_rel), float(y_rel), float(v_rel)
        point.vLead = point.vRel + self.v_ego
        point.aRel, point.yvRel = float(a_rel), float(yv_rel)
      t_id += 1

    ret.points = [p for p in self.pts.values() if p.measured]
    return ret

  def _clear_point(self, t_id: int):
    """Mark a slot unmeasured rather than deleting it.

    Deleting would re-create the point with a fresh trackId next cycle, which reads as a
    brand new object to the downstream tracker.
    """
    if t_id not in self.pts:
      self.pts[t_id] = structs.RadarData.RadarPoint()
    self.pts[t_id].measured = False
    self.pts[t_id].dRel = 0.
    self.pts[t_id].yRel = 0.
    self.pts[t_id].vRel = 0.
    self.pts[t_id].vLead = self.v_ego
    self.pts[t_id].aRel = float('nan')
    self.pts[t_id].yvRel = 0.

  def _update_corner_objects(self, updated_messages):
    """Decode the 0x235 corner object payloads (one object per message)."""
    if self.rcp_corner_objects is None:
      return

    if not updated_messages:
      self._apply_corner_objects(
        "corner235", [],
        range(CORNER_OBJECT_235_TRACK_ID_OFFSET,
              CORNER_OBJECT_235_TRACK_ID_OFFSET + CORNER_OBJECT_235_MSG_COUNT))
      return

    candidates = []
    for slot, addr in enumerate(range(CORNER_OBJECT_235_START_ADDR,
                                      CORNER_OBJECT_235_START_ADDR + CORNER_OBJECT_235_MSG_COUNT)):
      t_id = CORNER_OBJECT_235_TRACK_ID_OFFSET + slot
      msg = self.rcp_corner_objects.vl[f"CORNER_RADAR_235_OBJECTS_{addr:x}"]

      d_rel, y_rel = msg["OBJ_REL_POS_X"], msg["OBJ_REL_POS_Y"]
      v_rel, yv_rel = msg["OBJ_REL_VEL_X"], msg["OBJ_REL_VEL_Y"]
      a_rel = msg["OBJ_REL_ACCEL_X"]
      # Side objects are clipped to x=0 by the corner radar; quality, identity and
      # lateral motion still describe a real object, which is why the position test
      # accepts that clipped case rather than dropping the object.
      valid = (msg["OBJ_QUAL_LEVEL"] > 0 and corner_object_position_valid(d_rel, y_rel)
               and v_rel > -99.0)
      if not valid:
        continue
      candidates.append((t_id, int(msg["OBJ_OBJECT_ID"]), int(msg["OBJ_AGE"]),
                         int(msg["OBJ_QUAL_LEVEL"]), d_rel, y_rel, v_rel, yv_rel, a_rel))

    self._apply_corner_objects(
      "corner235", candidates,
      range(CORNER_OBJECT_235_TRACK_ID_OFFSET,
            CORNER_OBJECT_235_TRACK_ID_OFFSET + CORNER_OBJECT_235_MSG_COUNT))

  def _update_corner_objects_180(self, updated_messages):
    """Decode the 0x180 corner object payloads (two slots per message)."""
    if self.rcp_corner_objects_180 is None:
      return

    slots_total = CORNER_OBJECT_180_MSG_COUNT * CORNER_OBJECT_180_SLOTS_PER_MSG
    if not updated_messages:
      self._apply_corner_objects(
        "corner180", [],
        range(CORNER_OBJECT_180_TRACK_ID_OFFSET, CORNER_OBJECT_180_TRACK_ID_OFFSET + slots_total))
      return

    candidates = []
    for msg_index, addr in enumerate(range(CORNER_OBJECT_180_START_ADDR,
                                           CORNER_OBJECT_180_START_ADDR + CORNER_OBJECT_180_MSG_COUNT)):
      msg = self.rcp_corner_objects_180.vl[f"CORNER_RADAR_180_OBJECTS_{addr:x}"]
      for slot_index in range(CORNER_OBJECT_180_SLOTS_PER_MSG):
        t_id = (CORNER_OBJECT_180_TRACK_ID_OFFSET
                + msg_index * CORNER_OBJECT_180_SLOTS_PER_MSG + slot_index)
        prefix = f"SLOT{slot_index + 1}_"
        d_rel, y_rel = msg[f"{prefix}REL_POS_X"], msg[f"{prefix}REL_POS_Y"]
        v_rel, yv_rel = msg[f"{prefix}REL_VEL_X"], msg[f"{prefix}REL_VEL_Y"]
        a_rel = msg[f"{prefix}REL_ACCEL_X"]
        valid = (msg[f"{prefix}QUAL_LEVEL"] > 0 and corner_object_position_valid(d_rel, y_rel)
                 and v_rel > -99.0)
        if not valid:
          continue
        candidates.append((t_id, int(msg[f"{prefix}OBJECT_ID"]), int(msg[f"{prefix}AGE"]),
                           int(msg[f"{prefix}QUAL_LEVEL"]), d_rel, y_rel, v_rel, yv_rel, a_rel))

    self._apply_corner_objects(
      "corner180", candidates,
      range(CORNER_OBJECT_180_TRACK_ID_OFFSET, CORNER_OBJECT_180_TRACK_ID_OFFSET + slots_total))

  def _apply_corner_objects(self, source, candidates, slot_ids):
    for t_id in slot_ids:
      self._clear_point(t_id)

    # The same object can sit in two CAN slots for one cycle during a handoff. Only
    # physically close copies are merged - one object ID can be on two distant objects at
    # the same time, so ID alone is not an identity.
    objects = deduplicate_corner_candidates(candidates)
    track_ids = self.corner_object_track_ids.get_track_ids(source, objects)

    for t_id, _, _, _, d_rel, y_rel, v_rel, yv_rel, a_rel in objects:
      point = self.pts[t_id]
      point.measured = True
      point.trackId = track_ids[t_id]
      point.radarSource = source
      point.dRel, point.yRel, point.vRel = float(d_rel), float(y_rel), float(v_rel)
      point.vLead = point.vRel + self.v_ego
      point.aRel, point.yvRel = float(a_rel), float(yv_rel)

  def _update_group3(self, ret, updated_messages):
    """Decode the group-3 object list.

    Group 3 addresses are transport slots, not identities: objects move between
    addresses, and an address can be reused for a different object. Group3TrackIds
    resolves a stable identifier per object so the downstream tracker does not see a
    new target every time an object shifts slot, and so a reused slot does not inherit
    the previous occupant's state.

    Points are keyed by slot offset from the group start, and the previous entries are
    cleared first - an unmeasured copy left behind would reset the surviving object's
    filter. Ported from cp.
    """
    objects = {
      addr: Group3Object.from_signals(self.rcp.vl[f"RADAR_TRACK_{addr:x}"])
      for addr in range(self.radar_start_addr, self.radar_start_addr + self.radar_msg_count)
      if addr in updated_messages
    }
    assignments = self.group3_track_ids.update(objects)

    for slot in range(32, 32 + self.radar_msg_count):
      self.pts.pop(slot, None)

    for addr, track_id in assignments.items():
      obj = objects[addr]
      point = structs.RadarData.RadarPoint()
      point.trackId = track_id
      point.radarSource = "frontRadar"
      point.measured = True
      point.dRel, point.yRel, point.vRel = obj.d_rel, obj.y, obj.v
      point.vLead, point.aRel, point.yvRel = self.v_ego + obj.v, float("nan"), 0.0
      self.pts[32 + addr - self.radar_start_addr] = point

    ret.points = list(self.pts.values())
    return ret
