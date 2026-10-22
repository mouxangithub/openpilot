"""One decision point for which navigation GPS source is usable.

The service used to answer this twice: `gps_source` (for the UI) only checked
freshness and a non-zero coordinate, while `_phone_gps_is_usable` (for the data
path) also required a plausible accuracy. The UI could therefore report "phone"
for a fix the fallback had refused. Both now call the same selector.

Priority is navi > phone > device. The device source is the localizer's own
fused position and only fills the gap where the alternative is a (0, 0) fix.
"""
import importlib.util
import sys
import time
import unittest

from openpilot.sunnypilot.carrot.gps_sources import (Fix, PHONE_MAX_ACCURACY_M, PRIORITY, WINDOWS,
                                                     fresh, plausible, select, usable)


def _real_module(name):
  """True when ``name`` is importable for real, not stubbed by another test.

  Some carrot test modules install fake ``openpilot.common``/``cereal`` packages
  into ``sys.modules``, which also makes ``zstandard`` resolvable. Under
  ``unittest discover`` that leakage would make this module importable by
  accident and the result would then depend on collection order. A stub has no
  string ``__file__``, so it is distinguishable from a really imported module.
  """
  module = sys.modules.get(name)
  if module is None:
    return importlib.util.find_spec(name) is not None
  return isinstance(getattr(module, '__file__', None), str)


HAVE_SERV = _real_module('zstandard') and _real_module('opendbc')
CarrotServ = None
if HAVE_SERV:
  try:
    from openpilot.sunnypilot.carrot.carrot_serv import CarrotServ
  except ImportError:
    HAVE_SERV = False

NOW = 1000.0


def fix(lat=37.5, lon=127.0, age=0.0, accuracy=5.0, heading=0.0, speed=0.0):
  return Fix(lat, lon, heading, speed, accuracy, NOW - age)


class TestPlausibility(unittest.TestCase):
  def test_normal_fix_is_plausible(self):
    self.assertTrue(plausible(fix()))

  def test_null_island_is_rejected(self):
    self.assertFalse(plausible(fix(0.0, 0.0)))

  def test_out_of_range_is_rejected(self):
    self.assertFalse(plausible(fix(lat=91.0)))
    self.assertFalse(plausible(fix(lon=-181.0)))

  def test_teleport_speed_and_non_finite_are_rejected(self):
    self.assertFalse(plausible(fix(speed=91.0)))
    self.assertTrue(plausible(fix(speed=89.9)))
    self.assertFalse(plausible(Fix(float('nan'), 127.0, stamp=NOW)))
    self.assertFalse(plausible(Fix(37.5, float('inf'), stamp=NOW)))

  def test_zero_speed_is_fine(self):
    self.assertTrue(plausible(fix(speed=0.0)))


class TestFreshness(unittest.TestCase):
  def test_window_is_per_source_and_inclusive(self):
    for source in PRIORITY:
      window = WINDOWS[source]
      self.assertTrue(fresh(fix(age=window), NOW, source))
      self.assertFalse(fresh(fix(age=window + .01), NOW, source))

  def test_a_future_stamp_is_not_fresh(self):
    self.assertFalse(fresh(fix(age=-1.0), NOW, 'external_navi'))


class TestSelection(unittest.TestCase):
  def test_navi_wins_over_a_fresher_phone(self):
    source, chosen = select({'external_navi': fix(age=.5), 'phone': fix(lat=37.6, age=0.)}, NOW)
    self.assertEqual(source, 'navi')
    self.assertEqual(chosen.lat, 37.5)

  def test_phone_takes_over_a_stale_navi(self):
    fixes = {'external_navi': fix(age=5.), 'phone': fix(lat=37.6)}
    self.assertEqual(select(fixes, NOW)[0], 'phone')

  def test_coarse_phone_is_refused(self):
    fixes = {'phone': fix(accuracy=PHONE_MAX_ACCURACY_M)}
    self.assertEqual(select(fixes, NOW), ('none', None))
    fixes = {'phone': fix(accuracy=PHONE_MAX_ACCURACY_M - .1)}
    self.assertEqual(select(fixes, NOW)[0], 'phone')

  def test_device_is_the_last_resort(self):
    fixes = {'external_navi': fix(age=9.), 'phone': fix(age=9.), 'device': fix(lat=37.4)}
    source, chosen = select(fixes, NOW)
    self.assertEqual(source, 'device')
    self.assertEqual(chosen.lat, 37.4)

  def test_implausible_fix_falls_through_to_the_next_source(self):
    fixes = {'external_navi': fix(0.0, 0.0), 'phone': fix(lat=37.6)}
    self.assertEqual(select(fixes, NOW)[0], 'phone')

  def test_nothing_usable_reports_none(self):
    self.assertEqual(select({}, NOW), ('none', None))
    self.assertEqual(select({'phone': fix(age=10.)}, NOW), ('none', None))

  def test_unknown_source_is_ignored(self):
    self.assertEqual(select({'vehicle': fix()}, NOW), ('none', None))

  def test_labels_are_the_public_names(self):
    self.assertEqual(select({'external_navi': fix()}, NOW)[0], 'navi')
    self.assertTrue(usable(fix(), NOW, 'external_navi'))


@unittest.skipUnless(HAVE_SERV, 'carrot_serv needs zstandard and the opendbc checkout')
class TestCarrotServUsesTheSameSelector(unittest.TestCase):
  def setUp(self):
    self.serv = CarrotServ()
    self.serv.reset()

  def phone(self, **kw):
    packet = {'latitude': 37.5, 'longitude': 127.0, 'heading': 10.0, 'accuracy': 5.0}
    packet.update(kw)
    self.serv.update_raw(packet, time.monotonic())

  def test_fixes_snapshot_carries_each_source(self):
    self.phone()
    fixes = self.serv._gps_fixes()
    self.assertEqual(set(fixes), set(PRIORITY))
    self.assertAlmostEqual(fixes['phone'].lat, 37.5)
    self.assertAlmostEqual(fixes['phone'].heading, 10.0)

  def test_phone_fills_the_raw_position_when_navi_is_absent(self):
    self.phone()
    self.assertAlmostEqual(self.serv.raw['vpPosPointLat'], 37.5)
    self.assertAlmostEqual(self.serv.raw['vpPosPointLon'], 127.0)
    self.assertAlmostEqual(self.serv.raw['nPosAngle'], 10.0)

  def test_a_navi_fix_in_the_packet_wins(self):
    self.phone()
    self.serv.update_raw({'vpPosPointLat': 37.25, 'vpPosPointLon': 127.25, 'nPosAngle': 45.0},
                         time.monotonic())
    self.assertAlmostEqual(self.serv.raw['vpPosPointLat'], 37.25)
    self.assertEqual(self.serv.gps_source, 'navi')

  def test_the_reported_source_agrees_with_the_data_path(self):
    self.phone(accuracy=20.0)  # too coarse for the fallback
    self.assertEqual(self.serv.gps_source, 'none')
    self.assertEqual(self.serv.raw['vpPosPointLat'], 0.0)

  def test_the_reported_source_can_be_the_device(self):
    # The property reads the real monotonic clock, so the device stamp must too.
    self.serv._device_gps = Fix(37.4, 127.4, stamp=time.monotonic())
    self.assertEqual(self.serv.gps_source, 'device')

  def test_invalid_localizer_fix_is_ignored(self):
    class Measurement:
      valid = False
      value = [37.4, 127.4]

    class Llk:
      positionGeodetic = Measurement()
      status = None
      gpsOK = True

    before = self.serv._device_gps
    self.serv.update_device_gps({'liveLocationKalman': Llk()})
    self.assertEqual(self.serv._device_gps, before)


if __name__ == '__main__':
  unittest.main()
