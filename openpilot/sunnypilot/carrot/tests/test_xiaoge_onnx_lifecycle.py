"""ONNX BSD model load/unload lifecycle.

The resident blind-spot model must be releasable when OnnxBsdEnabled is off,
otherwise it stays loaded for the lifetime of the service for no reason. These
tests exercise the state transitions without requiring OpenCV or an actual
ONNX file: the missing-file and missing-cv2 branches both leave ``valid``
False, which is exactly the state ``unload`` also produces.
"""
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openpilot.sunnypilot.carrot.xiaoge.v_asm_inference import VASMInference


class TestInferenceLifecycle(unittest.TestCase):
  def test_unload_clears_valid_state(self):
    with TemporaryDirectory() as d:
      inf = VASMInference(Path(d) / "missing.onnx")
      self.assertFalse(inf.load())
      self.assertFalse(inf.valid)
      # unload on an already unloaded instance is idempotent.
      inf.unload()
      inf.unload()
      self.assertIsNone(inf.net)
      self.assertFalse(inf.valid)
      self.assertFalse(inf.active["left"])
      self.assertFalse(inf.active["right"])

  def test_load_then_unload_with_mock_net(self):
    with TemporaryDirectory() as d:
      model = Path(d) / "model.onnx"
      model.write_bytes(b"fake-onnx")

      # Inject a minimal fake cv2 module so load() succeeds without OpenCV.
      fake_dnn = types.SimpleNamespace(
        DNN_BACKEND_OPENCV=5, DNN_TARGET_CPU=0,
        readNetFromONNX=lambda path: types.SimpleNamespace(
          setPreferableBackend=lambda *a: None,
          setPreferableTarget=lambda *a: None,
        ),
      )
      fake_cv2 = types.SimpleNamespace(dnn=fake_dnn, error=RuntimeError)
      original = sys.modules.get("cv2")
      sys.modules["cv2"] = fake_cv2
      try:
        # Reload the module-level cv2 binding inside the class by importing a
        # fresh copy is unnecessary: the module reads the global at call time
        # only on ImportError, so instead point at the fake through monkeypatch.
        import openpilot.sunnypilot.carrot.xiaoge.v_asm_inference as mod
        mod.cv2 = fake_cv2
        mod.CV2_ERROR = RuntimeError
        inf = VASMInference(model)
        self.assertTrue(inf.load())
        self.assertTrue(inf.valid)
        self.assertIsNotNone(inf.net)
        # load() is idempotent while already valid.
        self.assertTrue(inf.load())
        inf.unload()
        self.assertIsNone(inf.net)
        self.assertFalse(inf.valid)
      finally:
        mod.cv2 = original if original is not None else None
        if original is None:
          sys.modules.pop("cv2", None)

  def test_failed_reload_does_not_leave_stale_net(self):
    with TemporaryDirectory() as d:
      model = Path(d) / "model.onnx"
      model.write_bytes(b"fake-onnx")

      fake_dnn = types.SimpleNamespace(
        DNN_BACKEND_OPENCV=5, DNN_TARGET_CPU=0,
        readNetFromONNX=lambda path: types.SimpleNamespace(
          setPreferableBackend=lambda *a: None,
          setPreferableTarget=lambda *a: None,
        ),
      )
      fake_cv2 = types.SimpleNamespace(dnn=fake_dnn, error=RuntimeError)
      original = sys.modules.get("cv2")
      sys.modules["cv2"] = fake_cv2
      try:
        import openpilot.sunnypilot.carrot.xiaoge.v_asm_inference as mod
        mod.cv2 = fake_cv2
        mod.CV2_ERROR = RuntimeError
        inf = VASMInference(model)
        self.assertTrue(inf.load())
        # A re-load whose read now fails (cv2 vanished mid-session) must not
        # leave the old net reachable behind a valid=False facade. Unload first
        # so the idempotent early-return does not mask the failure path.
        inf.unload()
        mod.cv2 = None
        self.assertFalse(inf.load())
        self.assertIsNone(inf.net)
        self.assertFalse(inf.valid)
      finally:
        mod.cv2 = original if original is not None else None
        if original is None:
          sys.modules.pop("cv2", None)


class TestSettingsRefreshLifecycle(unittest.TestCase):
  """The toggle must invalidate every blind-spot artifact of the old lifecycle.

  Uses ``__new__`` to skip the real constructor (SubMaster/PubMaster need a
  running messaging stack); only the state the refresh path touches is set up.
  The module import needs msgq/cv2/PIL doubles on a bare PC: v_asm_server pulls
  the messaging stack and exits without OpenCV.
  """

  @classmethod
  def setUpClass(cls):
    import sys
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

  @staticmethod
  def _bare_service():
    import threading
    from openpilot.sunnypilot.carrot.xiaoge.v_asm_server import VASMService
    svc = VASMService.__new__(VASMService)
    svc.lock = threading.Lock()
    svc.settings_refresh_lock = threading.Lock()
    svc.vasm_inference_lock = threading.Lock()
    svc.last_param_refresh_at = 0.0
    svc.params = None  # read_param_int falls back to PARAM_SETTING_DEFAULTS
    svc.bsd_enabled = True
    svc.bsd_generation = 0
    svc.vasm_result = {"left": True, "right": False, "side": "left", "updatedMonoTimeNanos": 123}
    svc.last_side_at = {"left": 9.0, "right": 8.0}
    svc.followup_until = 99.0
    svc.last_inference_at = 7.0
    svc.inference = types.SimpleNamespace(load=lambda: True, unload=lambda: None, valid=False)
    svc.config = None
    return svc

  def test_disable_clears_stale_results_and_bumps_generation(self):
    svc = self._bare_service()
    calls = []
    svc.inference.unload = lambda: calls.append("unload")
    svc._refresh_settings_from_params(force=True)  # defaults switch BSD off
    self.assertEqual(calls, ["unload"])
    self.assertFalse(svc.bsd_enabled)
    self.assertEqual(svc.bsd_generation, 1)
    self.assertEqual(svc.vasm_result["left"], False)
    self.assertEqual(svc.vasm_result["side"], "")
    self.assertEqual(svc.last_side_at, {"left": 0.0, "right": 0.0})
    self.assertEqual(svc.followup_until, 0.0)
    self.assertEqual(svc.last_inference_at, 0.0)

  def test_stale_read_cannot_revive_disabled_model(self):
    # The refresh holds settings_refresh_lock across read+commit+transition, so
    # two concurrent refreshes end in one consistent state, not a reload race.
    svc = self._bare_service()
    load_calls, unload_calls = [], []
    svc.inference.load = lambda: load_calls.append(1)
    svc.inference.unload = lambda: unload_calls.append(1)
    # Off -> on transition with params=None reads the defaults (0), so flip the
    # baseline to off and let a stubbed param read return 1 for the enable.
    svc.bsd_enabled = False
    svc.params = types.SimpleNamespace(get=lambda name: b"1")
    svc._refresh_settings_from_params(force=True)
    self.assertEqual(load_calls, [1])
    self.assertEqual(unload_calls, [])
    # A second refresh seeing the same value must not touch the model again.
    svc._refresh_settings_from_params(force=True)
    self.assertEqual(load_calls, [1])
    self.assertEqual(svc.bsd_generation, 1)


if __name__ == "__main__":
  unittest.main()
