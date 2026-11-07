"""Tool-result pruner tests (G3: dsh compaction-tool-result-pruner port)."""

from __future__ import annotations

import unittest

import ai.tests.bootstrap_pc  # noqa: F401

from ai.core.session.log import EventType, SessionLog, SurfaceOp
from ai.core.session.pruner import (
  DEFAULT_THRESHOLD_CHARS,
  PRUNE_MARKER,
  PruneResult,
  ToolResultPruner,
  code_point_length,
  prune_events,
  resolve_config,
)


def _seed_tool_result(log: SessionLog, call_id: str, text: str) -> None:
  log.append(EventType.TOOL_CALL, {"turn": 1, "step": 1, "callId": call_id, "name": "bash"})
  log.append(
    EventType.TOOL_RESULT,
    {"turn": 1, "step": 1, "tool_call_id": call_id, "content": text},
    surface_op=SurfaceOp.APPEND,
  )


class ConfigTests(unittest.TestCase):
  def test_defaults_match_dsh(self) -> None:
    cfg = resolve_config()
    self.assertEqual(cfg.threshold_chars, 8192)
    self.assertEqual(cfg.head_chars, 4096)
    self.assertEqual(cfg.tail_chars, 1024)

  def test_emitted_budget_must_fit_threshold(self) -> None:
    with self.assertRaises(ValueError):
      resolve_config(threshold_chars=100, head_chars=4096, tail_chars=1024)

  def test_negative_and_zero_rejected(self) -> None:
    with self.assertRaises(ValueError):
      resolve_config(threshold_chars=0)
    with self.assertRaises(ValueError):
      resolve_config(head_chars=-1)


class PruneContentTests(unittest.TestCase):
  def test_within_budget_returns_none(self) -> None:
    pruner = ToolResultPruner()
    self.assertIsNone(pruner.prune_content("short"))

  def test_over_budget_prunes_middle(self) -> None:
    pruner = ToolResultPruner()
    text = "H" * 4096 + "X" * 4000 + "T" * 1024
    pruned = pruner.prune_content(text)
    self.assertIsNotNone(pruned)
    assert pruned is not None
    self.assertIn(PRUNE_MARKER.strip(), pruned)
    self.assertLessEqual(code_point_length(pruned), DEFAULT_THRESHOLD_CHARS)
    self.assertTrue(pruned.startswith("H"))
    self.assertTrue(pruned.endswith("T"))
    self.assertEqual(pruned.count("[... tool result middle pruned ...]"), 1)

  def test_unicode_code_point_slicing(self) -> None:
    pruner = ToolResultPruner(threshold_chars=100, head_chars=40, tail_chars=20)
    text = "你" * 200  # BMP chars, 1 code point each
    pruned = pruner.prune_content(text)
    self.assertIsNotNone(pruned)
    assert pruned is not None
    self.assertLessEqual(code_point_length(pruned), 100)
    self.assertIn("你", pruned)


class PruneSessionTests(unittest.TestCase):
  def test_prune_session_replaces_over_budget_results(self) -> None:
    log = SessionLog("prune-session-test")
    big = "Z" * 20_000
    _seed_tool_result(log, "c1", big)
    _seed_tool_result(log, "c2", "small result")
    pruner = ToolResultPruner()
    result = pruner.prune_session(log)
    self.assertIsInstance(result, PruneResult)
    self.assertEqual(len(result.pruned), 1)
    entry = result.pruned[0]
    self.assertEqual(entry.tool_call_id, "c1")
    self.assertEqual(entry.chars_before, 20_000)
    self.assertGreater(result.chars_removed, 0)
    # Shadow-price event landed adjacent to its replacement.
    shadow_events = [e for e in log.events if e.type == EventType.COMPACTION_PRUNE]
    self.assertEqual(len(shadow_events), 1)
    self.assertEqual(shadow_events[0].data["shadowedSeqs"], [entry.original_seq])
    self.assertEqual(shadow_events[0].data["shadowedCharCount"], 20_000)
    replacement = log.events[entry.replacement_seq]
    self.assertEqual(replacement.type, EventType.TOOL_RESULT)
    self.assertEqual(replacement.data["tool_call_id"], "c1")
    self.assertEqual(replacement.surface_op, SurfaceOp.REPLACE)
    self.assertEqual(list(replacement.source_seqs or []), [entry.original_seq])
    # Surface: exactly one live node per tool result, small one untouched.
    tool_nodes = [n for n in log.surface if n.event_type == EventType.TOOL_RESULT]
    self.assertEqual(len(tool_nodes), 2)
    contents = {n.data.get("tool_call_id"): n.data.get("content") for n in tool_nodes}
    self.assertEqual(contents["c2"], "small result")
    self.assertIn("tool result middle pruned", contents["c1"])
    # Idempotent: a second pass changes nothing.
    self.assertEqual(pruner.prune_session(log).pruned, [])

  def test_pure_projection_subtracts_shadowed_chars(self) -> None:
    log = SessionLog("prune-projection-test")
    _seed_tool_result(log, "c1", "Y" * 20_000)
    ToolResultPruner().prune_session(log)
    projection = prune_events(log.events)
    self.assertEqual(projection["shadowedSeqs"], [1])  # tool_result seq
    self.assertEqual(projection["shadowedChars"], 20_000)
    self.assertLessEqual(projection["liveToolResultChars"], DEFAULT_THRESHOLD_CHARS)

  def test_non_string_content_skipped(self) -> None:
    log = SessionLog("prune-nonstr-test")
    log.append(EventType.TOOL_CALL, {"turn": 1, "step": 1, "callId": "c9", "name": "x"})
    log.append(
      EventType.TOOL_RESULT,
      {"turn": 1, "step": 1, "tool_call_id": "c9", "content": {"raw": "Z" * 20_000}},
      surface_op=SurfaceOp.APPEND,
    )
    result = ToolResultPruner().prune_session(log)
    self.assertEqual(result.pruned, [])


if __name__ == "__main__":
  unittest.main()
