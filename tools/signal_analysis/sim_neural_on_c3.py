"""Run the neural signal chain on the C3 with substitute artifacts.

What here is real, and what is not:

REAL   copy_nv12_crop_rgb NV12 handling, letterboxing to 416, the
       detector tensor layout, session creation, score product, grid
       decode, NMS through overlap(), the 224 classifier crop with
       ImageNet normalisation, label lookup, and NV12 geometry guards.
SUBSTITUTE  the two ONNX weights. The pinned reference models are not
       public, so make_substitute_models emits constant outputs at the
       same contract. Nothing about the wrapper is relaxed except the
       sha256 expectation, which is patched here rather than in the
       product code.

Prints a JSON line per stage so the run can be recomputed and diffed.
"""
import json
import numpy as np

from openpilot.common.repo_tools import load

neural_signal = load('signal_analysis/neural_signal.py')
NeuralSignal = neural_signal.NeuralSignal
copy_nv12_crop_rgb = neural_signal.copy_nv12_crop_rgb


class Frame:
  """The fields copy_nv12_crop_rgb reads off a VisionBuf-like frame."""
  def __init__(self, width, height, stride, uv_offset, data):
    self.width, self.height = width, height
    self.stride, self.uv_offset = stride, uv_offset
    self.data = data


def synthetic_nv12(width=1344, height=760):
  """A grey frame with a red square placed inside the usual search ROI."""
  y = np.full((height, width), 120, np.uint8)
  uv = np.full((height // 2, width), 128, np.uint8)
  cv2 = None
  x1, y1, x2, y2 = 620, 120, 700, 200
  y[y1:y2, x1:x2] = 76                      # Y for a bright red
  uv[y1 // 2:y2 // 2, x1 // 2:x2 // 2] = 90  # crude chroma
  data = np.concatenate((y, uv), axis=0).tobytes()
  return Frame(width, height, width, width * height, data)


def main():
  detector_path, classifier_path = '/data/tmp/sub_detector.onnx', '/data/tmp/sub_classifier.onnx'
  import hashlib
  from pathlib import Path

  def actual(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

  # Patch only the pin, never the wrapper: any model we can run is a stand-in.
  NeuralSignal.DETECTOR_SHA = actual(detector_path)
  NeuralSignal.CLASSIFIER_SHA = actual(classifier_path)

  report = {}

  # 1. NV12 crop with even-aligned geometry
  frame = synthetic_nv12()
  rgb = copy_nv12_crop_rgb(frame, (0, 0, frame.width, frame.height))
  report['nv12_crop'] = dict(shape=list(rgb.shape), dtype=str(rgb.dtype))
  for bad in [(1, 0, 10, 10), (0, 0, 10000, 10), (10, 10, 0, 20)]:
    try:
      copy_nv12_crop_rgb(frame, bad)
      report.setdefault('geometry_guard', []).append([bad, 'accepted'])
    except ValueError as e:
      report.setdefault('geometry_guard', []).append([list(bad), f'rejected: {e}'])

  # 2. Detector session and box decode
  neural = NeuralSignal(detector_path, classifier_path, backend='cpu')
  boxes = neural.detect(rgb)
  report['detect'] = dict(count=len(boxes), boxes=[[round(v, 1) for v in b['box']] + [round(b['score'], 3)]
                                                   for b in boxes])

  # 3. Classifier on a detected box, and on junk geometry
  if boxes:
    report['classify'] = neural.classify(rgb, boxes[0]['box'])
  report['classify_empty'] = neural.classify(rgb, [0, 0, 0, 0])

  # 4. Sequence wrapper: two frames 100 ms apart
  seq = neural_signal.NeuralSignalSequence(neural, period=.2)
  first = seq.process(rgb, 1.0)
  report['sequence_first'] = dict(tracks=len(first['tracks']),
                                  labels=[[t.get('box'), t['label'], round(t['score'], 3)] for t in first['tracks']])
  print(json.dumps(report, indent=2, default=str))


if __name__ == '__main__':
  main()
