"""xiaogeVision payload v1 + optional YOLO section: parse and carStateSP digest.

The version gate stays at 1: the yolo section is an optional key, so payloads
from a YOLO-enabled server parse on old readers and vice versa.
"""
import unittest

from openpilot.sunnypilot.carrot.xiaoge.xiaoge_vision import (
  XIAOGE_YOLO_TIMEOUT_NS,
  XiaogeVisionResult,
  apply_yolo_summary_to_cs_sp,
  parse_xiaoge_vision_payload,
)

BASE = {
  "type": "xiaogeVision",
  "version": 1,
  "lane": {"leftLine": 0, "rightLine": 1, "valid": True, "receivedMonoTimeNanos": 100},
  "blindspot": {"left": False, "right": False, "valid": True, "receivedMonoTimeNanos": 100},
}


def _det(cid=0, d=12.5, **over):
  det = {"tid": 1, "cid": cid, "conf": 0.8, "cx": 0.5, "cy": 0.5, "w": 0.1, "h": 0.2, "d": d, "y": 0.0,
         "pred": [[0.5, 0.5]]}
  det.update(over)
  return det


class TestParseV1Compat(unittest.TestCase):
  def test_v1_payload_without_yolo(self):
    result = parse_xiaoge_vision_payload(__import__("json").dumps(BASE).encode())
    self.assertIsInstance(result, XiaogeVisionResult)
    self.assertIsNone(result.yolo)
    self.assertTrue(result.lane_valid)

  def test_yolo_section_parses(self):
    payload = dict(BASE, yolo={"valid": True, "receivedMonoTimeNanos": 200, "dets": [_det()]})
    result = parse_xiaoge_vision_payload(__import__("json").dumps(payload).encode())
    self.assertIsNotNone(result.yolo)
    self.assertEqual(result.yolo["dets"][0]["cid"], 0)

  def test_malformed_yolo_section_rejected(self):
    for bad in ({"yolo": {"valid": True}}, {"yolo": []},
                {"yolo": {"valid": True, "receivedMonoTimeNanos": 1, "dets": {}}}):
      with self.assertRaises(ValueError):
        parse_xiaoge_vision_payload(__import__("json").dumps(dict(BASE, **bad)).encode())

  def test_version_gate_unchanged(self):
    with self.assertRaises(ValueError):
      parse_xiaoge_vision_payload(__import__("json").dumps(dict(BASE, version=2)).encode())


class _FakeCS_SP:
  def __init__(self):
    self.yoloVruPresent = False
    self.yoloVruNearestDist = 0.0
    self.yoloVruBlockLeft = False
    self.yoloVruBlockRight = False
    self.yoloVruMonoTimeNanos = 0


class TestYoloSummary(unittest.TestCase):
  def _result(self, dets, received=1_000_000):
    yolo = {"valid": True, "receivedMonoTimeNanos": received, "dets": dets}
    return XiaogeVisionResult(0, 1, True, 100, False, False, True, 100, yolo=yolo)

  def test_nearest_high_risk_distance(self):
    cs = _FakeCS_SP()
    dets = [_det(cid=2, d=8.0), _det(cid=0, d=15.0), _det(cid=0, d=25.0)]
    self.assertTrue(apply_yolo_summary_to_cs_sp(cs, self._result(dets), 2_000_000))
    # car is not VRU; nearest VRU (person) wins
    self.assertTrue(cs.yoloVruPresent)
    self.assertEqual(cs.yoloVruNearestDist, 15.0)
    self.assertEqual(cs.yoloVruMonoTimeNanos, 1_000_000)

  def test_no_vru_writes_invalid_zero(self):
    cs = _FakeCS_SP()
    self.assertTrue(apply_yolo_summary_to_cs_sp(cs, self._result([_det(cid=2, d=8.0)]), 2_000_000))
    self.assertFalse(cs.yoloVruPresent)
    self.assertEqual(cs.yoloVruNearestDist, 0.0)

  def test_stale_payload_not_applied(self):
    cs = _FakeCS_SP()
    # age ~3 s > the 1.5 s window
    self.assertFalse(apply_yolo_summary_to_cs_sp(cs, self._result([_det()], received=10), 3_000_000_000))
    self.assertFalse(cs.yoloVruPresent)
    self.assertEqual(cs.yoloVruNearestDist, 0.0)

  def test_block_flags_stay_false_until_gate(self):
    cs = _FakeCS_SP()
    apply_yolo_summary_to_cs_sp(cs, self._result([_det(cid=0, d=5.0)]), 2_000_000)
    self.assertFalse(cs.yoloVruBlockLeft)
    self.assertFalse(cs.yoloVruBlockRight)

  def test_timeout_constant_covers_low_fps(self):
    # at the target 3-6 fps a 1.5 s window tolerates several missed frames
    self.assertEqual(XIAOGE_YOLO_TIMEOUT_NS, 1_500_000_000)


if __name__ == "__main__":
  unittest.main()
