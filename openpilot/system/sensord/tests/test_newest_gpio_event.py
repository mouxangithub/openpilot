#!/usr/bin/env python3
"""The gpioevent buffer may hold several pending data-ready edges after a delayed poll;
only the newest timestamp belongs with the sample read right after."""
import struct
import unittest

from openpilot.system.sensord.sensord import newest_gpio_event


def pack_event(timestamp: int, event_id: int) -> bytes:
  # gpioevent_data is __u64 timestamp + __u32 id, padded to 16 bytes by the ABI.
  return struct.pack('<QI', timestamp, event_id) + b'\x00' * 4


class TestNewestGpioEvent(unittest.TestCase):
  def test_empty_read_is_none(self):
    assert newest_gpio_event(b'') is None

  def test_partial_record_is_none(self):
    assert newest_gpio_event(b'\x00' * 8) is None

  def test_single_event(self):
    ev = newest_gpio_event(pack_event(111, 1))
    assert ev is not None and ev.timestamp == 111 and ev.id == 1

  def test_returns_newest_of_several(self):
    buf = pack_event(111, 1) + pack_event(222, 2) + pack_event(333, 3)
    ev = newest_gpio_event(buf)
    assert ev is not None and ev.timestamp == 333 and ev.id == 3

  def test_trailing_partial_ignored(self):
    buf = pack_event(111, 1) + pack_event(222, 2) + b'\x00' * 5
    ev = newest_gpio_event(buf)
    assert ev is not None and ev.timestamp == 222


if __name__ == "__main__":
  unittest.main()
