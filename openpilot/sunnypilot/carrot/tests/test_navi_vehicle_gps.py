"""7714 v2 vehicle stream -> external_navi GPS source chain (cp semantics port).

Covers the two round-3 audit gaps:
1. carrot_navi_cereal must publish roadCategoryValid, otherwise the motorway
   signal suppression in signal_road_policy can never fire (the flag stays at
   its capnp default False and "unset" becomes indistinguishable from
   "expressway").
2. The vehicle stream must feed the external_navi GPS source with heartbeat
   dedup and original receipt-time preservation (cp: a cereal heartbeat is not
   a GPS fix; dead reckoning and map freshness must not restart on it).
"""
import sys
import time
import types
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

# PC hosts have no libparams_c.so / capnp runtime: stub the same four modules
# test_carrot_man.py stubs before importing the carrot subtree. Saved modules
# are restored at the bottom so this file never poisons sibling test modules.
_SAVED_MODULES = {name: sys.modules.get(name) for name in (
  "openpilot.common", "openpilot.common.params", "openpilot.common.realtime", "openpilot.common.swaglog",
  "openpilot.cereal", "openpilot.cereal.messaging",
)}
_common_pkg = types.ModuleType("openpilot.common")
_common_pkg.params = MagicMock(Params=MagicMock)
_common_pkg.realtime = MagicMock(DT_MDL=0.05, DT_CTRL=0.01, Ratekeeper=MagicMock,
                                 config_realtime_process=MagicMock())
_common_pkg.swaglog = MagicMock(cloudlog=MagicMock())
sys.modules["openpilot.common"] = _common_pkg
sys.modules["openpilot.common.params"] = _common_pkg.params
sys.modules["openpilot.common.realtime"] = _common_pkg.realtime
sys.modules["openpilot.common.swaglog"] = _common_pkg.swaglog
_cereal_pkg = types.ModuleType("openpilot.cereal")
_cereal_pkg.messaging = MagicMock()
sys.modules["openpilot.cereal"] = _cereal_pkg
sys.modules["openpilot.cereal.messaging"] = _cereal_pkg.messaging

from openpilot.sunnypilot.carrot.carrot_navi_cereal import _lane
from openpilot.sunnypilot.carrot.carrot_man import CarrotManager, _NaviVehicleControl
from openpilot.sunnypilot.carrot.carrot_serv import CarrotServ
from openpilot.sunnypilot.carrot.gps_sources import select


def _vehicle_item(sequence=3, lat=37.5, lon=127.0, received_ns=0):
  return {
    'meta': {'present': True, 'sequence': sequence, 'receivedMonoTimeNanos': received_ns},
    'latitude': lat,
    'longitude': lon,
    'headingDeg': 90.0,
    'speedKph': 60.0,
    'roadName': 'test road',
  }


class TestRoadCategoryValidPublished(unittest.TestCase):
  def test_valid_range_published_true(self):
    payload = _lane({}, {'road_category': 1})
    assert payload['roadCategoryValid'] is True

  def test_out_of_range_published_false(self):
    assert _lane({}, {'road_category': 13})['roadCategoryValid'] is False
    assert _lane({}, {'road_category': -1})['roadCategoryValid'] is False

  def test_missing_published_false(self):
    assert _lane({}, {})['roadCategoryValid'] is False

  def test_non_int_published_false(self):
    # cp semantics: validity requires an int source field; a string "1" is
    # not evidence of a road class.
    assert _lane({}, {'road_category': '1'})['roadCategoryValid'] is False


class TestNaviVehicleGpsSource(unittest.TestCase):
  def setUp(self):
    self.serv = CarrotServ()

  def test_vehicle_fix_feeds_external_navi(self):
    self.serv.update_navi_vehicle_position(37.5, 127.0, 90.0, 60.0, 'test road', 0, 5)
    now = time.monotonic()
    fixes = self.serv._gps_fixes()
    assert fixes['external_navi'].lat == 37.5
    assert fixes['external_navi'].lon == 127.0
    assert fixes['external_navi'].stamp > 0.0
    source, fix = select(fixes, now)
    assert source == 'navi' and fix is not None
    # Raw packet stays in sync for the UI / road-name consumers.
    assert self.serv.raw['vpPosPointLat'] == 37.5
    assert self.serv.raw['nPosSpeed'] == 60.0
    assert self.serv.raw['szPosRoadName'] == 'test road'

  def test_heartbeat_does_not_restart_freshness(self):
    t0 = time.monotonic()
    first_received_ns = int((t0 - 5.0) * 1e9)
    self.serv.update_navi_vehicle_position(37.5, 127.0, 90.0, 60.0, '', first_received_ns, 7)
    stamp_after_fix = self.serv._last_update_gps_time_navi
    assert abs(stamp_after_fix - (t0 - 5.0)) < 0.5
    # A 2 Hz heartbeat re-sends the same fix: same sequence, "fresher" stamp.
    self.serv.update_navi_vehicle_position(37.5, 127.0, 90.0, 60.0, '', int(time.monotonic() * 1e9), 7)
    assert self.serv._last_update_gps_time_navi == stamp_after_fix

  def test_future_timestamp_refused(self):
    now = time.monotonic()
    self.serv.update_navi_vehicle_position(37.5, 127.0, 90.0, 60.0, '', int((now + 100.0) * 1e9), 9)
    assert self.serv._navi_vehicle_sequence == -1
    assert self.serv._last_update_gps_time_navi == 0.0
    # The sequence was not consumed: a well-stamped fix with the same
    # sequence must still apply.
    self.serv.update_navi_vehicle_position(37.5, 127.0, 90.0, 60.0, '', 0, 9)
    assert self.serv._navi_vehicle_sequence == 9
    assert self.serv._gps_fixes()['external_navi'].lat == 37.5

  def test_disconnected_expires_source_and_keeps_sequence(self):
    self.serv.update_navi_vehicle_position(37.5, 127.0, 90.0, 60.0, 'test road', 0, 11)
    self.serv.navi_vehicle_disconnected()
    assert self.serv._last_update_gps_time_navi == 0.0
    assert self.serv.raw['szPosRoadName'] == ''
    source, _ = select(self.serv._gps_fixes(), time.monotonic())
    assert source != 'navi'
    # cp semantics: sequence tracking survives the disconnect, so a late
    # re-transmission of the same fix is still recognised as a heartbeat.
    self.serv.update_navi_vehicle_position(38.0, 128.0, 90.0, 60.0, '', 0, 11)
    assert self.serv._last_update_gps_time_navi == 0.0

  def test_new_sequence_after_disconnect_reapplies(self):
    self.serv.update_navi_vehicle_position(37.5, 127.0, 90.0, 60.0, '', 0, 11)
    self.serv.navi_vehicle_disconnected()
    self.serv.update_navi_vehicle_position(38.0, 128.0, 91.0, 55.0, 'back', 0, 12)
    source, fix = select(self.serv._gps_fixes(), time.monotonic())
    assert source == 'navi' and fix.lat == 38.0


class TestVehicleDispatch(unittest.TestCase):
  """carrot_man dispatch wiring: present -> feed, absent -> expire."""

  def test_present_vehicle_feeds_serv(self):
    serv = CarrotServ()
    fake_man = SimpleNamespace(_carrot_serv=serv)
    vehicle = _NaviVehicleControl(_vehicle_item(sequence=3, received_ns=123))
    assert vehicle.present and vehicle.received_mono_time_ns == 123
    CarrotManager._apply_carrot_navi_vehicle(fake_man, vehicle)
    assert serv._navi_vehicle_sequence == 3
    assert serv._gps_fixes()['external_navi'].lat == 37.5

  def test_absent_vehicle_expires_serv(self):
    serv = CarrotServ()
    serv.update_navi_vehicle_position(37.5, 127.0, 90.0, 60.0, 'test road', 0, 4)
    fake_man = SimpleNamespace(_carrot_serv=serv)
    CarrotManager._apply_carrot_navi_vehicle(fake_man, _NaviVehicleControl({'meta': {'present': False, 'sequence': 5}}))
    assert serv._last_update_gps_time_navi == 0.0
    assert serv.raw['szPosRoadName'] == ''


if __name__ == '__main__':
  unittest.main()

# Restore the real modules so later test modules in the same process are not
# poisoned by the stubs (same discipline as test_carrot_man.py).
for _name, _module in _SAVED_MODULES.items():
  if _module is None:
    sys.modules.pop(_name, None)
  else:
    sys.modules[_name] = _module
