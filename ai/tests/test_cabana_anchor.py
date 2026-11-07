"""Tests for the cabana anchoring / calibration / detection library
(ai/services/cabana/anchor.py)."""

from __future__ import annotations

import ai.tests.bootstrap_pc  # noqa: F401  # PC mocks before ai imports
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from ai.services.cabana import anchor
from ai.tests.cabana_fixtures import (
  make_brake_frames,
  make_mux_frames,
  make_noise_frames,
  make_speed_frames,
  make_truth_series,
  make_xor_checksum_frames,
  speed_at,
)

ADDR_SPEED = 0x1A8
ADDR_BRAKE = 0x1C0
ADDR_CHECKSUM = 0x2FF
ADDR_NOISE = 0x123
ADDR_MUX = 0x310


class FitLinearTest(unittest.TestCase):
  def test_exact_linear_recovery(self):
    raws = [float(i) for i in range(200)]
    phys = [0.01 * r - 2.0 for r in raws]
    fit = anchor._fit_linear(raws, phys)
    self.assertIsNotNone(fit)
    self.assertAlmostEqual(fit["factor"], 0.01, delta=1e-9)
    self.assertAlmostEqual(fit["offset"], -2.0, delta=1e-6)
    self.assertGreaterEqual(fit["r2"], 0.999)

  def test_rejects_short_or_noisy(self):
    self.assertIsNone(anchor._fit_linear([1.0] * 10, [2.0] * 10))
    rng = __import__("random").Random(3)
    raws = [float(i) for i in range(200)]
    phys = [0.01 * r + rng.uniform(-50, 50) for r in raws]
    self.assertIsNone(anchor._fit_linear(raws, phys))

  def test_rejects_extreme_factor(self):
    raws = [float(i) for i in range(200)]
    phys = [1e-6 * r for r in raws]
    self.assertIsNone(anchor._fit_linear(raws, phys))


class DetectChecksumTest(unittest.TestCase):
  def test_xor_byte_detected(self):
    frames = make_xor_checksum_frames(ADDR_CHECKSUM, n=400)
    datas = [bytes.fromhex(f["data"]) for f in frames]
    self.assertEqual(anchor._detect_checksum(datas), 7)

  def test_random_payload_not_detected(self):
    frames = make_noise_frames(ADDR_NOISE, n=500)
    datas = [bytes.fromhex(f["data"]) for f in frames]
    self.assertIsNone(anchor._detect_checksum(datas))

  def test_too_few_samples(self):
    datas = [bytes(8)] * 10
    self.assertIsNone(anchor._detect_checksum(datas))


class MuxHintTest(unittest.TestCase):
  def test_mux_evidence_reported(self):
    frames = make_mux_frames(ADDR_MUX, n=600)
    truth = make_truth_series()
    cands = anchor._annotate_candidates(ADDR_MUX, frames, truth, 0.0)
    muxed = [c for c in cands if c.get("flag") == "mux"]
    self.assertTrue(muxed, f"expected a mux-flagged candidate, got: {[(c['start_bit'], c['size']) for c in cands]}")
    self.assertTrue(any(e.startswith("mux_hint:") for e in muxed[0]["evidence"]))

  def test_no_mux_on_continuous_signal(self):
    frames = make_speed_frames(ADDR_SPEED, n=600)
    truth = make_truth_series()
    cands = anchor._annotate_candidates(ADDR_SPEED, frames, truth, 0.0)
    # counter byte2 (256 values) and speed bytes must not be mux-flagged
    self.assertFalse([c for c in cands if c.get("flag") == "mux" and c["size"] >= 16])


class SpeedAnchorTest(unittest.TestCase):
  SPEED_FACTOR = 0.00016
  SPEED_OFFSET = 5.0

  def setUp(self):
    self.frames = make_speed_frames(ADDR_SPEED, n=1000, factor=self.SPEED_FACTOR, offset=self.SPEED_OFFSET)
    self.truth = make_truth_series()
    self.cands = anchor._annotate_candidates(ADDR_SPEED, self.frames, self.truth, 0.0)

  def test_speed_candidate_anchored(self):
    speed = next(c for c in self.cands if c["start_bit"] == 0 and c["size"] == 16)
    self.assertIsNotNone(speed.get("anchor"))
    self.assertGreater(abs(speed["anchor"]["pearson_r"]), 0.9)
    self.assertEqual(speed["anchor"]["truth"], "gps_speed")
    self.assertGreater(speed["anchor"]["n"], 0)

  def test_speed_candidate_calibrated(self):
    speed = next(c for c in self.cands if c["start_bit"] == 0 and c["size"] == 16)
    cal = speed.get("calibration")
    self.assertIsNotNone(cal)
    # factor error < 1% vs the encoding factor; offset error < 1% of span
    self.assertAlmostEqual(cal["factor"], self.SPEED_FACTOR, delta=self.SPEED_FACTOR * 0.01)
    self.assertAlmostEqual(cal["offset"], self.SPEED_OFFSET, delta=0.2)
    self.assertGreaterEqual(cal["r2"], 0.9)
    self.assertEqual(speed["unit"], "m/s")

  def test_speed_functions_and_confidence(self):
    speed = next(c for c in self.cands if c["start_bit"] == 0 and c["size"] == 16)
    self.assertIn("speed", speed["functions"])
    self.assertIsInstance(speed["confidence"], int)
    self.assertGreaterEqual(speed["confidence"], 80)

  def test_evidence_is_prefixed_string_list(self):
    speed = next(c for c in self.cands if c["start_bit"] == 0 and c["size"] == 16)
    evidence = speed["evidence"]
    self.assertIsInstance(evidence, list)
    self.assertTrue(all(isinstance(e, str) for e in evidence))
    prefixes = {e.split(":", 1)[0] for e in evidence}
    self.assertIn("statistical", prefixes)
    self.assertIn("anchor", prefixes)
    self.assertIn("fit", prefixes)
    self.assertIn("decode", prefixes)
    self.assertTrue(prefixes <= {"statistical", "anchor", "fit", "decode", "mux_hint"})

  def test_preview_present(self):
    speed = next(c for c in self.cands if c["start_bit"] == 0 and c["size"] == 16)
    preview = speed.get("preview") or {}
    self.assertTrue(preview.get("t"))
    self.assertEqual(len(preview["t"]), len(preview["v"]))
    self.assertLessEqual(len(preview["t"]), 120)
    # preview physical values should match the fixture speed profile
    self.assertAlmostEqual(max(preview["v"]), max(speed_at(t) for t in (0.0, 2.5)), delta=0.5)


class BrakeAnchorTest(unittest.TestCase):
  def test_brake_bool_negative_anchor(self):
    frames = make_brake_frames(ADDR_BRAKE, n=1000)
    truth = make_truth_series()
    cands = anchor._annotate_candidates(ADDR_BRAKE, frames, truth, 0.0)
    brake = next(c for c in cands if c["size"] == 1)
    self.assertIsNotNone(brake.get("anchor"))
    self.assertEqual(brake["anchor"]["sign"], -1)
    self.assertLessEqual(abs(brake["anchor"]["pearson_r"]), 1.0)
    self.assertGreaterEqual(abs(brake["anchor"]["pearson_r"]), 0.5)
    self.assertIn("brake", brake["functions"])

  def test_brake_fit_keeps_positive_factor(self):
    frames = make_brake_frames(ADDR_BRAKE, n=1000)
    truth = make_truth_series()
    cands = anchor._annotate_candidates(ADDR_BRAKE, frames, truth, 0.0)
    brake = next(c for c in cands if c["size"] == 1)
    cal = brake.get("calibration")
    if cal is not None:  # bool fit needs ≥50 aligned points; may stay None
      self.assertGreater(cal["factor"], 0)


class DegradationTest(unittest.TestCase):
  def test_zero_variance_truth_produces_no_anchor(self):
    frames = make_speed_frames(ADDR_SPEED, n=500)
    truth = {
      "available": True,
      "note": "",
      "series": {"gps_speed": {"t": [0.0, 1.0, 2.0], "v": [5.0, 5.0, 5.0]}},
    }
    cands = anchor._annotate_candidates(ADDR_SPEED, frames, truth, 0.0)
    self.assertTrue(cands)
    for c in cands:
      self.assertIsNone(c.get("anchor"))
      self.assertIsNone(c.get("calibration"))

  def test_unavailable_truth_uses_renormalized_confidence(self):
    frames = make_speed_frames(ADDR_SPEED, n=500)
    cands = anchor._annotate_candidates(ADDR_SPEED, frames, None, 0.0)
    speed = next(c for c in cands if c["start_bit"] == 0 and c["size"] == 16)
    self.assertIsNone(speed.get("anchor"))
    self.assertIsInstance(speed["confidence"], int)
    # statistical-only signal with high transition rate should still score
    self.assertGreater(speed["confidence"], 0)

  def test_checksum_flagged_and_excluded_from_confidence(self):
    frames = make_xor_checksum_frames(ADDR_CHECKSUM, n=400)
    truth = make_truth_series()
    cands = anchor._annotate_candidates(ADDR_CHECKSUM, frames, truth, 0.0)
    flagged = [c for c in cands if c.get("flag") == "checksum"]
    self.assertTrue(flagged)
    for c in flagged:
      self.assertIsNone(c["confidence"])

  def test_noise_frames_not_checksum_flagged(self):
    frames = make_noise_frames(ADDR_NOISE, n=500)
    cands = anchor._annotate_candidates(ADDR_NOISE, frames, None, 0.0)
    self.assertTrue(cands)
    self.assertFalse([c for c in cands if c.get("flag") == "checksum"])


class BestLagCorrelationTest(unittest.TestCase):
  def test_zero_lag_perfect_correlation(self):
    ts = [i / 20.0 for i in range(400)]
    vs = [math.sin(2.0 * math.pi * t / 10.0) for t in ts]
    out = anchor._best_lag_correlation(ts, vs, ts, vs)
    self.assertIsNotNone(out)
    self.assertGreater(out["pearson_r"], 0.99)
    self.assertEqual(out["sign"], 1)

  def test_constant_series_returns_none(self):
    ts = [i / 20.0 for i in range(400)]
    out = anchor._best_lag_correlation(ts, [1.0] * 400, ts, [2.0] * 400)
    self.assertIsNone(out)

  def test_no_overlap_returns_none(self):
    ts_a = [i / 20.0 for i in range(400)]
    ts_b = [100.0 + i / 20.0 for i in range(400)]
    out = anchor._best_lag_correlation(ts_a, [float(i) for i in range(400)], ts_b, [float(i) for i in range(400)])
    self.assertIsNone(out)


class TruthVarianceTest(unittest.TestCase):
  def test_variance_ok(self):
    self.assertTrue(anchor._truth_variance_ok(make_truth_series()))
    self.assertFalse(anchor._truth_variance_ok(None))
    self.assertFalse(anchor._truth_variance_ok({"available": False, "series": {}}))
    flat = {"available": True, "series": {"gps_speed": {"t": [float(i) for i in range(100)], "v": [1.0] * 100}}}
    self.assertFalse(anchor._truth_variance_ok(flat))


if __name__ == "__main__":
  unittest.main()
