#!/usr/bin/env python3
"""
End-to-end tests for the ADAS lane-line UDP listener embedded in
``sunnypilot/carrot/carrot_man.py`` (single-producer model).

These tests run WITHOUT cereal/gen on a stock Windows workstation: all
``openpilot.*`` dependencies are stubbed before the real source files are
loaded via importlib.  A real UDP socket pair verifies the full wiring:

  bind (AmapNaviUdpPort) -> send JSON packet -> _drain_adas_packets()
  -> AmapNaviServ.update_adas() -> SharedData adas_* fields

Coverage:
  * _ensure_amap_socket binds and reuses the socket; port 0 stays disabled;
  * a valid ADAS JSON packet lands in SharedData;
  * a malformed packet is dropped without raising and without corrupting state;
  * _close_amap_socket releases the port (rebind by another process works).
"""
import importlib.util
import json
import pathlib
import socket
import sys
import time
import types
import unittest

_CARROT_DIR = pathlib.Path(r"E:/sp/openpilot/sunnypilot/carrot")

# --- 1. stub the openpilot package tree (no cereal/pycapnp needed) ---------
op = types.ModuleType("openpilot")
op.__path__ = []
op_common = types.ModuleType("openpilot.common")
op_common.__path__ = []
op_cereal = types.ModuleType("op_cereal")  # placeholder, replaced below
op_cereal_pkg = types.ModuleType("openpilot.cereal")
op_cereal_pkg.__path__ = []
op_messaging = types.ModuleType("openpilot.cereal.messaging")
op_messaging.__path__ = []
op_messaging.SubMaster = lambda services: types.SimpleNamespace(update=lambda t: None, alive={}, updated={})
op_messaging.PubMaster = lambda socks: types.SimpleNamespace(send=lambda *a, **k: None)

rt = types.ModuleType("openpilot.common.realtime")
rt.DT_MDL = 0.05
rt.Ratekeeper = lambda *a, **k: types.SimpleNamespace(keep_time=lambda: True)
rt.config_realtime_process = lambda *a, **k: None

swaglog = types.ModuleType("openpilot.common.swaglog")
swaglog.cloudlog = types.SimpleNamespace(info=lambda *a, **k: None, error=lambda *a, **k: None,
                                         warning=lambda *a, **k: None)

class _FakeParams:
  def __init__(self):
    self._d = {}
  def get(self, k, block=False, return_default=False):
    return self._d.get(k)
  def get_bool(self, k, block=False):
    v = self._d.get(k)
    return bool(int(v)) if v is not None else False
  def get_int(self, k):
    v = self._d.get(k)
    return int(v) if v is not None else 0
  def get_float(self, k):
    v = self._d.get(k)
    return float(v) if v is not None else 0.0
  def put(self, k, v, block=False):
    self._d[k] = v

params_mod = types.ModuleType("openpilot.common.params")
params_mod.Params = _FakeParams

sp = types.ModuleType("openpilot.sunnypilot")
sp.__path__ = []
carrot_pkg = types.ModuleType("openpilot.sunnypilot.carrot")
carrot_pkg.__path__ = []

# --- 2. stub cereal.messaging for amap_navi's own import ------------------
cereal = types.ModuleType("cereal")
cereal.__path__ = []
cereal_messaging = types.ModuleType("cereal.messaging")
cereal_messaging.__path__ = []
cereal_messaging.new_message = lambda name: None

# --- 3. config stub (UnifiedParams) ----------------------------------------
cfg = types.ModuleType("openpilot.sunnypilot.carrot.config")
class _UnifiedParams:
  def __init__(self):
    self.p = _FakeParams()
  def get(self, k, d=None):
    v = self.p.get(k)
    return v if v is not None else d
  def get_int(self, k, d=0):
    v = self.p.get(k)
    return int(v) if v is not None else d
  def get_float(self, k, d=0.0):
    v = self.p.get(k)
    return float(v) if v is not None else d
  def get_bool(self, k, d=False):
    v = self.p.get(k)
    return bool(int(v)) if v is not None else d
cfg.UnifiedParams = _UnifiedParams

sys.modules.update({
  "openpilot": op, "openpilot.common": op_common,
  "openpilot.common.realtime": rt, "openpilot.common.swaglog": swaglog,
  "openpilot.common.params": params_mod,
  "openpilot.cereal": op_cereal_pkg, "openpilot.cereal.messaging": op_messaging,
  "cereal": cereal, "cereal.messaging": cereal_messaging,
  "openpilot.sunnypilot": sp, "openpilot.sunnypilot.carrot": carrot_pkg,
  "openpilot.sunnypilot.carrot.config": cfg,
})

def _load_real(name: str, path: pathlib.Path):
  spec = importlib.util.spec_from_file_location(name, path)
  mod = importlib.util.module_from_spec(spec)
  sys.modules[name] = mod
  spec.loader.exec_module(mod)
  return mod

# --- 4. load real source files (amap_navi -> carrot_serv -> carrot_man) ---
amap_navi = _load_real("openpilot.sunnypilot.carrot.amap_navi", _CARROT_DIR / "amap_navi.py")
carrot_serv = _load_real("openpilot.sunnypilot.carrot.carrot_serv", _CARROT_DIR / "carrot_serv.py")
carrot_man_mod = _load_real("openpilot.sunnypilot.carrot.carrot_man", _CARROT_DIR / "carrot_man.py")
CarrotManager = carrot_man_mod.CarrotManager


def _free_port() -> int:
  s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  s.bind(('127.0.0.1', 0))
  port = s.getsockname()[1]
  s.close()
  return port


def _send_udp(port: int, payload: bytes):
  with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
    sock.sendto(payload, ('127.0.0.1', port))
  time.sleep(0.05)  # let the loopback packet land in the receive buffer


class TestAdasSocketWiring(unittest.TestCase):

  def setUp(self):
    self.mgr = CarrotManager()

  def tearDown(self):
    self.mgr._close_amap_socket()

  def test_port_zero_stays_disabled(self):
    self.assertFalse(self.mgr._ensure_amap_socket(0))
    self.assertIsNone(self.mgr._amap_sock)

  def test_bind_and_ingest_valid_packet(self):
    port = _free_port()
    self.assertTrue(self.mgr._ensure_amap_socket(port))
    self.assertIsNotNone(self.mgr._amap_sock)
    _send_udp(port, json.dumps({"lineValid": True, "leftLine": 2, "rightLine": 1}).encode())
    self.mgr._drain_adas_packets()
    sd = self.mgr._amap_navi.shared_data
    self.assertTrue(sd.adas_line_valid)
    self.assertEqual(sd.adas_left_line, 2)
    self.assertEqual(sd.adas_right_line, 1)

  def test_bind_is_idempotent_on_same_port(self):
    port = _free_port()
    self.assertTrue(self.mgr._ensure_amap_socket(port))
    sock_before = self.mgr._amap_sock
    self.assertTrue(self.mgr._ensure_amap_socket(port))
    self.assertIs(self.mgr._amap_sock, sock_before)  # no churn on re-tick

  def test_malformed_packet_dropped_without_raising(self):
    port = _free_port()
    self.assertTrue(self.mgr._ensure_amap_socket(port))
    _send_udp(port, b"this is not json \xff\xfe")
    self.mgr._drain_adas_packets()  # must not raise
    sd = self.mgr._amap_navi.shared_data
    self.assertFalse(sd.adas_line_valid)
    self.assertEqual(sd.adas_left_line, 0)

  def test_line_invalid_packet_zeroes_lanes(self):
    port = _free_port()
    self.assertTrue(self.mgr._ensure_amap_socket(port))
    _send_udp(port, json.dumps({"lineValid": True, "leftLine": 3, "rightLine": 3}).encode())
    self.mgr._drain_adas_packets()
    _send_udp(port, json.dumps({"lineValid": False, "leftLine": 0, "rightLine": 0}).encode())
    self.mgr._drain_adas_packets()
    sd = self.mgr._amap_navi.shared_data
    self.assertFalse(sd.adas_line_valid)
    self.assertEqual(sd.adas_left_line, 0)

  def test_close_releases_port(self):
    port = _free_port()
    self.assertTrue(self.mgr._ensure_amap_socket(port))
    self.mgr._close_amap_socket()
    self.assertIsNone(self.mgr._amap_sock)
    # another socket must be able to bind the same port now
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s2:
      s2.bind(('127.0.0.1', port))  # no OSError => port released

  def test_blindspot_state_untouched_by_adas_packets(self):
    # ADAS packets must never overwrite Carrot-protocol blind-spot bits.
    port = _free_port()
    self.assertTrue(self.mgr._ensure_amap_socket(port))
    self.mgr._amap_navi.shared_data.left_blind = True
    self.mgr._amap_navi.shared_data.lidar_left_blind = True
    _send_udp(port, json.dumps({"lineValid": True, "leftLine": 1, "rightLine": 1,
                                "leftBlind": 0, "rightBlind": 0}).encode())
    self.mgr._drain_adas_packets()
    sd = self.mgr._amap_navi.shared_data
    self.assertTrue(sd.left_blind)       # preserved
    self.assertTrue(sd.lidar_left_blind)  # preserved
    self.assertTrue(sd.adas_line_valid)   # lane-line ingested


class TestBroadcastPortAdvertisement(unittest.TestCase):
  """Broadcast must advertise the port we actually listen on
  (CarrotManUdpPort), not the legacy hard-coded 7706."""

  def setUp(self):
    self.mgr = CarrotManager()
    self.mgr.sm.alive = {"carState": False}
    self.mgr._carrot_serv = types.SimpleNamespace(
      x_dist_to_turn=0, x_spd_dist=0, n_road_limit_speed=0,
      v_turn_speed=0, traffic_state=0)

  def _msg(self):
    return json.loads(self.mgr.make_send_message())

  def test_advertises_actual_listen_port(self):
    self.mgr._port = 7716
    self.assertEqual(self._msg()["port"], 7716)

  def test_falls_back_to_legacy_7706_when_unbound(self):
    self.mgr._port = 0
    self.mgr._port_advertise_warned = False
    self.assertEqual(self._msg()["port"], 7706)
    self.assertTrue(self.mgr._port_advertise_warned)  # one-shot warning armed

  def test_repeated_fallback_does_not_raise(self):
    self.mgr._port = 0
    self.mgr._port_advertise_warned = False
    first = self._msg()
    second = self._msg()
    self.assertEqual(first["port"], second["port"])  # stable, no exception


if __name__ == "__main__":
  unittest.main()
