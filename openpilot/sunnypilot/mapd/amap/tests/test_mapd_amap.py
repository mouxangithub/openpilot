#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import json
import sys
import time
import types
import unittest
from unittest.mock import MagicMock


class _FakeMsg:
  def __init__(self):
    self.amapNaviSP = MagicMock()
    self.valid = False


class _FakeMessaging:
  @staticmethod
  def PubMaster(services):
    pm = MagicMock()
    pm.send = MagicMock()
    return pm

  @staticmethod
  def new_message(service):
    return _FakeMsg()


class _FakeParams:
  def __init__(self):
    self._store = {"AmapEnabled": b"1", "AmapNaviUdpPort": b"7707"}

  def get_bool(self, key):
    return self._store.get(key, b"0") == b"1"

  def get(self, key, return_default=False):
    return self._store.get(key, b"")


# Mock heavy openpilot dependencies so these unit tests can run without a full
# SCons build / native libraries.
_common_pkg = types.ModuleType("openpilot.common")
_common_pkg.params = MagicMock(Params=_FakeParams)
_common_pkg.realtime = MagicMock(Ratekeeper=MagicMock, config_realtime_process=MagicMock())
_common_pkg.swaglog = MagicMock(cloudlog=MagicMock())
sys.modules["openpilot.common"] = _common_pkg
sys.modules["openpilot.common.params"] = _common_pkg.params
sys.modules["openpilot.common.realtime"] = _common_pkg.realtime
sys.modules["openpilot.common.swaglog"] = _common_pkg.swaglog

_cereal_pkg = types.ModuleType("openpilot.cereal")
_cereal_pkg.messaging = _FakeMessaging
sys.modules["openpilot.cereal"] = _cereal_pkg
sys.modules["openpilot.cereal.messaging"] = _FakeMessaging

from openpilot.sunnypilot.mapd.amap.mapd_amap import AmapNaviServer


class TestAmapNaviServer(unittest.TestCase):
  def setUp(self):
    self.server = AmapNaviServer()

  def test_parse_valid_json_packet(self):
    payload = json.dumps({"leftBlind": 1, "rightBlind": 0}).encode("utf-8")
    assert self.server._parse_packet(payload) == {"leftBlind": 1, "rightBlind": 0}

  def test_parse_invalid_packet_returns_none(self):
    assert self.server._parse_packet(b"not-json") is None
    assert self.server._parse_packet(b"[]") is None

  def test_update_state_applies_fields(self):
    packet = {
      "leftBlind": 1,
      "rightBlind": 2,
      "lineValid": True,
      "leftLine": 3,
      "rightLine": 4,
    }
    self.server._update_state(packet, time.monotonic())
    assert self.server._state["leftBlind"] == 1
    assert self.server._state["rightBlind"] == 2
    assert self.server._state["lineValid"] is True
    assert self.server._state["leftLine"] == 3
    assert self.server._state["rightLine"] == 4

  def test_update_state_ignores_unknown_keys(self):
    before = dict(self.server._state)
    self.server._update_state({"unknown": 123}, time.monotonic())
    assert self.server._state == before

  def test_update_state_coerces_types(self):
    packet = {"leftBlind": 1.9, "lineValid": 1}
    self.server._update_state(packet, time.monotonic())
    assert self.server._state["leftBlind"] == 1
    assert self.server._state["lineValid"] is True

  def test_out_of_order_sequence_is_ignored(self):
    now = time.monotonic()
    self.server._update_state({"seq": 10, "leftBlind": 1}, now)
    self.server._update_state({"seq": 5, "leftBlind": 2}, now + 0.1)
    assert self.server._state["leftBlind"] == 1

  def test_state_expires_after_timeout(self):
    now = time.monotonic()
    self.server._update_state({"leftBlind": 1}, now)
    self.server._maybe_expire_state(now + 10.0)
    assert self.server._state["leftBlind"] == 0
    assert self.server._state["lineValid"] is False

  def test_publish_sends_amapnavisp(self):
    self.server._state = {"leftBlind": 1, "rightBlind": 0, "lineValid": True, "leftLine": 2, "rightLine": 3}
    self.server._publish()
    self.server.pm.send.assert_called_once()
    args = self.server.pm.send.call_args[0]
    assert args[0] == "amapNaviSP"
    assert args[1].amapNaviSP.leftBlind == 1
    assert args[1].amapNaviSP.lineValid is True


if __name__ == "__main__":
  unittest.main()
