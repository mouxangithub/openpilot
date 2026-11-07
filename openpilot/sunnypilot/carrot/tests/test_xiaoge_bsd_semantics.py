"""cp c6566c65a sync: classifier decode, dual-side gate, per-side freshness.

Covers the semantics imported from CarrotPilot's ONNX BSD classifier upgrade:
strict predictions[1] decoding, EMA smoothing with threshold-relative
hysteresis, the dual-side continuous gate (no lane-change direction, no speed
gate), and per-side blind-spot freshness on the payload path.
"""
import json
import sys
import threading
import types
import unittest

import numpy as np


def setUpModule():
  """Bare-PC doubles for the v_asm_server import chain (msgq/capnp/cv2/PIL)."""
  import platform
  fake_ipc = types.ModuleType("msgq.ipc_pyx")
  for name in ("Context", "Poller", "SubSocket", "PubSocket", "SocketEventHandle"):
    setattr(fake_ipc, name, type(name, (), {}))
  fake_ipc.MultiplePublishersError = type("MultiplePublishersError", (Exception,), {})
  fake_ipc.IpcError = type("IpcError", (Exception,), {})
  for name in ("toggle_fake_events", "set_fake_prefix", "get_fake_prefix", "delete_fake_prefix",
               "wait_for_one_event", "fake_event_handle", "drain_sock_raw", "tuple_of_ints"):
    setattr(fake_ipc, name, lambda *a, **k: None)
  sys.modules.setdefault("msgq.ipc_pyx", fake_ipc)
  fake_cv2 = types.SimpleNamespace(
    dnn=types.SimpleNamespace(DNN_BACKEND_OPENCV=5, DNN_TARGET_CPU=0, readNetFromONNX=lambda p: None),
    error=RuntimeError)
  for name in ("setNumThreads", "cvtColor", "resize", "rotate", "imencode", "imdecode"):
    setattr(fake_cv2, name, lambda *a, **k: None)
  sys.modules.setdefault("cv2", fake_cv2)
  for name in ("PIL", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont"):
    sys.modules.setdefault(name, types.ModuleType(name))
  # Windows pycapnp aborts the whole process (KJ fatal, no Python exception)
  # while parsing the full openpilot schemas, so importing openpilot.cereal is
  # not survivable here. Stub capnp with a permissive dummy: these tests never
  # touch real capnp objects, they exercise plain-Python logic on __new__
  # instances. posix (the device) keeps the real capnp.
  if platform.system() == "Windows" and "openpilot.cereal" not in sys.modules:
    class _Meta(type):
      def __getattr__(cls, name):
        return _CapnpDummy
    class _CapnpDummy(BaseException, metaclass=_Meta):
      def __init__(self, *args, **kwargs):
        pass
      def __getattr__(self, name):
        return _CapnpDummy
    class _FakeModule(types.ModuleType):
      def __getattr__(self, name):
        return _CapnpDummy
    sys.modules["capnp"] = _FakeModule("capnp")
    sys.modules["capnp.lib"] = _FakeModule("capnp.lib")
    sys.modules["capnp.lib.capnp"] = _FakeModule("capnp.lib.capnp")


from openpilot.sunnypilot.carrot.xiaoge.v_asm_inference import (
  HYSTERESIS_GAP,
  MODEL_INPUT_SIZE,
  VASMInference,
)
from openpilot.sunnypilot.carrot.xiaoge.xiaoge_vision import (
  XIAOGE_BLINDSPOT_TIMEOUT_NS,
  XiaogeVisionResult,
  apply_xiaoge_vision_result_to_cs,
  parse_xiaoge_vision_payload,
  xiaoge_blindspot_vision,
)


class _FakeNet:
  def __init__(self, output):
    self.output = output
    self.last_blob = None

  def setInput(self, blob):
    self.last_blob = blob

  def forward(self):
    return self.output


def _install_fake_cv2():
  """Minimal cv2 double: pass-through colour ops, shape-aware resize."""
  def resize(img, dsize, interpolation=None):
    return np.zeros((dsize[1], dsize[0], 3), dtype=np.uint8)

  fake = types.SimpleNamespace(
    dnn=types.SimpleNamespace(DNN_BACKEND_OPENCV=5, DNN_TARGET_CPU=0, readNetFromONNX=lambda p: None),
    error=RuntimeError,
    COLOR_YUV2RGB_NV12=100,
    INTER_LINEAR=1,
    cvtColor=lambda *a, **k: np.zeros((4, 4, 3), dtype=np.uint8),
    bitwise_and=lambda rgb, rgb2, mask=None: rgb,
    resize=resize,
  )
  original = sys.modules.get("cv2")
  sys.modules["cv2"] = fake
  import openpilot.sunnypilot.carrot.xiaoge.v_asm_inference as mod
  mod.cv2 = fake
  mod.CV2_ERROR = RuntimeError
  return mod, original


class TestClassifierDecode(unittest.TestCase):
  def setUp(self):
    self.mod, self.original = _install_fake_cv2()

  def tearDown(self):
    if self.original is not None:
      sys.modules["cv2"] = self.original
      self.mod.cv2 = self.original
    else:
      sys.modules.pop("cv2", None)
      self.mod.cv2 = None

  def _inference(self, output):
    inf = VASMInference()
    inf.bboxes["left"] = (0, 0, 4, 4)
    inf.masks["left"] = np.ones((4, 4), dtype=np.uint8)
    inf.net = _FakeNet(output)
    return inf

  def test_reads_blindspot_class_index(self):
    inf = self._inference(np.array([0.10, 0.93, 0.20]))
    self.assertAlmostEqual(inf._confidence(np.zeros((12, 4), np.uint8), 8, "left"), 0.93)

  def test_two_output_model_supported(self):
    inf = self._inference(np.array([0.05, 0.87]))
    self.assertAlmostEqual(inf._confidence(np.zeros((12, 4), np.uint8), 8, "left"), 0.87)

  def test_detector_output_raises_instead_of_decoding_garbage(self):
    # The retired (N,6) detection output must fail loudly, not decode as BSD.
    inf = self._inference(np.array([[0.1, 0.2, 0.3, 0.4, 0.9, 0.0], [0.1, 0.2, 0.3, 0.4, 0.8, 0.0]]))
    with self.assertRaises(ValueError):
      inf._confidence(np.zeros((12, 4), np.uint8), 8, "left")

  def test_letterbox_blob_is_square(self):
    inf = self._inference(np.array([0.1, 0.9]))
    inf._confidence(np.zeros((12, 4), np.uint8), 8, "left")
    blob = inf.net.last_blob
    self.assertEqual(blob.shape, (1, 3, MODEL_INPUT_SIZE, MODEL_INPUT_SIZE))

  def test_ema_smoothing_and_relative_hysteresis(self):
    inf = VASMInference()
    inf._confidence = lambda *a, **k: 0.95  # above any sane threshold
    for _ in range(50):
      inf.update(None, 0, 0, "left", threshold=0.94, smoothing_seconds=0.2, dt=0.05)
    self.assertTrue(inf.active["left"])
    # Drop to just below threshold but above threshold-gap: stays latched.
    inf._confidence = lambda *a, **k: 0.90
    for _ in range(50):
      inf.update(None, 0, 0, "left", threshold=0.94, smoothing_seconds=0.2, dt=0.05)
    self.assertTrue(inf.active["left"])
    # Below threshold - gap: unlatches.
    inf._confidence = lambda *a, **k: 0.5
    for _ in range(200):
      inf.update(None, 0, 0, "left", threshold=0.94, smoothing_seconds=0.2, dt=0.05)
    self.assertFalse(inf.active["left"])

  def test_gap_constant_matches_cp(self):
    self.assertEqual(HYSTERESIS_GAP, 0.15)


BASE = {
  "type": "xiaogeVision",
  "version": 1,
  "lane": {"leftLine": 0, "rightLine": 1, "valid": True, "receivedMonoTimeNanos": 100},
  "blindspot": {"left": True, "right": False, "valid": True, "receivedMonoTimeNanos": 100},
}


class TestPerSideFreshness(unittest.TestCase):
  def test_by_side_map_parsed(self):
    payload = dict(BASE, blindspot={"left": True, "right": False, "valid": True,
                                    "receivedMonoTimeNanos": 100,
                                    "receivedMonoTimeNanosBySide": {"left": 900, "right": 0}})
    r = parse_xiaoge_vision_payload(json.dumps(payload).encode())
    self.assertEqual(r.left_blindspot_received_nanos, 900)
    self.assertEqual(r.right_blindspot_received_nanos, 0)

  def test_missing_map_falls_back_to_shared_nanos(self):
    r = parse_xiaoge_vision_payload(json.dumps(BASE).encode())
    self.assertEqual(r.left_blindspot_received_nanos, 100)
    self.assertEqual(r.right_blindspot_received_nanos, 100)

  def test_malformed_map_rejected(self):
    payload = dict(BASE, blindspot={"left": True, "right": False, "valid": True,
                                    "receivedMonoTimeNanos": 100,
                                    "receivedMonoTimeNanosBySide": []})
    with self.assertRaises(ValueError):
      parse_xiaoge_vision_payload(json.dumps(payload).encode())

  def test_fresh_side_only_reported(self):
    # left stamped now, right stamped long ago: only left survives.
    now = 1_500_000_500
    r = XiaogeVisionResult(0, 1, True, 100, True, True, True, now - 500,
                           left_blindspot_received_nanos=now - 500,
                           right_blindspot_received_nanos=10)
    left, right = xiaoge_blindspot_vision(r, now)
    self.assertTrue(left)
    self.assertFalse(right)

  def test_stale_shared_timestamp_blocks_both(self):
    r = XiaogeVisionResult(0, 1, True, 100, True, True, True, 1_000)
    left, right = xiaoge_blindspot_vision(r, 1_000 + XIAOGE_BLINDSPOT_TIMEOUT_NS + 1)
    self.assertFalse(left)
    self.assertFalse(right)

  def test_apply_writes_only_fresh_sides(self):
    class CS:
      leftBlindspot = False
      rightBlindspot = False
    now = 1_500_000_500
    r = XiaogeVisionResult(0, 1, True, 100, True, True, True, now - 500,
                           left_blindspot_received_nanos=now - 500,
                           right_blindspot_received_nanos=10)
    cs = CS()
    self.assertTrue(apply_xiaoge_vision_result_to_cs(cs, r, now))
    self.assertTrue(cs.leftBlindspot)
    self.assertFalse(cs.rightBlindspot)


class _FakeMeta:
  def __init__(self, left, right):
    self.laneWidthLeft = left
    self.laneWidthRight = right


class _FakeSm:
  def __init__(self, left, right):
    self._meta = _FakeMeta(left, right)

  def update(self, timeout):
    pass

  def all_alive(self, services):
    return True

  def all_valid(self, services):
    return True

  def __getitem__(self, name):
    return types.SimpleNamespace(meta=self._meta)


def _bare_gate_service(left, right, configured=("left", "right"), next_side="left"):
  from openpilot.sunnypilot.carrot.xiaoge.v_asm_server import VASMService
  svc = VASMService.__new__(VASMService)
  svc.lock = threading.Lock()
  svc.sm = _FakeSm(left, right)
  svc.next_side = next_side
  svc.inference = types.SimpleNamespace(configured_sides=tuple(configured))
  svc.vasm_gate = {}
  return svc


class TestDualSideGate(unittest.TestCase):
  def test_both_sides_eligible_no_speed_gate(self):
    svc = _bare_gate_service(2.5, 2.4)
    eligible = svc._update_vasm_gate()
    self.assertEqual(eligible, ("left", "right"))
    self.assertTrue(svc.vasm_gate["active"])
    self.assertEqual(svc.vasm_gate["side"], "left")
    self.assertEqual(svc.vasm_gate["eligibleSides"], ["left", "right"])

  def test_narrow_side_excluded(self):
    svc = _bare_gate_service(2.5, 1.9)
    eligible = svc._update_vasm_gate()
    self.assertEqual(eligible, ("left",))
    self.assertEqual(svc.vasm_gate["laneWidths"]["right"], 1.9)

  def test_width_threshold_is_two_meters(self):
    self.assertEqual(_bare_gate_service(2.0, 1.99)._update_vasm_gate(), ("left",))

  def test_unconfigured_side_excluded(self):
    svc = _bare_gate_service(3.0, 3.0, configured=("left",))
    self.assertEqual(svc._update_vasm_gate(), ("left",))

  def test_next_side_preferred_for_rotation(self):
    svc = _bare_gate_service(3.0, 3.0, next_side="right")
    eligible = svc._update_vasm_gate()
    self.assertEqual(eligible, ("left", "right"))
    self.assertEqual(svc.vasm_gate["side"], "right")

  def test_no_eligible_side_reason(self):
    svc = _bare_gate_service(1.0, 1.0)
    self.assertEqual(svc._update_vasm_gate(), ())
    self.assertEqual(svc.vasm_gate["reason"], "configured lane widths below 2.0 m")


if __name__ == "__main__":
  unittest.main()
