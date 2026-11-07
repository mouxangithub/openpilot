"""G3 closure — token meter + compaction budget gating + retain + summary.

Proves behavior, not existence:
- the heuristic meter bounds ASCII (~4 chars/token) and CJK (~1.6 chars/token);
- compaction fires only above budget*threshold_ratio and never when the
  budget is unset (the old always-compact bug);
- compact_now prunes oversized results with token-priced shadow events,
  keeps the most recent slice unpruned (retain_ratio), and emits a summary
  marker with provenance (APPEND — pruned seqs are scattered, so REPLACE
  would fail strict surface validation);
- llm_stream wins when provided; the deterministic digest is the fallback.
"""

from __future__ import annotations

import unittest

import ai.tests.bootstrap_pc  # noqa: F401  (PC openpilot mocks)

from ai.core.session.compaction import CompactionConfig, CompactionService
from ai.core.session.log import EventType, SessionLog, SurfaceOp
from ai.core.session.pruner import ToolResultPruner
from ai.core.session.tokens import count_message_tokens, estimate_tokens

_BIG = "x" * 40_000


def _log_with_results(n_big: int = 3, n_small: int = 2) -> SessionLog:
    log = SessionLog("compaction-test")
    log.append(EventType.USER_MESSAGE, {"content": "please analyze the exports"}, surface_op=SurfaceOp.APPEND)
    for i in range(n_big):
        log.append(EventType.TOOL_RESULT, {"tool_call_id": f"big-{i}", "content": _BIG}, surface_op=SurfaceOp.APPEND)
    for i in range(n_small):
        log.append(EventType.TOOL_RESULT, {"tool_call_id": f"small-{i}", "content": f"small result {i}"}, surface_op=SurfaceOp.APPEND)
    return log


class TokenMeterTests(unittest.TestCase):
    def test_ascii_about_four_chars_per_token(self) -> None:
        text = "a" * 4000
        estimate = estimate_tokens(text)
        self.assertAlmostEqual(estimate, 1000, delta=100)

    def test_cjk_about_one_point_six_chars_per_token(self) -> None:
        text = "车" * 1600
        estimate = estimate_tokens(text)
        self.assertAlmostEqual(estimate, 1000, delta=120)

    def test_mixed_and_empty(self) -> None:
        self.assertEqual(estimate_tokens(""), 0)
        mixed = "abc车" * 100
        self.assertGreater(estimate_tokens(mixed), 0)

    def test_message_counting(self) -> None:
        messages = [
            {"role": "user", "content": "a" * 400},
            {"role": "assistant", "content": "车" * 160},
        ]
        total = count_message_tokens(messages)
        self.assertGreater(total, 100 + 100)  # framing overhead included
        self.assertLess(total, 400 + 400)


class BudgetGatingTests(unittest.TestCase):
    def test_under_budget_never_fires(self) -> None:
        log = _log_with_results(n_big=0)
        service = CompactionService(log, config=CompactionConfig(max_tokens=1_000_000))
        result = __import__("asyncio").run(service.compact_if_needed(None))
        self.assertIsNone(result)

    def test_zero_budget_disables_auto_but_not_explicit(self) -> None:
        log = _log_with_results()
        service = CompactionService(log, config=CompactionConfig(max_tokens=0))
        should, measured, budget = service.should_compact()
        self.assertFalse(should)
        self.assertEqual(budget, 0)
        # Explicit compaction still works.
        result = __import__("asyncio").run(service.compact_now(None))
        self.assertIsNotNone(result)

    def test_over_budget_fires_and_reports(self) -> None:
        log = _log_with_results()
        service = CompactionService(log, config=CompactionConfig(max_tokens=3000, threshold_ratio=0.8))
        should, measured, _budget = service.should_compact()
        self.assertTrue(should)
        self.assertGreater(measured, 2400)
        result = __import__("asyncio").run(service.compact_if_needed(None))
        self.assertIsNotNone(result)
        self.assertGreater(result.shadowed_token_count, 0)
        self.assertEqual(len(result.shadowed_seqs), 3, "all three oversized results pruned")
        self.assertTrue(result.summary)


class CompactionBehaviorTests(unittest.TestCase):
    def test_summary_marker_and_lifecycle_events(self) -> None:
        log = _log_with_results()
        service = CompactionService(log, config=CompactionConfig(max_tokens=3000))
        result = __import__("asyncio").run(service.compact_now(None))
        # Summary marker is an APPEND user message with provenance.
        marker = log.events[result.replacement_seq]
        self.assertEqual(marker.type, EventType.USER_MESSAGE)
        self.assertEqual(marker.surface_op, SurfaceOp.APPEND)
        self.assertIn("Compaction summary", marker.data["content"])
        self.assertEqual(marker.data["shadowedSeqs"], result.shadowed_seqs)
        kinds = [e.data.get("kind") for e in log.events if e.type == EventType.LIFECYCLE]
        self.assertIn("compaction/start", kinds)
        self.assertIn("compaction/summary", kinds)
        self.assertIn("compaction/end", kinds)

    def test_retain_ratio_keeps_recent_results(self) -> None:
        log = _log_with_results(n_big=3, n_small=0)
        # 3 tool results, retain_ratio 1/3 → most recent 1 unpruned.
        service = CompactionService(log, config=CompactionConfig(max_tokens=3000, retain_ratio=1 / 3))
        result = __import__("asyncio").run(service.compact_now(None))
        self.assertEqual(len(result.shadowed_seqs), 2, "most recent result must survive")
        # The retained node's content is still the full text on the surface.
        surface_contents = [
            (n.data or {}).get("content", "") for n in log.surface
            if n.event_type == EventType.TOOL_RESULT
        ]
        self.assertIn(_BIG, surface_contents, "retained recent result untouched")

    def test_llm_summary_wins_over_digest(self) -> None:
        log = _log_with_results()

        async def llm_stream(messages):
            return "LLM digest of the session"

        service = CompactionService(log, llm_stream=llm_stream, config=CompactionConfig(max_tokens=3000))
        result = __import__("asyncio").run(service.compact_now(None))
        self.assertEqual(result.summary, "LLM digest of the session")

    def test_llm_failure_falls_back_to_digest(self) -> None:
        log = _log_with_results()

        async def broken(messages):
            raise RuntimeError("llm down")

        service = CompactionService(log, llm_stream=broken, config=CompactionConfig(max_tokens=3000))
        result = __import__("asyncio").run(service.compact_now(None))
        self.assertIn("Session objective", result.summary)
        self.assertIn("pruned", result.summary)

    def test_digest_mentions_objective_and_counts(self) -> None:
        log = _log_with_results()
        service = CompactionService(log, config=CompactionConfig(max_tokens=3000))
        result = __import__("asyncio").run(service.compact_now(None))
        self.assertIn("please analyze the exports", result.summary)
        self.assertIn("3 oversized tool result", result.summary)


class PrunerMeterTests(unittest.TestCase):
    def test_shadow_event_carries_token_price(self) -> None:
        log = _log_with_results(n_big=1, n_small=0)
        result = ToolResultPruner().prune_session(log, token_meter=estimate_tokens)
        self.assertEqual(len(result.pruned), 1)
        self.assertGreater(result.tokens_removed, 0)
        shadow = next(e for e in log.events if e.type == EventType.COMPACTION_PRUNE)
        self.assertGreater(shadow.data["shadowedTokenCount"], 0)
        self.assertLess(shadow.data["shadowedTokenCount"], shadow.data["shadowedCharCount"])

    def test_retain_recent_direct(self) -> None:
        log = _log_with_results(n_big=2, n_small=0)
        result = ToolResultPruner().prune_session(log, retain_recent=1)
        self.assertEqual(len(result.pruned), 1)


if __name__ == "__main__":
    unittest.main()
