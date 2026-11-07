"""Signal road policy: suspend red-light control only on a fresh explicit
motorway road class. Missing/stale/unset sources keep detecting (False)."""
import unittest
from types import SimpleNamespace as NS

from openpilot.sunnypilot.carrot.signal_road_policy import signal_detection_suspended

NAVI = 'carrotNaviSP'


class _SM:
  def __init__(self, navi_msg, seen, valid, alive, recv_time):
    self._navi = navi_msg
    self.seen, self.valid, self.alive, self.recv_time = seen, valid, alive, recv_time

  def __getitem__(self, key):
    return self._navi


def _sm(seen=True, valid=True, alive=True, recv_age=0.0, **navi):
  lane = NS(meta=NS(present=navi.get('lane_meta_present', True),
                    receivedMonoTimeNanos=navi.get('lane_recv_ns', 0)),
            roadCategory=navi.get('roadCategory', 0),
            roadCategoryValid=navi.get('roadCategoryValid', True))
  navigation_status = NS(meta=NS(present=navi.get('ns_meta_present', False)),
                         offRoute=navi.get('offRoute', False))
  navi_msg = NS(schemaVersion=navi.get('schemaVersion', 1),
                connected=navi.get('connected', True),
                sessionId=navi.get('sessionId', 'sid'),
                laneCurrent=lane, navigationStatus=navigation_status)
  now = navi.get('now', 100.0)
  return _SM(navi_msg, {NAVI: seen}, {NAVI: valid}, {NAVI: alive}, {NAVI: now - recv_age})


class TestSignalRoadPolicy(unittest.TestCase):
  def test_missing_source_keeps_detecting(self):
    sm = _sm(seen=False)
    self.assertFalse(signal_detection_suspended(sm, now=100.0))

  def test_stale_navi_keeps_detecting(self):
    sm = _sm(recv_age=5.0, lane_recv_ns=99_500_000_000)
    self.assertFalse(signal_detection_suspended(sm, now=100.0))

  def test_motorway_class_suspends(self):
    sm = _sm(roadCategory=1, lane_recv_ns=100_000_000_000)
    self.assertTrue(signal_detection_suspended(sm, now=100.0))

  def test_road_category_zero_valid_suspends(self):
    sm = _sm(roadCategory=0, lane_recv_ns=100_000_000_000)
    self.assertTrue(signal_detection_suspended(sm, now=100.0))

  def test_invalid_category_keeps_detecting(self):
    sm = _sm(roadCategory=1, roadCategoryValid=False, lane_recv_ns=100_000_000_000)
    self.assertFalse(signal_detection_suspended(sm, now=100.0))

  def test_off_route_keeps_detecting(self):
    sm = _sm(roadCategory=1, lane_recv_ns=100_000_000_000, ns_meta_present=True, offRoute=True)
    self.assertFalse(signal_detection_suspended(sm, now=100.0))

  def test_not_connected_keeps_detecting(self):
    sm = _sm(roadCategory=1, lane_recv_ns=100_000_000_000, connected=False)
    self.assertFalse(signal_detection_suspended(sm, now=100.0))

  def test_stale_road_receipt_keeps_detecting(self):
    sm = _sm(roadCategory=1, lane_recv_ns=int((100.0 - 20.0) * 1e9))
    self.assertFalse(signal_detection_suspended(sm, now=100.0))

  def test_malformed_is_safe(self):
    self.assertFalse(signal_detection_suspended(object(), now=100.0))


if __name__ == "__main__":
  unittest.main()
