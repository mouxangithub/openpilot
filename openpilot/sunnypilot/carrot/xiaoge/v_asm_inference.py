"""V-ASM blind-spot detection ONNX inference engine.

Ported from CarrotPilot (cp):
  selfdrive/carrot/xiaoge/v_asm_inference.py

Model generation: cp c6566c65a (2026-10-07) swapped the 256x352 (N,6) YOLO
detector for a three-class 352x352 classifier (md5 6b2b2f4d, 6166229 bytes).
This engine now letterboxes into a square and reads predictions[1] strictly;
the old detector output would raise ValueError instead of decoding garbage.

Requirements: opencv-python-headless >= 4.10.0, numpy >= 1.24
"""
from pathlib import Path
import numpy as np

try:
  import cv2
  CV2_ERROR = cv2.error
except ImportError:
  cv2 = None
  CV2_ERROR = Exception

MODEL_INPUT_SIZE = 352
HYSTERESIS_GAP = 0.15
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
DEFAULT_MODEL_PATH = ASSETS_DIR / "v_asm_model.onnx"


class VASMInference:
  def __init__(self, model_path: Path = DEFAULT_MODEL_PATH):
    self.model_path = model_path
    self.net = None
    self.valid = False
    self.error = ""
    self.frame_size = (0, 0)
    self.config_size = (0, 0)
    self.raw_polygons = {"left": None, "right": None}
    self.bboxes = {"left": None, "right": None}
    self.masks = {"left": None, "right": None}
    self.reset()

  def load(self) -> bool:
    if self.valid and self.net is not None:
      return True
    if not self.model_path.is_file():
      self.error = f"model missing: {self.model_path}"
      self.valid = False
      return False
    if cv2 is None:
      self.error = "OpenCV (cv2) is missing - install opencv-python-headless"
      self.valid = False
      return False
    # Drop any previous net before attempting the read: a failed re-load must
    # not leave the old (possibly stale or freed) net reference behind.
    self.net = None
    self.valid = False
    try:
      self.net = cv2.dnn.readNetFromONNX(str(self.model_path))
      self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
      self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
    except CV2_ERROR as error:
      self.error = f"could not load model: {error}"
      self.valid = False
      return False
    self.valid = True
    self.error = ""
    return True

  def unload(self) -> None:
    """Release the ONNX net and clear detection state.

    Lets the OnnxBsdEnabled switch free the resident model when BSD is off;
    ``load`` re-reads the file on the next enable. Idempotent: an already
    unloaded instance stays unloaded.
    """
    self.net = None
    self.valid = False
    self.error = "disabled by OnnxBsdEnabled"
    self.reset()

  def reset(self) -> None:
    self.scores = {"left": 0.0, "right": 0.0}
    self.active = {"left": False, "right": False}
    self.confidence = {"left": 0.0, "right": 0.0}

  @property
  def configured_sides(self) -> tuple[str, ...]:
    return tuple(side for side in ("left", "right") if self.raw_polygons[side] is not None)

  def load_config(self, config: dict) -> None:
    self.reset()
    self.frame_size = (0, 0)
    self.config_size = (int(config["width"]), int(config["height"]))
    for side in ("left", "right"):
      polygon = config.get(f"poly_{side}", [])
      self.raw_polygons[side] = np.array(polygon, dtype=np.float32) if len(polygon) >= 3 else None
      self.bboxes[side] = None
      self.masks[side] = None

  def _prepare_geometry(self, height: int, width: int) -> None:
    if self.frame_size == (height, width):
      return
    self.frame_size = (height, width)
    config_width, config_height = self.config_size
    scale_x = width / config_width
    scale_y = height / config_height
    for side in ("left", "right"):
      raw_polygon = self.raw_polygons[side]
      if raw_polygon is None:
        continue
      polygon = raw_polygon.copy()
      polygon[:, 0] *= scale_x
      polygon[:, 1] *= scale_y
      x, y, crop_w, crop_h = cv2.boundingRect(polygon.astype(np.int32))
      x = max(0, min((x // 2) * 2, width - 2))
      y = max(0, min((y // 2) * 2, height - 2))
      crop_w = max(2, min(((crop_w + 1) // 2) * 2, width - x))
      crop_h = max(2, min(((crop_h + 1) // 2) * 2, height - y))
      crop_w = (crop_w // 2) * 2
      crop_h = (crop_h // 2) * 2
      self.bboxes[side] = (x, y, crop_w, crop_h)
      mask = np.zeros((crop_h, crop_w), dtype=np.uint8)
      cv2.fillPoly(mask, [polygon.astype(np.int32) - [x, y]], 255)
      self.masks[side] = mask

  def _confidence(self, nv12: np.ndarray, frame_height: int, side: str) -> float:
    bbox = self.bboxes[side]
    if bbox is None or self.net is None:
      return 0.0
    x, y, crop_w, crop_h = bbox
    y_crop = nv12[y:y + crop_h, x:x + crop_w]
    uv_crop = nv12[frame_height + y // 2:frame_height + (y + crop_h) // 2, x:x + crop_w]
    rgb = cv2.cvtColor(np.vstack((y_crop, uv_crop)), cv2.COLOR_YUV2RGB_NV12)
    rgb = cv2.bitwise_and(rgb, rgb, mask=self.masks[side])
    # Classifier model (three-class 352x352): letterbox the aspect ratio intact
    # into a square canvas instead of stretching to 256x352 like the retired
    # detector. predictions[1] is the blindspot class; anything else is a
    # model/family mismatch and must fail loudly, not decode garbage.
    height, width = rgb.shape[:2]
    scale = MODEL_INPUT_SIZE / max(height, width)
    resized_width = max(1, round(width * scale))
    resized_height = max(1, round(height * scale))
    resized = cv2.resize(rgb, (resized_width, resized_height), interpolation=cv2.INTER_LINEAR)
    square = np.zeros((MODEL_INPUT_SIZE, MODEL_INPUT_SIZE, 3), dtype=np.uint8)
    top = (MODEL_INPUT_SIZE - resized_height) // 2
    left = (MODEL_INPUT_SIZE - resized_width) // 2
    square[top:top + resized_height, left:left + resized_width] = resized
    blob = np.transpose(square.astype(np.float32) / 255.0, (2, 0, 1))[None, :]
    self.net.setInput(blob)
    predictions = np.squeeze(self.net.forward())
    if predictions.ndim != 1 or predictions.size not in (2, 3):
      raise ValueError(f"unexpected V-ASM model output shape: {predictions.shape}")
    return float(predictions[1])

  def update(self, nv12: np.ndarray, width: int, height: int, side: str,
             threshold: float, smoothing_seconds: float, dt: float) -> None:
    self._prepare_geometry(height, width)
    confidence = self._confidence(nv12, height, side)
    # EMA smoothing: responds within smoothing_seconds but never latches on a
    # single frame the way the old +/- score counter could.
    alpha = min(1.0, dt / max(smoothing_seconds, 0.001))
    self.scores[side] = (1.0 - alpha) * self.scores[side] + alpha * confidence
    self.confidence[side] = confidence
    if not self.active[side] and self.scores[side] >= threshold:
      self.active[side] = True
    elif self.active[side] and self.scores[side] < max(0.0, threshold - HYSTERESIS_GAP):
      self.active[side] = False
