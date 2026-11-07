"""Offline accuracy check for the traffic-light YOLOv8 detector.

Runs the exported ONNX graph over a labelled YOLO-format dataset and reports
per-class precision/recall/mAP plus the confusion between the detector's
housing/lamp output and the annotations. No car connection, no messaging, no
Params and no control outputs.

python tools/signal_analysis/eval_signal_yolo.py DATASET_DIR [--model PATH] [--split val]

DATASET_DIR holds ``data.yaml`` and ``images/{train,val}`` and
``labels/{train,val}`` in the standard YOLO layout.
"""
import argparse
import json
from collections import Counter
from pathlib import Path
import sys

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from openpilot.sunnypilot.carrot.signal_yolo_detector import (  # noqa: E402
  CLASSES, GREEN, HOUSING, RED, YELLOW, detect, group_housings,
)


def read_labels(path):
  """Read one YOLO label file into (class_id, x1, y1, x2, y2) pixel boxes."""
  rows = []
  for line in path.read_text().strip().split('\n'):
    if not line.strip():
      continue
    parts = line.split()
    class_id = int(parts[0])
    x, y, w, h = (float(v) for v in parts[1:5])
    rows.append((class_id, x - w / 2, y - h / 2, x + w / 2, y + h / 2))
  return rows


def iou(a, b):
  ix = min(a[2], b[2]) - max(a[0], b[0])
  iy = min(a[3], b[3]) - max(a[1], b[1])
  if ix <= 0 or iy <= 0:
    return 0.
  inter = ix * iy
  union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
  return inter / union if union > 0 else 0.


def match(predictions, annotations, threshold=.3):
  """Greedy IoU matching per class. Returns (tp, fp, fn) counts."""
  tp = fp = fn = 0
  for class_id in set(p[0] for p in predictions) | set(a[0] for a in annotations):
    preds = sorted((p for p in predictions if p[0] == class_id), key=lambda p: -p[3])
    gts = [a for a in annotations if a[0] == class_id]
    used = set()
    for pred in preds:
      best, best_iou = None, threshold
      for index, gt in enumerate(gts):
        if index in used:
          continue
        score = iou(pred[1:], gt[1:])
        if score >= best_iou:
          best, best_iou = index, score
      if best is None:
        fp += 1
      else:
        used.add(best)
        tp += 1
    fn += len(gts) - len(used)
  return tp, fp, fn


def average_precision(predictions, annotations, threshold=.3):
  """Area under the precision/recall curve from the ranked predictions."""
  by_class = {}
  for class_id in set(p[0] for p in predictions) | set(a[0] for a in annotations):
    preds = sorted((p for p in predictions if p[0] == class_id), key=lambda p: -p[3])
    gts = [a for a in annotations if a[0] == class_id]
    used = set()
    tp_curve, fp_curve = [], []
    for pred in preds:
      best, best_iou = None, threshold
      for index, gt in enumerate(gts):
        if index in used:
          continue
        score = iou(pred[1:], gt[1:])
        if score >= best_iou:
          best, best_iou = index, score
      if best is None:
        tp_curve.append(0)
        fp_curve.append(1)
      else:
        used.add(best)
        tp_curve.append(1)
        fp_curve.append(0)
    if not gts:
      by_class[class_id] = 0.
      continue
    tp_c = np.cumsum(tp_curve)
    fp_c = np.cumsum(fp_curve)
    recalls = tp_c / len(gts)
    precisions = tp_c / np.maximum(tp_c + fp_c, 1e-9)
    # 101-point interpolated AP, the same convention ultralytics reports.
    ap = 0.
    for recall in np.linspace(0, 1, 101):
      masked = precisions[recalls >= recall]
      ap += float(masked.max()) if masked.size else 0.
    by_class[class_id] = ap / 101.
  return by_class


def evaluate(dataset, model_path, split='val', limit=None):
  import cv2
  from PIL import Image
  from openpilot.sunnypilot.carrot.signal_yolo_detector import Detection, decode_output, resize_params, INPUT_SIZE

  net = cv2.dnn.readNetFromONNX(str(model_path))
  images = sorted((dataset / 'images' / split).glob('*.jpg'))
  if limit:
    images = images[:limit]
  annotations_all, predictions_all = [], []
  per_image = []
  for image_path in images:
    label_path = dataset / 'labels' / split / (image_path.stem + '.txt')
    if not label_path.is_file():
      continue
    rgb = np.asarray(Image.open(image_path).convert('RGB'))
    height, width = rgb.shape[:2]
    left, top, net_w, net_h = resize_params(width, height)
    canvas = np.full((INPUT_SIZE, INPUT_SIZE, 3), 114, np.uint8)
    canvas[top:top + net_h, left:left + net_w] = cv2.resize(rgb, (net_w, net_h), interpolation=cv2.INTER_LINEAR)
    blob = cv2.dnn.blobFromImage(canvas, 1 / 255., (INPUT_SIZE, INPUT_SIZE), swapRB=False, crop=False)
    net.setInput(blob)
    output = net.forward()
    detections = decode_output(output, left=left, top=top, net_w=net_w, net_h=net_h,
                               source_w=width, source_h=height)
    annotations = read_labels(label_path)
    # Annotations are normalized to the image, detections are in pixels.
    scaled = [(c, x1 * width, y1 * height, x2 * width, y2 * height) for c, x1, y1, x2, y2 in annotations]
    predictions = [(CLASSES.index(d.cls), d.box[0], d.box[1], d.box[2], d.box[3], d.conf) for d in detections]
    annotations_all += [(c, x1, y1, x2, y2) for c, x1, y1, x2, y2 in scaled]
    predictions_all += predictions
    per_image.append((image_path.stem, scaled, detections))

  classes = sorted(set(a[0] for a in annotations_all) | set(p[0] for p in predictions_all))
  tp, fp, fn = match(predictions_all, annotations_all)
  precision = tp / max(1, tp + fp)
  recall = tp / max(1, tp + fn)
  aps = average_precision(predictions_all, annotations_all)
  per_class = {}
  for class_id in classes:
    ctp, cfp, cfn = match([p for p in predictions_all if p[0] == class_id],
                           [a for a in annotations_all if a[0] == class_id])
    per_class[CLASSES[class_id]] = {
      'instances': sum(1 for a in annotations_all if a[0] == class_id),
      'precision': round(ctp / max(1, ctp + cfp), 4),
      'recall': round(ctp / max(1, ctp + cfn), 4),
      'ap50': round(aps.get(class_id, 0.), 4),
    }
  return {
    'model': str(model_path),
    'split': split,
    'images': len(per_image),
    'overall': {
      'precision': round(precision, 4),
      'recall': round(recall, 4),
      'f1': round(2 * precision * recall / max(1e-9, precision + recall), 4),
      'map50': round(float(np.mean(list(aps.values()))), 4) if aps else 0.,
      'tp': tp, 'fp': fp, 'fn': fn,
    },
    'per_class': per_class,
    '_per_image': per_image,
  }


def lamp_state_report(result):
  """How often the grouped housing/lamps carry a usable colour.

  This is the number that matters downstream: a housing whose lamps disagree
  stays 'unknown', so it can never be read as a red or a green.
  """
  counts = Counter()
  for _, _, detections in result.pop('_per_image', []):
    for observation in group_housings(detections):
      counts[observation.state] += 1
  return dict(counts)


# Which annotation class carries an action colour. Yellow and the turn arrows
# are not action colours: a housing that shows only a yellow lamp is 'unknown',
# never a red and never a green. The keys are the dataset's integer class ids.
ANNOTATION_STATE = {
  CLASSES.index(RED): 'red',
  CLASSES.index(GREEN): 'green',
}


def inside_fraction(inner, outer):
  """Fraction of the ``inner`` box that lies inside the ``outer`` box."""
  ix = min(inner[2], outer[2]) - max(inner[0], outer[0])
  iy = min(inner[3], outer[3]) - max(inner[1], outer[1])
  if ix <= 0 or iy <= 0:
    return 0.
  area = max(0., inner[2] - inner[0]) * max(0., inner[3] - inner[1])
  return (ix * iy) / area if area > 0 else 0.


def state_report(per_image):
  """Housing-level colour agreement with the annotations.

  For every annotated housing, the predicted housing that overlaps it most is
  taken as the detector's answer for that housing, and its colour state is
  compared with the colour the annotation implies. A housing whose annotation
  implies 'unknown' (a yellow lamp, or no lamp at all) is excluded from the
  red/green agreement, but a detector that claims a colour for it is counted
  as a false colour, because claiming 'red' for a yellow signal is exactly the
  mistake this pipeline must not make.
  """
  agreed = Counter()
  false_colour = Counter()
  missed = 0
  for _, annotations, detections in per_image:
    observations = group_housings(detections)
    housings = [a[1:] for a in annotations if a[0] == CLASSES.index(HOUSING)]
    lamps = [a for a in annotations if a[0] != CLASSES.index(HOUSING)]
    for box in housings:
      # A lamp belongs to the housing that contains it, not the one it merely
      # overlaps: a lamp is much smaller than its housing, so overlap ratio is
      # the wrong measure here.
      inside = [a for a in lamps if inside_fraction(a[1:], box) >= .55]
      states = {ANNOTATION_STATE[a[0]] for a in inside if a[0] in ANNOTATION_STATE}
      # A housing with a red and a yellow lamp is still red: yellow is not an
      # action colour. A housing with a red and a green lamp disagrees and
      # stays unknown, on both sides of the comparison.
      expected = states.pop() if len(states) == 1 else 'unknown'
      best, best_iou = None, .3
      for observation in observations:
        score = iou(box, observation.box)
        if score > best_iou:
          best, best_iou = observation, score
      if best is None:
        missed += 1
        continue
      if expected == 'unknown':
        if best.state != 'unknown':
          false_colour[f'claimed_{best.state}_for_{expected}'] += 1
        else:
          agreed['unknown'] += 1
      elif best.state == expected:
        agreed[expected] += 1
      else:
        false_colour[f'{best.state}_instead_of_{expected}'] += 1
  total = sum(agreed.values()) + sum(false_colour.values()) + missed
  correct = sum(agreed.values())
  return {
    'housings': total,
    'agreed': dict(agreed),
    'wrong': dict(false_colour),
    'missed_housing': missed,
    'state_accuracy': round(correct / total, 4) if total else 0.,
  }


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('dataset', type=Path)
  parser.add_argument('--model', type=Path,
                      default=REPO_ROOT / 'openpilot/sunnypilot/assets/vision_models/signal_light_detector.onnx')
  parser.add_argument('--split', default='val')
  parser.add_argument('--limit', type=int)
  parser.add_argument('--json', type=Path)
  args = parser.parse_args()
  result = evaluate(args.dataset, args.model, args.split, args.limit)
  per_image = result.pop('_per_image')
  result['lamp_states'] = lamp_state_report(dict(_per_image=per_image))
  result['housing_states'] = state_report(per_image)
  print(json.dumps(result, indent=2))
  if args.json:
    args.json.write_text(json.dumps(result, indent=2))


if __name__ == '__main__':
  main()
