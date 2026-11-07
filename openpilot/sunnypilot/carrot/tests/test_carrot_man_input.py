#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import time
import unittest


from openpilot.sunnypilot.carrot.carrot_man_input import CARROT_MAN_TIMEOUT, get_carrot_man


class _FakeCap:
  def __init__(self, desired_speed: float = 60.0):
    self.desiredSpeed = desired_speed


class _FakeSM:
  """Minimal SubMaster stand-in for the fields get_carrot_man touches."""

  def __init__(self, *, seen=True, alive=True, valid=True, recv_age=0.0, desired_speed=60.0):
    self.seen = {'carrotManSP': seen}
    self.alive = {'carrotManSP': alive}
    self.valid = {'carrotManSP': valid}
    self.recv_time = {'carrotManSP': time.monotonic() - recv_age}
    self._cap = _FakeCap(desired_speed)

  def __getitem__(self, service):
    assert service == 'carrotManSP'
    return self._cap


class TestGetCarrotMan(unittest.TestCase):
  def test_returns_cap_when_fresh_and_sane(self):
    cap = get_carrot_man(_FakeSM())
    self.assertIsNotNone(cap)
    self.assertEqual(cap.desiredSpeed, 60.0)

  def test_rejects_unseen_service(self):
    self.assertIsNone(get_carrot_man(_FakeSM(seen=False)))

  def test_rejects_dead_publisher(self):
    self.assertIsNone(get_carrot_man(_FakeSM(alive=False)))

  def test_rejects_invalid_service(self):
    self.assertIsNone(get_carrot_man(_FakeSM(valid=False)))

  def test_rejects_stale_frame(self):
    self.assertIsNone(get_carrot_man(_FakeSM(recv_age=CARROT_MAN_TIMEOUT + 0.01)))

  def test_accepts_frame_just_inside_timeout(self):
    # just inside the window: an exact-boundary recv_age would flake because
    # the stub and the gate read time.monotonic() at different instants
    self.assertIsNotNone(get_carrot_man(_FakeSM(recv_age=CARROT_MAN_TIMEOUT - 0.05)))

  def test_rejects_future_recv_time(self):
    # negative age means a broken clock: cp's gate treats it as unusable
    sm = _FakeSM()
    sm.recv_time['carrotManSP'] = time.monotonic() + 1.0
    self.assertIsNone(get_carrot_man(sm))

  def test_rejects_zero_desired_speed(self):
    self.assertIsNone(get_carrot_man(_FakeSM(desired_speed=0.0)))

  def test_rejects_out_of_range_desired_speed(self):
    self.assertIsNone(get_carrot_man(_FakeSM(desired_speed=251.0)))

  def test_accepts_boundary_desired_speed(self):
    self.assertIsNotNone(get_carrot_man(_FakeSM(desired_speed=250.0)))


if __name__ == '__main__':
  unittest.main()
