"""G1 closure — spill dispatch-log arm.

The session log's copy of an oversized tool result must shrink to
preview + locator independently of the model-facing waterfall (dsh
``tools/ptc-dispatch-log``): read-family tools and nested calls are
deliberately NOT bounded on the model-facing side, but the log copy is not
model context and always gets bounded. Proves behavior via the extracted
``bound_dispatch_log_copy`` seam plus a source-level guard for the wiring.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

import ai.tests.bootstrap_pc  # noqa: F401  (PC openpilot mocks)
from ai.core.agent.loop import bound_dispatch_log_copy
from ai.tools.result_externalize import threshold_bytes

import ai.system.paths as paths_mod


def _workspace_root() -> Path:
    return Path(str(paths_mod.workspace_path(".")))


class DispatchLogArmTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session_id = "dispatch-arm-test"
        self.cap = threshold_bytes(None)

    def _big_text(self, target_bytes: int) -> str:
        base = "x" * 1024
        reps = target_bytes // 1024 + 2
        return (base * reps)[:target_bytes + 64]

    def test_oversized_read_result_log_copy_bounded(self) -> None:
        big = self._big_text(self.cap * 3)
        result = {"ok": True, "content": big}
        original_payload = json.dumps(result, ensure_ascii=False)

        bounded = bound_dispatch_log_copy(
            result, original_payload,
            session_id=self.session_id, tool_name="read_file", call_id="c1",
        )

        self.assertLess(len(bounded.encode("utf-8")), len(original_payload.encode("utf-8")))
        self.assertIn(big[:100], bounded, "head retained")
        self.assertIn(big[-100:], bounded, "tail retained")
        self.assertIn("stored at", bounded, "locator present")
        self.assertIn("omitted", bounded, "bounded notice present")
        # The model-facing result object is untouched — read still returns whole.
        self.assertEqual(result["content"], big)
        self.assertEqual(json.dumps(result, ensure_ascii=False), original_payload)

    def test_small_result_log_copy_unchanged(self) -> None:
        result = {"ok": True, "content": "tiny"}
        payload = json.dumps(result, ensure_ascii=False)
        bounded = bound_dispatch_log_copy(
            result, payload,
            session_id=self.session_id, tool_name="read_file", call_id="c2",
        )
        self.assertEqual(bounded, payload)

    def test_structured_result_spilled_as_json(self) -> None:
        result = {"ok": True, "rows": [{"v": i} for i in range(2000)]}
        payload = json.dumps(result, ensure_ascii=False)
        self.assertGreater(len(payload.encode("utf-8")), self.cap)
        bounded = bound_dispatch_log_copy(
            result, payload,
            session_id=self.session_id, tool_name="db_query", call_id="c3",
        )
        self.assertNotEqual(bounded, payload)
        self.assertIn("stored at", bounded)

    def test_spill_disabled_keeps_payload(self) -> None:
        big = self._big_text(self.cap * 3)
        result = {"ok": True, "content": big}
        payload = json.dumps(result, ensure_ascii=False)
        with patch("ai.tools.result_externalize.externalize_enabled", return_value=False):
            bounded = bound_dispatch_log_copy(
                result, payload,
                session_id=self.session_id, tool_name="read_file", call_id="c4",
            )
        self.assertEqual(bounded, payload)

    def test_no_session_owner_keeps_payload(self) -> None:
        big = self._big_text(self.cap * 3)
        result = {"ok": True, "content": big}
        payload = json.dumps(result, ensure_ascii=False)
        bounded = bound_dispatch_log_copy(
            result, payload,
            session_id="", tool_name="read_file", call_id="c5",
        )
        self.assertEqual(bounded, payload)

    def test_loop_wiring_guards(self) -> None:
        """Static guard: the TOOL_RESULT append path must route through the
        dispatch arm and skip already-externalized (pointer) results."""
        import ai.core.agent.loop as loop_mod

        source = loop_mod.AgentLoop._step.__code__.co_names
        self.assertIn("_bound_log_copy", source, "TOOL_RESULT append must call the arm")
        src = loop_mod.bound_dispatch_log_copy.__doc__ or ""
        self.assertIn("kind=\"dispatch\"", src)
        step_src = loop_mod.AgentLoop._step.__code__
        self.assertIsNotNone(step_src)
        # The externalized skip condition lives in _step's bytecode constants.
        import dis
        consts = set()
        for ins in dis.get_instructions(loop_mod.AgentLoop._step):
            if isinstance(ins.argval, str):
                consts.add(ins.argval)
        self.assertIn("externalized", consts, "loop must skip already-externalized results")

    def test_ref_records_dispatch_kind(self) -> None:
        from ai.tools.result_externalize import spill_text_if_needed
        big = self._big_text(self.cap * 3)
        replaced, ref = spill_text_if_needed(
            big, session_id=self.session_id, tool_name="read_file",
            call_id="c6", kind="dispatch",
        )
        self.assertIsNotNone(replaced)
        self.assertEqual(ref["kind"], "dispatch")
        # Default kind stays "result" (model-facing arm parity).
        _r2, ref2 = spill_text_if_needed(
            self._big_text(self.cap * 3), session_id=self.session_id,
            tool_name="t", call_id="c7",
        )
        self.assertEqual(ref2["kind"], "result")


if __name__ == "__main__":
    unittest.main()
