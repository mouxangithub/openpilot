"""Suspend signal-specific control only on a fresh, explicit vNavi road class.

Ported from carrot (signal_road_policy): signal detection is suppressed on a
motorway/expressway road class reported by the navigation source, so the car
does not brake for a red light (or gantry lamp) on a high-speed road where a
traffic-light stop is implausible. Any missing / stale / unset source is NOT
evidence of a motorway (returns False = keep detecting).
"""
import time

NAVI_TIMEOUT = 2.0
ROAD_TIMEOUT = 10.0  # v2 JSON stream's advertised stale_timeout_ms

# sp publishes the navigation state on carrotNaviSP (cp used carrotNavi).
NAVI_SERVICE = 'carrotNaviSP'


def signal_detection_suspended(sm, now=None):
  now = time.monotonic() if now is None else now
  try:
    if not (sm.seen[NAVI_SERVICE] and sm.valid[NAVI_SERVICE] and sm.alive[NAVI_SERVICE]):
      return False
    if not 0 <= now - sm.recv_time[NAVI_SERVICE] <= NAVI_TIMEOUT:
      return False
    navi = sm[NAVI_SERVICE]
    lane = navi.laneCurrent
    if navi.schemaVersion != 1 or not navi.connected or not navi.sessionId:
      return False
    if navi.navigationStatus.meta.present and navi.navigationStatus.offRoute:
      return False
    # roadCategory defaults to zero in old messages and when the source omits
    # it. Neither case is evidence of a motorway.
    return bool(lane.meta.present and lane.roadCategoryValid and lane.roadCategory in (0, 1)
                and lane.meta.receivedMonoTimeNanos > 0
                and 0 <= now - lane.meta.receivedMonoTimeNanos / 1e9 <= ROAD_TIMEOUT)
  except (AttributeError, KeyError, TypeError):
    return False
