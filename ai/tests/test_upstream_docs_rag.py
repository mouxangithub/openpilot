"""Tests for upstream docs RAG seeds and the safety rules prompt block."""

from __future__ import annotations

import unittest
from typing import Any
from unittest import mock

import ai.tests.bootstrap_pc  # noqa: F401 — side effect: openpilot mocks

from ai.core.wspace.safety_rules import safety_rules_prompt_block
from ai.tools.domains.core.comma_docs_rag import COMMA_DOCS_RAG
from ai.tools.domains.core.upstream_docs_rag import UPSTREAM_DOCS_RAG


def _doc_ids(docs: list[dict[str, Any]]) -> set[str]:
  return {str(d.get("id", "")) for d in docs}


class TestUpstreamDocsRag(unittest.TestCase):
  def test_upstream_entries_structure(self):
    self.assertGreaterEqual(len(UPSTREAM_DOCS_RAG), 6)
    ids = _doc_ids(UPSTREAM_DOCS_RAG)
    self.assertIn("builtin_op_connect_comma_full", ids)
    self.assertIn("builtin_op_debugging_safety_full", ids)
    for doc in UPSTREAM_DOCS_RAG:
      for key in ("id", "title", "tags", "text"):
        self.assertTrue(doc.get(key), f"{doc.get('id')} missing {key}")
      self.assertTrue(str(doc["id"]).startswith("builtin_"), doc["id"])
      self.assertTrue(doc.get("refresh"), doc["id"])
      self.assertTrue(str(doc["text"]).startswith("来源：openpilot 上游 docs"), doc["id"])

  def test_imu_calibration_fork_note(self):
    imu = next(d for d in UPSTREAM_DOCS_RAG if d["id"] == "builtin_op_imu_calibration_full")
    self.assertIn("sunnypilot fork", imu["text"])
    self.assertIn("上游 openpilot 无此功能", imu["text"])

  def test_safety_fulltext_entries_exist(self):
    ids = _doc_ids(COMMA_DOCS_RAG)
    self.assertIn("builtin_op_safety_full", ids)
    self.assertIn("builtin_op_limitations_full", ids)
    self.assertIn("builtin_op_cars_index_guide", ids)
    for doc in COMMA_DOCS_RAG:
      if doc["id"] in ("builtin_op_safety_full", "builtin_op_limitations_full"):
        self.assertIn("来源：openpilot 上游 docs（comma.ai 原版）", doc["text"])
        self.assertIn("来源：", doc["text"][:200])

  def test_safety_rules_block(self):
    block = safety_rules_prompt_block()
    self.assertTrue(block.strip())
    self.assertIn("接管", block)
    self.assertIn("L2", block)

  def test_seed_idempotent(self):
    from ai.tools.domains.core import rag_seed

    store: list[dict[str, Any]] = []

    def _capture(_params: Any, docs: list[dict[str, Any]]) -> None:
      store.clear()
      store.extend(docs)

    with mock.patch.object(rag_seed, "_load_docs", return_value=[]), \
      mock.patch.object(rag_seed, "_save_docs", side_effect=_capture):
      first = rag_seed.ensure_builtin_rag_docs()
      second = rag_seed.ensure_builtin_rag_docs()
    self.assertTrue(first.get("ok"))
    self.assertTrue(second.get("ok"))
    self.assertEqual(first.get("total"), second.get("total"))
    self.assertEqual(first.get("errors"), [])
    ids = [str(d.get("id")) for d in store]
    self.assertEqual(len(ids), len(set(ids)))
    for expected in ("builtin_op_safety_full", "builtin_op_limitations_full", "builtin_op_logs_full"):
      self.assertIn(expected, ids)


if __name__ == "__main__":
  unittest.main()
