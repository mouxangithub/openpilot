"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of zoompilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

jetlink's numpy history buffers must produce exactly what openpilot's tinygrad
ones do.

img_q / big_img_q / feat_q / desire_q are reimplemented in numpy on the Jetson,
and drift means the model silently sees the wrong history. Compared against
compile_modeld's own functions over a run long enough for every ring to wrap
twice. Here rather than in jetlink, whose CI has no openpilot to compare with.
"""
from __future__ import annotations

import math
import unittest

import numpy as np
from tinygrad.tensor import Tensor

from jetlink.queues import PolicyQueues
from jetlink.spec import ModelSpec

from openpilot.common.test import OpenpilotTestCase
from openpilot.selfdrive.modeld import compile_modeld

# The big (chestnut) model, as shipped: 4-D features_buffer, 33-step desire.
BIG_SHAPES = {
  'img': (1, 12, 128, 256),
  'big_img': (1, 12, 128, 256),
  'desire_pulse': (1, 33, 8),
  'traffic_convention': (1, 2),
  'action_t': (1, 2),
  'features_buffer': (1, 32, 32, 512),
}
SMALL_SHAPES = {
  'img': (1, 12, 128, 256),
  'big_img': (1, 12, 128, 256),
  'desire_pulse': (1, 25, 8),
  'traffic_convention': (1, 2),
  'action_t': (1, 2),
  'features_buffer': (1, 24, 512),
}


def make_spec(shapes, frame_skip=4) -> ModelSpec:
  # the hidden state is the features queue's row, as the model returns it
  feat = math.prod(shapes['features_buffer'][2:])
  return ModelSpec(sha256='0' * 64, nbytes=0, frame_skip=frame_skip,
                   input_shapes=shapes, output_shapes={'outputs': (1, 2066 + feat + 2)},
                   output_slices={'hidden_state': slice(2066, 2066 + feat)}, checkpoint=None)


class TinygradReference:
  """openpilot's queues, driven exactly as run_policy drives them."""

  def __init__(self, spec: ModelSpec):
    fs = spec.frame_skip
    fb = spec.input_shapes['features_buffer']
    dp = spec.input_shapes['desire_pulse']
    img = spec.input_shapes['img']
    self.fs = fs

    # derived from openpilot's own formulae (get_policy_npy_shapes) rather than
    # jetlink's properties, so this is an independent reference
    feat_dim = math.prod(fb[2:])
    assert feat_dim == spec.feat_dim, f"spec.feat_dim {spec.feat_dim} != openpilot's {feat_dim}"
    n_frames = img[1] // 6
    img_buf_shape = (fs * (n_frames - 1) + 1, 6, img[2], img[3])
    assert img_buf_shape == spec.img_buf_shape

    self.img_q = Tensor(np.zeros(img_buf_shape, np.uint8)).contiguous().realize()
    self.big_img_q = Tensor(np.zeros(img_buf_shape, np.uint8)).contiguous().realize()
    self.feat_q = Tensor(np.zeros((fs * fb[1], fb[0], feat_dim), np.float32)).contiguous().realize()
    self.desire_q = Tensor(np.zeros((fs * dp[1], dp[0], dp[2]), np.float32)).contiguous().realize()

  def step(self, warped: np.ndarray, desire: np.ndarray, prev_feat: np.ndarray):
    w = Tensor(warped)
    img = compile_modeld.shift_and_sample(self.img_q, w[0:1], lambda b: compile_modeld.sample_skip(b, self.fs))
    big = compile_modeld.shift_and_sample(self.big_img_q, w[1:2], lambda b: compile_modeld.sample_skip(b, self.fs))
    des = compile_modeld.shift_and_sample(self.desire_q, Tensor(desire).reshape(1, 1, -1),
                                          lambda b: compile_modeld.sample_desire(b, self.fs))
    feat = compile_modeld.shift_and_sample(self.feat_q, Tensor(prev_feat).reshape(1, 1, -1),
                                           lambda b: compile_modeld.sample_skip(b, self.fs))
    return (img.numpy(), big.numpy(), des.numpy(), feat.numpy())


class TestPolicyQueues(OpenpilotTestCase):
  def test_matches_openpilot(self):
    for shapes, name in ((BIG_SHAPES, 'big'), (SMALL_SHAPES, 'small')):
      with self.subTest(name):
        spec = make_spec(shapes)
        # float32 queues so this compares representation as well as ordering; the
        # server runs float16, which only changes the cast point, not the values.
        ours = PolicyQueues(spec, dtype=np.float32)
        ref = TinygradReference(spec)
        rng = np.random.default_rng(0)

        # modeld's prev_feat: zero at the start, then each frame's hidden state.
        # jetlink keeps it on the Jetson and feeds it back there.
        prev_feat = np.zeros(spec.prev_feat_shape, np.float32)
        # Long enough for every ring (the longest is desire_q at frame_skip*33=132)
        # to wrap more than once.
        for i in range(300):
          warped = rng.integers(0, 256, spec.warped_shape, dtype=np.uint8)
          desire = (rng.random(spec.packed_shapes['desire']) > 0.8).astype(np.float32)
          packed = np.concatenate([
            desire.ravel(),
            rng.standard_normal(2).astype(np.float32),
            rng.standard_normal(2).astype(np.float32),
          ])

          got = ours.step(warped, packed)
          want_img, want_big, want_des, want_feat = ref.step(warped, desire, prev_feat)

          self.assertTrue(np.array_equal(got['img'].reshape(want_img.shape), want_img), f'{name} img @{i}')
          self.assertTrue(np.array_equal(got['big_img'].reshape(want_big.shape), want_big), f'{name} big_img @{i}')
          self.assertTrue(np.array_equal(got['desire_pulse'].reshape(want_des.shape), want_des), f'{name} desire @{i}')
          self.assertTrue(np.array_equal(got['features_buffer'].reshape(want_feat.shape), want_feat), f'{name} feat @{i}')

          # what the model returned this frame: its hidden state is next frame's prev_feat
          output = rng.standard_normal(spec.output_nelem).astype(np.float32)
          ours.after_run({'outputs': output}, {})
          prev_feat = output[spec.output_slices['hidden_state']].reshape(spec.prev_feat_shape)

  def test_reset_returns_to_initial_state(self):
    spec = make_spec(BIG_SHAPES)
    q = PolicyQueues(spec, dtype=np.float32)
    rng = np.random.default_rng(1)
    for _ in range(10):
      q.step(rng.integers(0, 256, spec.warped_shape, dtype=np.uint8),
             rng.standard_normal(spec.packed_nelem).astype(np.float32))
    q.reset()

    fresh = PolicyQueues(spec, dtype=np.float32)
    warped = np.zeros(spec.warped_shape, np.uint8)
    packed = np.zeros(spec.packed_nelem, np.float32)
    a, b = q.step(warped, packed), fresh.step(warped, packed)
    for k in a:
      self.assertTrue(np.array_equal(a[k], b[k]), k)

  def test_sampling_picks_oldest_first(self):
    """sample_skip must return history in order, oldest first, newest last."""
    spec = make_spec(BIG_SHAPES)
    q = PolicyQueues(spec, dtype=np.float32)
    # img_q holds frame_skip*(n_frames-1)+1 = 5 rows; sampling every 4 gives rows 0 and 4.
    for v in range(1, 8):
      warped = np.full(spec.warped_shape, v, np.uint8)
      out = q.step(warped, np.zeros(spec.packed_nelem, np.float32))
    img = out['img'].reshape(spec.img_shape)
    oldest, newest = img[0, 0, 0, 0], img[0, 6, 0, 0]
    self.assertEqual(newest, 7, 'newest should be the frame just pushed')
    self.assertEqual(oldest, 3, 'oldest should be 4 frames back')


if __name__ == '__main__':
  unittest.main()
