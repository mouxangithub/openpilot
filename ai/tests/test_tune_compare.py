"""API tune compare and platform integration tests."""

from __future__ import annotations

import unittest


class TestTuneCompareApi(unittest.TestCase):
  def test_compare_tune_ab_invalid_routes(self):
    from ai.tools.route_analysis_tools import compare_tune_ab

    res = compare_tune_ab("", "b")
    self.assertFalse(res.get("ok"))

  def test_score_tune_session_structure(self):
    from ai.tools.route_scoring_tools import score_tune_session
    from unittest.mock import patch

    fake_score = {
      "ok": True,
      "route": "r",
      "composite_score": 72.0,
      "grade": "B",
      "metrics": {},
    }
    fake_ab = {"ok": True, "tune_highlights": [], "tune_recommendations": []}
    with patch("ai.tools.route_scoring_tools.score_route_tune", return_value=fake_score):
      with patch("ai.tools.route_scoring_tools.compare_tune_ab", return_value=fake_ab):
        out = score_tune_session("a", "b")
    self.assertTrue(out.get("ok"))
    self.assertIn("score_delta", out)
    self.assertIn("passed", out)


if __name__ == "__main__":
  unittest.main()
