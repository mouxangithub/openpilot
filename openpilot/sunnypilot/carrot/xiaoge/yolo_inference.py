"""YOLOv8n-192 object-detection head for the xiaoge vision server.

Logic-only port of Z6's bypass ``yolo_hint_server.py`` (Detector / Tracker /
monocular distance); the display, JPEG and font plumbing stay behind. The
detector runs on the road-camera NV12 **Y plane** - letterboxed and replicated
to three channels - instead of a full-size NV12→BGR conversion, which Z6
measured at ~100 ms a frame.

Focal length comes from the constructor: the caller derives it from
``openpilot.common.transformations.camera`` (C3 road camera ``ox03c10`` maps to
``_ar_ox_config``, focal 2648 px at 1928x1208 - numerically identical to Z6's
hardcoded ``_ar_ox_config`` value, so the port changes nothing for distance).
The distance estimate is a coarse gating number (±30% is normal), never a
braking-distance input.

Grayscale note: Y-only drops chroma, which costs a little detection accuracy
versus full BGR but keeps the head inside the road thread's frame budget
alongside lane segmentation.
"""
import collections

try:
  import cv2
  CV2_ERROR = cv2.error
except ImportError:
  cv2 = None
  CV2_ERROR = RuntimeError

import numpy as np
from pathlib import Path

DEFAULT_YOLO_MODEL_PATH = Path(__file__).parent / "assets" / "yolov8n_192.onnx"
DEFAULT_INPUT_SIZE = 192
NMS_THRESHOLD = 0.45
DEFAULT_CONFIDENCE = 0.35

# COCO classes worth painting or gating on; everything else is dropped so the
# payload stays small and the HUD stays quiet.
KEEP_CLASSES = {
  0: ("person",), 1: ("bicycle",), 2: ("car",), 3: ("motorcycle",),
  5: ("bus",), 7: ("truck",), 9: ("traffic light",), 11: ("stop sign",),
  13: ("cone",), 16: ("dog",), 17: ("horse",),
}
# People and two-wheelers: the driving model cannot see them reliably.
HIGH_RISK_CLASSES = {0, 1, 3, 16, 17}
# Naturally slow/static classes (people, bikes, animals, cones) versus vehicles,
# which need ego speed to tell "parked" from "being followed". The gate (M5)
# treats these differently; the detector only labels them.
VRU_CLASSES = {0, 1, 3, 13, 16, 17}
VEHICLE_CLASSES = {2, 5, 7}

# Real-world heights (metres) for the monocular distance estimate. Only classes
# in this table get a distance; adding a class affects distance only, never
# gating membership.
REAL_HEIGHT_M = {
  0: 1.70, 1: 1.70, 2: 1.50, 3: 1.65, 5: 3.10, 7: 3.30, 16: 0.60, 17: 1.60,
}

DEFAULT_FOCAL_PX = 2648.0    # camera.py _ar_ox_config, C3 road camera
DEFAULT_WIDTH_PX = 1928
DEFAULT_HEIGHT_PX = 1208


def estimate_distance(class_id: int, height_norm: float, focal_px: float, height_px: int) -> float | None:
  """distance = focal * real height / pixel height. Metres, or None.

  Coarse by design (±30%): good enough to gate a lane change, never to compute
  a braking distance.
  """
  real_h = REAL_HEIGHT_M.get(class_id)
  if real_h is None or height_norm is None or height_norm <= 1e-4:
    return None
  h_px = height_norm * height_px
  if h_px <= 2.0:
    return None
  d = focal_px * real_h / h_px
  return round(d, 1) if 1.0 < d < 200.0 else None


def estimate_lateral(cx_norm: float, width_norm: float, focal_px: float,
                     width_px: int, distance: float | None) -> float | None:
  """Lateral offset in metres from the image centre; positive = right."""
  if distance is None or width_norm <= 0:
    return None
  dx_px = (cx_norm - width_norm / 2.0) / width_norm * width_px
  return round(dx_px * distance / focal_px, 2)


def _iou(a, b) -> float:
  ax1, ax2 = a[0] - a[2] * 0.5, a[0] + a[2] * 0.5
  ay1, ay2 = a[1] - a[3] * 0.5, a[1] + a[3] * 0.5
  bx1, bx2 = b[0] - b[2] * 0.5, b[0] + b[2] * 0.5
  by1, by2 = b[1] - b[3] * 0.5, b[1] + b[3] * 0.5
  iw = min(ax2, bx2) - max(ax1, bx1)
  ih = min(ay2, by2) - max(ay1, by1)
  if iw <= 0.0 or ih <= 0.0:
    return 0.0
  union = a[2] * a[3] + b[2] * b[3] - iw * ih
  return iw * ih / union if union > 0.0 else 0.0


class Track:
  """One trajectory: box centre + size in normalised coordinates."""

  __slots__ = ("tid", "cid", "conf", "box", "hist", "miss", "vx", "vy", "t", "age", "d", "y")

  def __init__(self, tid: int, det: dict, now: float):
    self.tid = tid
    self.cid = det["cid"]
    self.conf = det["conf"]
    self.box = (det["cx"], det["cy"], det["w"], det["h"])
    self.d = det.get("d")
    self.y = det.get("y")
    # ~2 s of history at the target 3-6 fps; the HUD tail needs only a few points.
    self.hist = collections.deque(maxlen=12)
    self.hist.append((now, det["cx"], det["cy"]))
    self.miss = 0
    self.vx = 0.0
    self.vy = 0.0
    self.t = now
    self.age = 0

  def predicted_box(self, now: float):
    dt = max(0.0, min(now - self.t, 0.5))
    return (self.box[0] + self.vx * dt, self.box[1] + self.vy * dt, self.box[2], self.box[3])


class Tracker:
  """Greedy IoU matching + alpha-beta filtering. Pure kinematics, <1 ms/frame.

  Deliberately not DeepSORT/ByteTrack: those need a ReID network, tens of extra
  milliseconds per frame on the C3 - not realistic next to lane inference.
  Normalised coordinates throughout, matching the detector output.
  """

  IOU_MIN = 0.15
  MAX_MISS = 4
  MAX_SPEED = 3.0   # normalised units/second; above this the match is bogus
  ALPHA = 0.6
  BETA = 0.25

  def __init__(self):
    self.tracks: dict[int, Track] = {}
    self.next_id = 1

  def reset(self) -> None:
    """Drop every track: called when the YOLO toggle flips or the model reloads,
    so a stale id never survives a lifecycle change."""
    self.tracks.clear()

  def update(self, dets: list[dict], now: float) -> dict[int, Track]:
    pairs = []
    for tid, tr in self.tracks.items():
      pbox = tr.predicted_box(now)
      for j, d in enumerate(dets):
        if d["cid"] != tr.cid:  # class must match, else a person rides a car
          continue
        iou = _iou(pbox, (d["cx"], d["cy"], d["w"], d["h"]))
        if iou >= self.IOU_MIN:
          pairs.append((iou, tid, j))
    pairs.sort(reverse=True)

    used_t: set[int] = set()
    used_d: set[int] = set()
    for _, tid, j in pairs:
      if tid in used_t or j in used_d:
        continue
      used_t.add(tid)
      used_d.add(j)
      tr = self.tracks[tid]
      d = dets[j]
      dt = max(1e-3, min(now - tr.t, 0.5))

      px, py, _, _ = tr.predicted_box(now)
      rx, ry = d["cx"] - px, d["cy"] - py
      nx, ny = px + self.ALPHA * rx, py + self.ALPHA * ry
      nvx = tr.vx + self.BETA * rx / dt
      nvy = tr.vy + self.BETA * ry / dt
      if abs(nvx) > self.MAX_SPEED or abs(nvy) > self.MAX_SPEED:
        nvx, nvy = tr.vx, tr.vy
        nx, ny = d["cx"], d["cy"]

      tr.vx, tr.vy = nvx, nvy
      tr.box = (nx, ny, d["w"], d["h"])
      tr.conf = d["conf"]
      tr.d = d.get("d")
      tr.y = d.get("y")
      tr.miss = 0
      tr.t = now
      tr.age += 1
      tr.hist.append((now, nx, ny))

    for tid in list(self.tracks.keys()):
      if tid in used_t:
        continue
      tr = self.tracks[tid]
      tr.miss += 1
      tr.t = now
      if tr.miss > self.MAX_MISS:
        del self.tracks[tid]

    for j, d in enumerate(dets):
      if j in used_d:
        continue
      self.tracks[self.next_id] = Track(self.next_id, d, now)
      self.next_id = self.next_id % 9999 + 1

    return self.tracks

  def predict(self, tr: Track, horizon: float = 0.8, steps: int = 4) -> list[tuple[float, float]]:
    """Extrapolate along current velocity; normalised points."""
    return [(tr.box[0] + tr.vx * horizon * i / steps,
             tr.box[1] + tr.vy * horizon * i / steps) for i in range(1, steps + 1)]


class YoloInference:
  """cv2.dnn wrapper around the yolov8n-192 ONNX. Grayscale (Y-plane) input."""

  def __init__(self, model_path: Path = DEFAULT_YOLO_MODEL_PATH, input_size: int = DEFAULT_INPUT_SIZE,
               focal_px: float = DEFAULT_FOCAL_PX, width_px: int = DEFAULT_WIDTH_PX,
               height_px: int = DEFAULT_HEIGHT_PX):
    self.model_path = Path(model_path)
    self.input_size = input_size
    self.focal_px = focal_px
    self.width_px = width_px
    self.height_px = height_px
    self.net = None
    self.valid = False
    self.error = "not loaded"
    # Letterbox canvas is preallocated and reused; the visible region is only
    # reset when the input aspect changes (Z6's residual-ghost bug, see load).
    self._canvas: np.ndarray | None = None
    self._lb_key = None
    self._roi: np.ndarray | None = None
    self._nh = self._nw = 0
    self._top = self._left = 0
    self.latency_ms = 0.0

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
    # Pre-clear before the read: a failed re-load must not leave the previous
    # net reachable behind a valid=False facade.
    self.net = None
    self.valid = False
    try:
      self.net = cv2.dnn.readNetFromONNX(str(self.model_path))
      self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
      self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
    except CV2_ERROR as error:
      self.error = f"could not load model: {error}"
      return False
    self.valid = True
    self.error = ""
    return True

  def unload(self) -> None:
    """Release the net; ``load`` re-reads the file on the next enable."""
    self.net = None
    self.valid = False
    self.error = "unloaded"

  def _letterbox_params(self, h: int, w: int):
    """Recompute letterbox geometry only when the input size changes.

    The canvas is reused across frames; when the visible region shrinks the
    previous frame would linger in the grey border and the model would see a
    collage of two frames, randomly breaking detection. Hence the full reset.
    """
    key = (h, w)
    if key != self._lb_key:
      r = min(self.input_size / h, self.input_size / w)
      self._nh, self._nw = int(round(h * r)), int(round(w * r))
      self._top, self._left = (self.input_size - self._nh) // 2, (self.input_size - self._nw) // 2
      self._canvas = np.full((self.input_size, self.input_size), 114, dtype=np.uint8)
      self._roi = self._canvas[self._top:self._top + self._nh, self._left:self._left + self._nw]
      self._lb_key = key
    return self._nh, self._nw

  def infer(self, y_plane: np.ndarray, width: int, height: int,
            conf_threshold: float = DEFAULT_CONFIDENCE) -> list[dict]:
    """Detect on a cropped NV12 Y plane. Returns normalised detections:
    ``{cid, conf, cx, cy, w, h, d, y}`` - centre/size in 0-1 image coords,
    ``d`` coarse metres (None when the class has no height model), ``y``
    lateral metres from centre (None when ``d`` is None)."""
    if not self.valid or cv2 is None:
      return []
    if y_plane.ndim != 2 or y_plane.shape[0] < height or y_plane.shape[1] < width:
      return []
    import time
    t0 = time.perf_counter()
    gray = y_plane[:height, :width]

    nh, nw = self._letterbox_params(height, width)
    cv2.resize(gray, (nw, nh), dst=self._roi, interpolation=cv2.INTER_LINEAR)
    three = cv2.merge((self._canvas, self._canvas, self._canvas))
    blob = cv2.dnn.blobFromImage(three, 1 / 255.0, (self.input_size, self.input_size),
                                 swapRB=True, crop=False)
    self.net.setInput(blob)
    out = self.net.forward()
    t1 = time.perf_counter()
    self.latency_ms = (t1 - t0) * 1000.0

    pred = out[0].T  # (N, 4+nc)
    cls_conf = pred[:, 4:]
    cls_ids = cls_conf.argmax(1)
    confs = cls_conf.max(1)

    dets = []
    keep = confs > conf_threshold
    if keep.any():
      idx = np.nonzero(keep)[0]
      boxes = pred[idx, :4]
      xy = np.concatenate([boxes[:, :2] - boxes[:, 2:] / 2, boxes[:, 2:]], axis=1)
      picked = cv2.dnn.NMSBoxes(xy.tolist(), confs[idx].tolist(), conf_threshold, NMS_THRESHOLD)
      if len(picked):
        for i in np.array(picked).flatten():
          cid = int(cls_ids[idx[i]])
          if cid not in KEEP_CLASSES:
            continue
          cx, cy, bw, bh = (float(v) for v in boxes[i])
          # Back-map model coords to the full frame, normalised to 0-1: subtract
          # the letterbox origin first, then divide by the visible region size.
          cx_n, cy_n = (cx - self._left) / self._nw, (cy - self._top) / self._nh
          w_n, h_n = bw / self._nw, bh / self._nh
          d = estimate_distance(cid, h_n, self.focal_px, self.height_px)
          dets.append({
            "cid": cid,
            "conf": round(float(confs[idx[i]]), 2),
            "cx": round(cx_n, 4),
            "cy": round(cy_n, 4),
            "w": round(w_n, 4),
            "h": round(h_n, 4),
            "d": d,
            "y": estimate_lateral(cx_n, self._nw, self.focal_px, self.width_px, d),
          })
    return dets
