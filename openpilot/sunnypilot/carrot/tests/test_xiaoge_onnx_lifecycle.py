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


if __name__ == "__main__":
  unittest.main()
