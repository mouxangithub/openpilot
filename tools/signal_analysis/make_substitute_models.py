"""Build substitute ONNX artifacts matching the neural-signal contract.

The reference detector and classifier are pinned by sha256 inside
NeuralSignal and live nowhere public. To exercise the real inference and
post-processing path on-device, emit two artifacts with the exact input
names, shapes and output ranks the wrapper expects:

  detector   images [1,3,416,416] -> [1,3549,7]
             score = p[:,4]*p[:,6]; boxes decode against a stride grid
  classifier input [1,3,224,224]  -> [1,11]  (one column per label)

Constant outputs are enough: every branch of detect()/classify() after
the session call is real code reading real tensors.
"""
import numpy as np
import onnx
from onnx import helper, TensorProto


STRIDES = (8, 16, 32)
GRID = np.array([(x, y, s) for s in STRIDES for y in range(416 // s) for x in range(416 // s)], np.float32)


def make_detector(path, *, center=(208., 208.), size=24.):
  # stride-8 row: (x=26, y=20) -> center (208, 208)
  n = len(GRID)
  out = np.zeros((1, n, 7), np.float32)
  index = 26 + 20 * 52  # x + y*width inside the stride-8 block
  stride = 8.
  out[0, index, 0:4] = [(center[0] - stride * GRID[index][0]) / stride - 0.0,
                        (center[1] - stride * GRID[index][1]) / stride - 0.0,
                        np.log(size / stride), np.log(size / stride)]
  # cx/cy are (sigmoid) offsets the code adds straight onto the grid
  out[0, index, 0] = 0.5
  out[0, index, 1] = 0.5
  out[0, index, 4] = 0.95   # objectness
  out[0, index, 6] = 0.95   # class score, use the index the score product reads
  graph = helper.make_graph(
    [helper.make_node('Constant', [], ['detections'],
                      value=onnx.numpy_helper.from_array(out, 'value'))],
    'substitute_detector',
    [helper.make_tensor_value_info('images', TensorProto.FLOAT, [1, 3, 416, 416])],
    [helper.make_tensor_value_info('detections', TensorProto.FLOAT, [1, n, 7])])
  model = helper.make_model(graph, opset_imports=[helper.make_opsetid('', 13)])
  model.ir_version = 8
  onnx.save(model, str(path))


def make_classifier(path, label_index=3):
  """label_index 3 is 'red' in NeuralSignal.LABELS."""
  rows = 11
  probs = np.full((1, rows), -8., np.float32)
  probs[0, label_index] = 4.
  graph = helper.make_graph(
    [helper.make_node('Constant', [], ['probs'],
                      value=onnx.numpy_helper.from_array(probs, 'value'))],
    'substitute_classifier',
    [helper.make_tensor_value_info('input', TensorProto.FLOAT, [1, 3, 224, 224])],
    [helper.make_tensor_value_info('probs', TensorProto.FLOAT, [1, rows])])
  model = helper.make_model(graph, opset_imports=[helper.make_opsetid('', 13)])
  model.ir_version = 8
  onnx.save(model, str(path))


if __name__ == '__main__':
  import sys
  make_detector(sys.argv[1])
  make_classifier(sys.argv[2])
  print('wrote', sys.argv[1], sys.argv[2])
