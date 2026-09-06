#!/usr/bin/env python3
"""
Offline unit tests for the ADAS lane-line integration in
``sunnypilot/carrot/amap_navi.py`` introduced during the carrot/mapd merge
(Commit C of the migration plan).

These tests run WITHOUT building cereal/gen (they stub ``cereal.messaging``
before importing the module), so they can be executed on a stock Windows
workstation where scons / pycapnp are unavailable.  They verify:

  * SharedData exposes adas_* fields and reset() clears them;
  * update_adas() ingests + clamps lane-line types and rejects malformed data;
  * build_amap_navi_msg() sources lineValid/leftLine/rightLine from ADAS
    instead of the old hardcoded 0, and fail-safes to lineValid=False when
    ADAS data is stale/absent;
  * the 3-bit blind-spot mask is preserved through the ADAS path.
"""
import importlib.util
import pathlib
import sys
import time
import unittest
from types import ModuleType
from unittest import mock

# Stub cereal so this file can import amap_navi without pycapnp / cereal/gen.
_cereal = ModuleType("cereal")
_cereal.messaging = ModuleType("cereal.messaging")
_cereal.messaging.new_message = lambda name: None
_cereal.__path__ = []
_cereal.messaging.__path__ = []
sys.modules["cereal"] = _cereal
sys.modules["cereal.messaging"] = _cereal.messaging

_SRC = pathlib.Path(r"E:/sp/openpilot/sunnypilot/carrot/amap_navi.py")
_spec = importlib.util.spec_from_file_location("amap_navi_under_test", _SRC)
amap_navi = importlib.util.module_from_spec(_spec)
sys.modules["amap_navi_under_test"] = amap_navi
_spec.loader.exec_module(amap_navi)


class _FakeNavi:
  def __init__(self):
    self.valid = True
    self.leftBlind = 0
    self.rightBlind = 0
    self.lineValid = False
    self.leftLine = 0
    self.rightLine = 0


class _FakeMsg:
  def __init__(self):
    self.amapNaviSP = _FakeNavi()
    self.valid = True


def _fake_new_message(_name):
  return _FakeMsg()


class TestAmapNaviAdas(unittest.TestCase):
  def _serv(self):
    return amap_navi.AmapNaviServ()

  def test_shared_data_exposes_adas_fields(self):
    sd = self._serv().shared_data
    self.assertTrue(hasattr(sd, "adas_line_valid"))
    self.assertTrue(hasattr(sd, "adas_left_line"))
    self.assertTrue(hasattr(sd, "adas_right_line"))
    self.assertTrue(hasattr(sd, "adas_last_mono"))

  def test_reset_clears_adas_fields(self):
    serv = self._serv()
    sd = serv.shared_data
    sd.adas_line_valid = True
    sd.adas_left_line = 5
    sd.adas_right_line = 2
    sd.adas_last_mono = time.monotonic()
    serv.reset()
    self.assertFalse(sd.adas_line_valid)
    self.assertEqual(sd.adas_left_line, 0)
    self.assertEqual(sd.adas_right_line, 0)
    self.assertEqual(sd.adas_last_mono, 0.0)

  def test_update_adas_ingests_valid(self):
    serv = self._serv()
    serv.update_adas({"lineValid": True, "leftLine": 2, "rightLine": 1})
    self.assertTrue(serv.shared_data.adas_line_valid)
    self.assertEqual(serv.shared_data.adas_left_line, 2)
    self.assertEqual(serv.shared_data.adas_right_line, 1)

  def test_update_adas_clamps_out_of_range(self):
    serv = self._serv()
    serv.update_adas({"lineValid": True, "leftLine": 99, "rightLine": -3})
    self.assertEqual(serv.shared_data.adas_left_line, 0)
    self.assertEqual(serv.shared_data.adas_right_line, 0)
    self.assertTrue(serv.shared_data.adas_line_valid)

  def test_update_adas_line_invalid_zeroes(self):
    serv = self._serv()
    serv.update_adas({"lineValid": False, "leftLine": 2, "rightLine": 1})
    self.assertFalse(serv.shared_data.adas_line_valid)
    self.assertEqual(serv.shared_data.adas_left_line, 0)
    self.assertEqual(serv.shared_data.adas_right_line, 0)

  def test_update_adas_rejects_malformed(self):
    serv = self._serv()
    serv.update_adas(None)
    serv.update_adas("not a dict")
    serv.update_adas({"lineValid": True, "leftLine": "boom", "rightLine": "x"})
    self.assertFalse(serv.shared_data.adas_line_valid)

  def test_build_msg_uses_adas_when_fresh(self):
    serv = self._serv()
    serv.update_adas({"lineValid": True, "leftLine": 5, "rightLine": 2})
    serv._last_packet_mono = time.monotonic()
    msg = serv.build_amap_navi_msg(_fake_new_message)
    self.assertTrue(msg.amapNaviSP.lineValid)
    self.assertEqual(msg.amapNaviSP.leftLine, 5)
    self.assertEqual(msg.amapNaviSP.rightLine, 2)

  def test_build_msg_fail_safe_when_adas_expired(self):
    serv = self._serv()
    serv.update_adas({"lineValid": True, "leftLine": 5, "rightLine": 2})
    serv.shared_data.adas_last_mono = 0.0  # simulate expiry
    serv._last_packet_mono = time.monotonic()
    msg = serv.build_amap_navi_msg(_fake_new_message)
    self.assertFalse(msg.amapNaviSP.lineValid)
    self.assertEqual(msg.amapNaviSP.leftLine, 0)
    self.assertEqual(msg.amapNaviSP.rightLine, 0)

  def test_build_msg_preserves_blind_mask(self):
    serv = self._serv()
    sd = serv.shared_data
    sd.left_blind = True
    sd.lidar_car_left_blind = True
    sd.right_blind = True
    serv.update_adas({"lineValid": True, "leftLine": 1, "rightLine": 1})
    serv._last_packet_mono = time.monotonic()
    msg = serv.build_amap_navi_msg(_fake_new_message)
    self.assertEqual(msg.amapNaviSP.leftBlind, 6)   # bit4 + bit2
    self.assertEqual(msg.amapNaviSP.rightBlind, 2)  # bit2


def _params_stub(return_value=None, raise_on_init=False):
  """Build a fake openpilot.common.params module for lazy-import probing."""
  mod = ModuleType("openpilot.common.params")

  class _P:
    def __init__(self):
      if raise_on_init:
        raise RuntimeError("params unavailable")
    def get(self, k, block=False, return_default=False):
      return return_value

  mod.Params = _P
  op = ModuleType("openpilot"); op.__path__ = []
  opc = ModuleType("openpilot.common"); opc.__path__ = []
  return {"openpilot": op, "openpilot.common": opc, "openpilot.common.params": mod}


class TestLiDARListenPortResolution(unittest.TestCase):
  """_resolve_listen_port: explicit arg > LiDARUdpPort param > default 4211."""

  def _serv(self):
    return amap_navi.AmapNaviServ()

  def test_explicit_argument_wins_over_param(self):
    serv = self._serv()
    with mock.patch.dict(sys.modules, _params_stub(return_value="4311")):
      self.assertEqual(serv._resolve_listen_port(5555), 5555)

  def test_param_value_used_when_set(self):
    serv = self._serv()
    with mock.patch.dict(sys.modules, _params_stub(return_value="4311")):
      self.assertEqual(serv._resolve_listen_port(None), 4311)

  def test_falls_back_to_default_when_param_unset(self):
    serv = self._serv()
    with mock.patch.dict(sys.modules, _params_stub(return_value=None)):
      self.assertEqual(serv._resolve_listen_port(None), 4211)

  def test_falls_back_to_default_when_param_zero(self):
    serv = self._serv()
    with mock.patch.dict(sys.modules, _params_stub(return_value="0")):
      self.assertEqual(serv._resolve_listen_port(None), 4211)

  def test_falls_back_to_default_when_params_unavailable(self):
    serv = self._serv()
    with mock.patch.dict(sys.modules, _params_stub(raise_on_init=True)):
      self.assertEqual(serv._resolve_listen_port(None), 4211)

  def test_start_navi_comm_resolves_port_and_starts_four_threads(self):
    serv = self._serv()
    created = []

    class _FakeThread:
      def __init__(self, target=None, daemon=None):
        created.append(target)
        self.daemon = daemon
      def start(self):
        pass

    with mock.patch.object(amap_navi.threading, "Thread", _FakeThread):
      serv.start_navi_comm(7777)
    self.assertEqual(serv._listen_port, 7777)
    self.assertEqual(len(created), 4)


if __name__ == "__main__":
  unittest.main()