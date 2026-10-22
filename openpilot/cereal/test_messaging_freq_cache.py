"""SubMaster health-check caching must not change any decision.

`freq_ok` used to re-read the frequency tracker on every loop even though a
frequency window only advances when that service delivers a message, and the
`all_*` helpers used generator expressions. Both are now cheaper. These lock
that the observable answers are identical to a per-iteration recomputation.
"""
import unittest
from unittest.mock import patch

from openpilot.cereal import messaging, services


class _CountingTracker:
  """FrequencyTracker stand-in that counts how often `valid` is read."""

  def __init__(self, valid):
    self._valid = valid
    self.reads = 0

  @property
  def valid(self):
    self.reads += 1
    return self._valid

  @valid.setter
  def valid(self, value):
    self._valid = value

  def record_recv_time(self, cur_time):
    pass


def _received(service):
  """A message shaped like what recv_one_or_none hands to update_msgs().

  'can' carries a list payload, so it needs an explicit size.
  """
  if service == 'can':
    dat = messaging.new_message('can', size=1, logMonoTime=1, valid=True)
  else:
    dat = messaging.new_message(service, logMonoTime=1, valid=True)
  return dat.as_reader()


def _feed(sm, *services, cur_time=1.0):
  """Deliver one message per service so alive/valid/freq carry real values."""
  sm.update_msgs(cur_time, [_received(s) for s in services])


class TestAllChecksEquivalence(unittest.TestCase):
  def setUp(self):
    self.sm = messaging.SubMaster(['carState', 'modelV2', 'can'])

  def _reference_all(self, method, ignore_attr, service_list=None):
    """Straight per-call recomputation, independent of the cached fields."""
    for s in service_list or self.sm.services:
      if s in getattr(self.sm, ignore_attr):
        continue
      if method == 'all_alive':
        ok = self.sm.alive[s]
      elif method == 'all_freq_ok':
        ok = (services.SERVICE_LIST[s].frequency > 0.99 and s not in self.sm.ignore_average_freq
              and s not in self.sm.ignore_alive)
        ok = ok and (self.sm.freq_tracker[s].valid or self.sm.simulation)
      else:
        ok = self.sm.valid[s]
      if not ok:
        return False
    return True

  def test_helpers_match_a_direct_recomputation(self):
    # Feed all three so alive/valid/freq all carry real values.
    _feed(self.sm, 'carState', 'modelV2', 'can')
    for method, ignore in (('all_alive', 'ignore_alive'), ('all_valid', 'ignore_valid'),
                           ('all_freq_ok', 'ignore_average_freq')):
      for service_list in (None, ['carState'], ['modelV2', 'can']):
        with self.subTest(method=method, services=service_list):
          self.assertEqual(getattr(self.sm, method)(service_list),
                           self._reference_all(method, ignore, service_list))
      # An ignored entry must change nothing about the verdict.
      ignored = self.sm.services[0]
      getattr(self.sm, ignore).append(ignored)
      with patch.dict(self.sm.alive if method == 'all_alive' else
                      self.sm.valid if method == 'all_valid' else self.sm.freq_ok,
                      {ignored: False}):
        self.assertEqual(getattr(self.sm, method)(), self._reference_all(method, ignore))
      getattr(self.sm, ignore).remove(ignored)

  def test_short_circuit_stops_at_the_first_failure(self):
    # A service never seen yet is not alive, so restrict the list to one that
    # has been fed a message.
    _feed(self.sm, 'carState', 'modelV2')
    with patch.dict(self.sm.alive, {'carState': False}):
      self.assertFalse(self.sm.all_alive())
      # A restricted list that excludes the failing service must still pass.
      self.assertTrue(self.sm.all_alive(['modelV2']))
    with patch.dict(self.sm.valid, {'modelV2': False}):
      self.assertFalse(self.sm.all_valid())
      self.assertTrue(self.sm.all_valid(['carState']))

  def test_ignore_lists_are_honored(self):
    # Feed every service so only the entries this test flips can fail the check.
    _feed(self.sm, 'carState', 'modelV2', 'can')
    self.sm.ignore_alive.append('carState')
    with patch.dict(self.sm.alive, {'carState': False}):
      self.assertTrue(self.sm.all_alive())
    self.sm.ignore_valid.append('modelV2')
    with patch.dict(self.sm.valid, {'modelV2': False}):
      self.assertTrue(self.sm.all_valid())


class TestReceivedFreqOkCache(unittest.TestCase):
  def setUp(self):
    self.sm = messaging.SubMaster(['carState'])

  def test_cache_starts_in_sync_with_freq_ok(self):
    for s in self.sm.services:
      self.assertEqual(self.sm._received_freq_ok[s], self.sm.freq_ok[s])

  def test_no_receipt_keeps_the_last_verdict(self):
    sm = self.sm
    sm.freq_tracker['carState'] = _CountingTracker(True)
    _feed(sm, 'carState')
    self.assertTrue(sm.freq_ok['carState'])

    # No new message: the tracker is not re-read, and the verdict holds.
    tracker = sm.freq_tracker['carState']
    before = tracker.reads
    sm.update_msgs(1.1, [])
    self.assertEqual(tracker.reads, before)
    self.assertTrue(sm.freq_ok['carState'])

  def test_a_new_message_refreshes_the_verdict(self):
    sm = self.sm
    tracker = _CountingTracker(True)
    sm.freq_tracker['carState'] = tracker
    _feed(sm, 'carState', cur_time=2.0)
    self.assertTrue(sm.freq_ok['carState'])

    tracker.valid = False
    _feed(sm, 'carState', cur_time=2.1)
    self.assertFalse(sm.freq_ok['carState'])

  def test_simulation_relaxes_the_check(self):
    sm = self.sm
    sm.simulation = True
    sm.freq_tracker['carState'] = _CountingTracker(False)
    sm.update_msgs(3.0, [])
    self.assertTrue(sm.freq_ok['carState'])


if __name__ == '__main__':
  unittest.main()
