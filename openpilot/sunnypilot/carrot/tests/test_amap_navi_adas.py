#!/usr/bin/env python3
"""
Offline unit tests for ``sunnypilot/carrot/amap_navi.py``.

These tests run WITHOUT building cereal/gen (they stub ``cereal.messaging``
before importing the module), so they can be executed on a stock Windows
workstation where scons / pycapnp are unavailable.  They verify:

  * ``build_amap_navi_msg()`` keeps the 3-bit blind-spot mask correct and
    now publishes lane-line fields as permanently invalid (the Amap ADAS
    JSON lane-line source was retired);
  * the LiDAR/camera direct-UDP listen port resolution logic (used by the
    dormant ``start_navi_comm`` path).
"""
import importlib.util
import pathlib
import sys
import time
import unittest
from types import ModuleType
from unittest import mock

# Stub the openpilot / cereal trees so this file can import amap_navi without
# pycapnp / cereal/gen (which cannot be built on a stock Windows workstation).
_op = ModuleType("openpilot")
_op.__path__ = []
sys.modules["openpilot"] = _op

_oc = ModuleType("openpilot.cereal")
_oc.__path__ = []
sys.modules["openpilot.cereal"] = _oc

_ocm = ModuleType("openpilot.cereal.messaging")
_ocm.new_message = lambda name: None
_ocm.SubMaster = lambda services: None
_ocm.PubMaster = lambda socks: None
sys.modules["openpilot.cereal.messaging"] = _ocm

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


class TestAmapNaviBlindSpotMask(unittest.TestCase):
  """build_amap_navi_msg must preserve the 3-bit blind-spot mask and now
  publish lane-line fields as permanently invalid (no ADAS JSON source)."""

  def _serv(self):
    return amap_navi.AmapNaviServ()

  def test_build_msg_preserves_blind_mask_and_invalidates_lanes(self):
    serv = self._serv()
    sd = serv.shared_data
    sd.left_blind = True
    sd.lidar_car_left_blind = True
    sd.right_blind = True
    serv._last_packet_mono = time.monotonic()
    msg = serv.build_amap_navi_msg(_fake_new_message)
    # bit4 (lidar-car) + bit2 (Carrot) => 6 ; bit2 => 2
    self.assertEqual(msg.amapNaviSP.leftBlind, 6)
    self.assertEqual(msg.amapNaviSP.rightBlind, 2)
    # Lane-line source retired: always invalid/zero now.
    self.assertFalse(msg.amapNaviSP.lineValid)
    self.assertEqual(msg.amapNaviSP.leftLine, 0)
    self.assertEqual(msg.amapNaviSP.rightLine, 0)


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
