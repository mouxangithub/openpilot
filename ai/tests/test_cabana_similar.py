"""Cabana find-similar-bits tool tests (hand-crafted frame sets)."""

from __future__ import annotations

import ai.tests.bootstrap_pc  # noqa: F401  # PC mocks before ai imports
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from ai.services.cabana.handlers import _similar_bits_results


def _f(t: float, bus: int, address: int, data: str) -> dict:
  return {"time": 1000.0 + t, "bus": bus, "address": address, "data": data}


class SimilarBitsTest(unittest.TestCase):
  def test_top_match_sorted_by_ratio(self):
    # Reference: 0x100 at t=1.0, data 0b00001011 (bits 0,1,3 set).
    frames = [
      _f(0.0, 0, 0x100, "00"),
      _f(1.0, 0, 0x100, "0b"),
      # 0x200 always equals the reference bit pattern -> ratio 1.0
      _f(0.5, 0, 0x200, "0b"),
      _f(1.5, 0, 0x200, "0b"),
      # 0x300 is the bitwise complement -> ratio 0.0
      _f(0.5, 0, 0x300, "f4"),
      # 0x400 matches half the time -> 0.5
      _f(0.5, 0, 0x400, "0b"),
      _f(1.5, 0, 0x400, "f4"),
    ]
    results, err = _similar_bits_results(frames, 0x100, 0, 1.0, bytes.fromhex("ff"), 10)
    self.assertIsNone(err)
    ratios = {r["address"]: r["match_ratio"] for r in results}
    self.assertAlmostEqual(ratios[0x200], 1.0)
    self.assertAlmostEqual(ratios[0x400], 0.5)
    self.assertAlmostEqual(ratios[0x300], 0.0)
    ordered = [r["address"] for r in results]
    self.assertEqual(ordered, sorted(ordered, key=lambda a: -ratios[a]))
    self.assertEqual(results[0]["address"], 0x200)
    self.assertNotIn(0x100, ratios)  # reference pair excluded
    self.assertEqual(results[0]["sample_data"], "0b")

  def test_partial_mask_selects_subset(self):
    # mask 0x0f -> only bits 0..3 participate; 0x200 matches on those bits.
    frames = [
      _f(1.0, 0, 0x100, "0b"),
      # upper nibble differs, lower nibble identical -> still ratio 1.0
      _f(0.5, 0, 0x200, "a" + "b"),
    ]
    results, err = _similar_bits_results(frames, 0x100, 0, 1.0, bytes.fromhex("0f"), 10)
    self.assertIsNone(err)
    self.assertEqual(len(results), 1)
    self.assertAlmostEqual(results[0]["match_ratio"], 1.0)

  def test_bus_isolation(self):
    frames = [
      _f(1.0, 0, 0x100, "0b"),
      _f(0.5, 1, 0x200, "0b"),
      _f(0.5, 0, 0x200, "f4"),
    ]
    results, _err = _similar_bits_results(frames, 0x100, 0, 1.0, bytes.fromhex("ff"), 10)
    by_bus = {r["address"]: r["bus"] for r in results}
    self.assertEqual(by_bus[0x200], 0)  # group key is (bus, address)

  def test_reference_not_found(self):
    frames = [_f(1.0, 0, 0x100, "0b")]
    _results, err = _similar_bits_results(frames, 0x999, 0, 1.0, bytes.fromhex("ff"), 10)
    self.assertEqual(err, "Reference frame not found")

  def test_empty_mask_rejected(self):
    frames = [_f(1.0, 0, 0x100, "0b")]
    _results, err = _similar_bits_results(frames, 0x100, 0, 1.0, b"", 10)
    self.assertEqual(err, "Empty mask")

  def test_top_n_limits_results(self):
    frames = [_f(1.0, 0, 0x100, "0b")]
    for i in range(5):
      frames.append(_f(0.5, 0, 0x200 + i, "0b"))
    results, err = _similar_bits_results(frames, 0x100, 0, 1.0, bytes.fromhex("ff"), 3)
    self.assertIsNone(err)
    self.assertEqual(len(results), 3)

  def test_top_n_zero_clamps_to_one(self):
    """Regression: top_n=0 must not fall back to the default (falsy trap)."""
    frames = [_f(1.0, 0, 0x100, "0b")]
    for i in range(3):
      frames.append(_f(0.5, 0, 0x200 + i, "0b"))
    results, err = _similar_bits_results(frames, 0x100, 0, 1.0, bytes.fromhex("ff"), 0)
    self.assertIsNone(err)
    self.assertEqual(len(results), 1)
    results, err = _similar_bits_results(frames, 0x100, 0, 1.0, bytes.fromhex("ff"), 99)
    self.assertIsNone(err)
    self.assertEqual(len(results), 3)


if __name__ == "__main__":
  unittest.main()
