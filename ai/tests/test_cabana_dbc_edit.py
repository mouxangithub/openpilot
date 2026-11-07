"""Tests for AI-assisted DBC editing (ai/services/cabana/dbc_edit.py).

Covers:
- statistical candidate extraction (counter / bool / constant exclusion),
- DBC draft build + structural parse + decode validation,
- edit ops (add / rename / remove / modify) incl. CM_/VAL_ annotation keeping,
- LLM output parsing + merging,
- the versioned user-DBC store (commit / versions / rollback / history prune),
- the HTTP endpoints (commit / versions / rollback / ai edit / ai infer).
"""

from __future__ import annotations

import ai.tests.bootstrap_pc  # noqa: F401  # PC mocks before ai imports
import asyncio
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from ai.services.cabana import dbc_edit
from ai.services.cabana.dbc_edit import (
  _apply_dbc_ops,
  _build_dbc_draft,
  _commit_user_dbc,
  _list_versions,
  _merge_llm_candidates,
  _parse_dbc_text,
  _parse_llm_candidates,
  _parse_op_target,
  _rollback_user_dbc,
  _safe_dbc_name,
  _safe_signal_name,
  _statistical_candidates,
  _user_dbc_paths,
  _validate_dbc_text,
)

ADDR = 0x50  # 80


def _infer_frames(n: int = 256) -> list[dict]:
  """Frames of 0x50: byte0 = frame index mod 256 (counter), bit 9 toggles (bool).

  256 samples guarantee every bit of byte0 is active (i reaches 0xFF).
  """
  frames: list[dict] = []
  for i in range(n):
    b1 = "02" if i % 2 else "00"
    frames.append({
      "time": 1000.0 + i * 0.1,
      "bus": 0,
      "address": ADDR,
      "data": f"{i:02x}{b1}" + "00" * 6,
    })
  return frames


BASE_DBC = """BO_ 380 ESP_Status: 8 Vector__XXX
 SG_ Counter : 0|4@1+ (1,0) [0|15] "" Vector__XXX
 SG_ Checksum : 4|4@1+ (1,0) [0|15] "" Vector__XXX
CM_ SG_ 380 Counter "rolling counter";
VAL_ 380 Counter 0 "zero" 1 "one";
"""


class StatisticalCandidatesTest(unittest.TestCase):
  def test_counter_and_bool_detected(self):
    candidates = _statistical_candidates(_infer_frames())
    names_kinds = {(c["start_bit"], c["size"]): c["kind"] for c in candidates}
    self.assertEqual(names_kinds.get((0, 8)), "counter")
    self.assertTrue(
      any(c["size"] == 1 and c["kind"] == "bool" and c["start_bit"] == 9 for c in candidates),
      f"expected bool candidate at bit 9, got: {candidates}",
    )

  def test_constant_bits_excluded(self):
    candidates = _statistical_candidates(_infer_frames())
    for c in candidates:
      self.assertNotIn((c["start_bit"], c["size"]), {(16, 8), (24, 8), (32, 8)})

  def test_requires_min_samples(self):
    self.assertEqual(_statistical_candidates(_infer_frames(2)), [])

  def test_byte_run_not_duplicated_across_endians(self):
    candidates = _statistical_candidates(_infer_frames())
    byte_runs = [c for c in candidates if c["size"] == 8]
    self.assertEqual(len(byte_runs), 1)
    self.assertTrue(byte_runs[0]["endian"] == "little")

  def test_invalid_hex_ignored(self):
    frames = _infer_frames()
    frames.append({"time": 2000.0, "bus": 0, "address": ADDR, "data": "zz"})
    candidates = _statistical_candidates(frames)
    self.assertTrue(candidates)


class DraftAndValidationTest(unittest.TestCase):
  def test_draft_roundtrip_and_decode_report(self):
    frames = _infer_frames()
    candidates = _statistical_candidates(frames)
    draft = _build_dbc_draft(ADDR, candidates)
    signals, errors = _parse_dbc_text(draft)
    self.assertEqual(errors, [], f"structural parse errors: {errors}")
    self.assertTrue(any(s["name"] == "S0_8" for s in signals))
    report = _validate_dbc_text(draft, {ADDR: frames})
    self.assertTrue(report["parse_ok"], f"validation errors: {report['errors']}")
    self.assertIsNotNone(report["decode_report"])
    self.assertTrue(report["decode_report"]["ok"])
    self.assertEqual(report["decode_report"]["undecodable_signals"], [])
    self.assertGreater(report["decode_report"]["decoded_frames"], 0)
    self.assertEqual(report["decode_report"]["non_finite_values"], 0)

  def test_malformed_dbc_reports_errors(self):
    report = _validate_dbc_text("BO_ 10 M: 8 X\n SG_ Bad : 0|x@1+ (1,0) [0|0] \"\" X\n")
    self.assertFalse(report["parse_ok"])
    self.assertTrue(any("malformed SG_" in e for e in report["errors"]))

  def test_draft_escapes_unsafe_names(self):
    draft = _build_dbc_draft(ADDR, [{
      "name": "1 bad name!", "default_name": "S0_8", "start_bit": 0, "size": 8,
      "endian": "little", "signed": False, "factor": 1.0, "offset": 0.0, "unit": "",
    }])
    self.assertIn("SG_ S_1_bad_name_", draft)


class EditOpsTest(unittest.TestCase):
  def test_rename_updates_annotations(self):
    new_text, errors = _apply_dbc_ops(BASE_DBC, [
      {"op": "rename", "target": "380.Counter", "payload": {"new_name": "RollCnt"}},
    ])
    self.assertEqual(errors, [])
    self.assertIn("SG_ RollCnt :", new_text)
    self.assertIn('CM_ SG_ 380 RollCnt "rolling counter";', new_text)
    self.assertIn('VAL_ 380 RollCnt 0 "zero"', new_text)
    self.assertNotIn("Counter", new_text.replace("RollCnt", ""))

  def test_modify_factor(self):
    new_text, errors = _apply_dbc_ops(BASE_DBC, [
      {"op": "modify", "target": "380.Checksum", "payload": {"factor": 0.5}},
    ])
    self.assertEqual(errors, [])
    self.assertIn("SG_ Checksum : 4|4@1+ (0.5,0)", new_text)

  def test_remove_signal(self):
    new_text, errors = _apply_dbc_ops(BASE_DBC, [
      {"op": "remove", "target": "380.Checksum"},
    ])
    self.assertEqual(errors, [])
    self.assertNotIn("Checksum", new_text)
    self.assertIn("SG_ Counter :", new_text)

  def test_remove_missing_signal_errors(self):
    _new_text, errors = _apply_dbc_ops(BASE_DBC, [
      {"op": "remove", "target": "380.NoSuch"},
    ])
    self.assertTrue(any("not found" in e for e in errors))

  def test_add_signal_to_existing_message(self):
    new_text, errors = _apply_dbc_ops(BASE_DBC, [
      {"op": "add", "target": "380.NewSig",
       "payload": {"address": 380, "name": "NewSig", "start_bit": 8, "size": 8}},
    ])
    self.assertEqual(errors, [])
    lines = new_text.splitlines()
    idx = next(i for i, ln in enumerate(lines) if "SG_ NewSig" in ln)
    self.assertGreater(idx, next(i for i, ln in enumerate(lines) if "SG_ Checksum" in ln))

  def test_add_signal_creates_message(self):
    new_text, errors = _apply_dbc_ops(BASE_DBC, [
      {"op": "add", "target": "0x200.NewMsg",
       "payload": {"address": 512, "name": "NewMsg", "start_bit": 0, "size": 16}},
    ])
    self.assertEqual(errors, [])
    self.assertIn("BO_ 512 MSG_200: 8 Vector__XXX", new_text)
    self.assertIn("SG_ NewMsg : 0|16@1+", new_text)

  def test_add_invalid_size_rejected(self):
    _new_text, errors = _apply_dbc_ops(BASE_DBC, [
      {"op": "add", "target": "380.TooBig",
       "payload": {"address": 380, "name": "TooBig", "size": 65}},
    ])
    self.assertTrue(any("size must be 1..64" in e for e in errors))

  def test_unknown_message_errors(self):
    _new_text, errors = _apply_dbc_ops(BASE_DBC, [
      {"op": "rename", "target": "999.Counter", "payload": {"new_name": "X"}},
    ])
    self.assertTrue(any("not found" in e for e in errors))

  def test_parse_op_target(self):
    self.assertEqual(_parse_op_target("0x50.Counter"), (0x50, "Counter"))
    self.assertEqual(_parse_op_target("380.Counter"), (380, "Counter"))
    self.assertEqual(_parse_op_target({"address": 512, "signal": "Sig"}), (512, "Sig"))
    self.assertIsNone(_parse_op_target("no-dot"))
    self.assertIsNone(_parse_op_target("bad.Sig"))


class SafeNameTest(unittest.TestCase):
  def test_signal_name_sanitized(self):
    self.assertEqual(_safe_signal_name("Wheel Speed", "FB"), "Wheel_Speed")
    self.assertEqual(_safe_signal_name("1abc", "FB"), "S_1abc")
    self.assertEqual(_safe_signal_name("", "FB"), "FB")
    self.assertLessEqual(len(_safe_signal_name("x" * 50, "FB")), 32)

  def test_dbc_name_validated(self):
    self.assertEqual(_safe_dbc_name("my car.dbc"), "my_car.dbc")
    self.assertIsNone(_safe_dbc_name("1bad"))
    self.assertIsNone(_safe_dbc_name("  "))
    # Leading dots are stripped, so ".hidden" becomes a valid "hidden".
    self.assertIsNotNone(_safe_dbc_name(".hidden"))


class LlmParsingTest(unittest.TestCase):
  def test_plain_array(self):
    ops = _parse_llm_candidates('[{"name": "Counter", "start_bit": 0, "size": 8}]')
    self.assertEqual(len(ops), 1)
    self.assertEqual(ops[0]["name"], "Counter")

  def test_prose_wrapped_array(self):
    ops = _parse_llm_candidates('Sure! Here you go:\n[{"name": "A", "start_bit": 0, "size": 1}]\nDone.')
    self.assertEqual(len(ops), 1)

  def test_dict_with_signals_key(self):
    ops = _parse_llm_candidates('{"signals": [{"name": "A", "start_bit": 0, "size": 1}]}')
    self.assertEqual(len(ops), 1)

  def test_garbage_returns_empty(self):
    self.assertEqual(_parse_llm_candidates("no json here"), [])
    self.assertEqual(_parse_llm_candidates(""), [])

  def test_merge_matches_by_position_key(self):
    stat = [{
      "name": "S0_8", "default_name": "S0_8", "start_bit": 0, "size": 8,
      "endian": "little", "signed": False, "factor": 1.0, "offset": 0.0,
      "unit": "", "kind": "counter", "confidence": "statistical", "evidence": "stats",
    }]
    merged = _merge_llm_candidates(stat, [{
      "name": "Odometer", "start_bit": 0, "size": 8, "endian": "little",
      "factor": 0.1, "unit": "km", "confidence": 0.9, "evidence": "increments",
    }])
    self.assertEqual(merged[0]["name"], "Odometer")
    self.assertEqual(merged[0]["factor"], 0.1)
    self.assertEqual(merged[0]["unit"], "km")
    self.assertEqual(merged[0]["confidence"], 0.9)
    self.assertIn("LLM: increments", merged[0]["evidence"])

  def test_merge_clamps_confidence(self):
    stat = [{
      "name": "S0_1", "default_name": "S0_1", "start_bit": 0, "size": 1,
      "endian": "little", "signed": False, "factor": 1.0, "offset": 0.0,
      "unit": "", "kind": "bool", "confidence": "statistical", "evidence": "",
    }]
    merged = _merge_llm_candidates(stat, [{"name": "B", "start_bit": 0, "size": 1, "confidence": 7}])
    self.assertEqual(merged[0]["confidence"], 1.0)


class UserDbcStoreTest(unittest.TestCase):
  """Store tests run against a temp AI_USER_DBC_DIR (env is read per call)."""

  def setUp(self):
    self._tmp = tempfile.TemporaryDirectory()
    self._env = patch.dict(os.environ, {"AI_USER_DBC_DIR": self._tmp.name})
    self._env.start()
    self.addCleanup(self._env.stop)
    self.addCleanup(self._tmp.cleanup)

  def test_commit_versions_rollback(self):
    v1, err = _commit_user_dbc("test_car", BASE_DBC)
    self.assertIsNone(err)
    time.sleep(0.01)
    other = BASE_DBC.replace("Checksum", "Crc")
    v2, err = _commit_user_dbc("test_car", other)
    self.assertIsNone(err)
    self.assertNotEqual(v1, v2)

    versions = _list_versions("test_car")
    self.assertEqual(versions[0]["version"], "current")
    self.assertTrue(versions[0]["current"])
    self.assertEqual({v["version"] for v in versions}, {"current", v1, v2})

    rolled, err = _rollback_user_dbc("test_car", v1)
    self.assertIsNone(err)
    self.assertNotEqual(rolled, v1)  # rollback registers a NEW version
    current = Path(self._tmp.name) / "test_car.dbc"
    self.assertEqual(current.read_text(encoding="utf-8"), BASE_DBC)

  def test_rollback_invalid_version(self):
    _text, err = _rollback_user_dbc("test_car", "not-a-version")
    self.assertEqual(err, "invalid version")
    _text, err = _rollback_user_dbc("test_car", "20260101000000")
    self.assertTrue(err and err.startswith("version not found"))

  def test_history_pruned_to_keep_limit(self):
    for i in range(13):
      _version, _err = _commit_user_dbc("prune_car", f"BO_ {10 + i} M{i}: 8 Vector__XXX\n SG_ S : 0|8@1+ (1,0) [0|0] \"\" Vector__XXX\n")
      time.sleep(0.01)
    history = sorted((Path(self._tmp.name) / "prune_car").glob("prune_car.*.dbc"))
    self.assertLessEqual(len(history), dbc_edit._USER_DBC_HISTORY_KEEP)

  def test_commit_name_with_path_separators_is_sanitized(self):
    """Security: path separators must never survive into the stored filename."""
    user_dir = Path(self._tmp.name)
    for raw in ("../evil", "..\\..\\evil", "a/b/c"):
      name = _safe_dbc_name(raw)
      self.assertIsNotNone(name, f"name {raw!r} unexpectedly rejected")
      self.assertNotIn("/", name)
      self.assertNotIn("\\", name)
      version, err = _commit_user_dbc(name, BASE_DBC)
      self.assertIsNone(err)
      # The naive traversal target (user_dir.parent/<leaf>.dbc) must not exist.
      leaf = raw.replace("\\", "/").split("/")[-1]
      self.assertFalse((user_dir.parent / f"{leaf}.dbc").exists(), f"traversal escape via {raw!r}")
      self.assertTrue((user_dir / f"{name}.dbc").exists())

  def test_versions_for_never_committed_name(self):
    self.assertEqual(_list_versions("ghost_car"), [])
    _current, history = _user_dbc_paths("ghost_car")
    self.assertFalse(_current.exists())
    self.assertEqual(history, [])


async def _no_llm(*_args, **_kwargs) -> dict:
  return {"ok": False, "error": "LLM disabled in tests"}


class DbcEditEndpointsTest(AioHTTPTestCase):
  """HTTP endpoints with a temp user dir and the LLM pass disabled."""

  def setUp(self):
    self._tmp = tempfile.TemporaryDirectory()
    self._env = patch.dict(os.environ, {"AI_USER_DBC_DIR": self._tmp.name})
    self._env.start()
    self.addCleanup(self._env.stop)
    super().setUp()
    self.addCleanup(self._tmp.cleanup)

  async def get_application(self) -> web.Application:
    app = web.Application()
    app.router.add_post("/api/cabana/dbc/ai/infer", dbc_edit.api_dbc_ai_infer)
    app.router.add_post("/api/cabana/dbc/ai/edit", dbc_edit.api_dbc_ai_edit)
    app.router.add_post("/api/cabana/dbc/commit", dbc_edit.api_dbc_commit)
    app.router.add_get("/api/cabana/dbc/versions", dbc_edit.api_dbc_versions)
    app.router.add_post("/api/cabana/dbc/rollback", dbc_edit.api_dbc_rollback)
    return app

  @unittest_run_loop
  async def test_commit_versions_rollback_flow(self):
    resp = await self.client.post("/api/cabana/dbc/commit", json={"name": "flow_car", "dbc_text": BASE_DBC})
    self.assertEqual(resp.status, 200)
    body = await resp.json()
    self.assertTrue(body["ok"])
    v1 = body["version"]

    resp = await self.client.post("/api/cabana/dbc/commit", json={"name": "flow_car", "dbc_text": "BO_ 1 Bad\n SG_ x : 0|x@1+ (1,0) [0|0] \"\" X\n"})
    self.assertEqual(resp.status, 422)

    resp = await self.client.post("/api/cabana/dbc/commit", json={"name": "1bad", "dbc_text": BASE_DBC})
    self.assertEqual(resp.status, 400)

    resp = await self.client.get("/api/cabana/dbc/versions", params={"name": "flow_car"})
    self.assertEqual(resp.status, 200)
    versions = (await resp.json())["versions"]
    self.assertEqual(versions[0]["version"], "current")
    self.assertIn(v1, {v["version"] for v in versions})

    await asyncio.sleep(0.01)
    resp = await self.client.post("/api/cabana/dbc/rollback", json={"name": "flow_car", "version": v1})
    self.assertEqual(resp.status, 200)
    rolled = (await resp.json())["version"]
    self.assertNotEqual(rolled, v1)

    resp = await self.client.post("/api/cabana/dbc/rollback", json={"name": "flow_car", "version": "999"})
    self.assertEqual(resp.status, 404)

  @unittest_run_loop
  async def test_ai_edit_with_ops(self):
    resp = await self.client.post("/api/cabana/dbc/ai/edit", json={
      "base_dbc": BASE_DBC,
      "ops": [{"op": "rename", "target": "380.Counter", "payload": {"new_name": "RollCnt"}}],
    })
    self.assertEqual(resp.status, 200)
    body = await resp.json()
    self.assertTrue(body["ok"])
    self.assertEqual(body["op_errors"], [])
    self.assertIn("SG_ RollCnt :", body["dbc_text"])
    self.assertIn("- SG_ Counter", body["diff"])
    self.assertIn("+ SG_ RollCnt", body["diff"])
    self.assertTrue(body["validation"]["parse_ok"])

  @unittest_run_loop
  async def test_ai_edit_requires_base_and_ops(self):
    resp = await self.client.post("/api/cabana/dbc/ai/edit", json={})
    self.assertEqual(resp.status, 400)
    resp = await self.client.post("/api/cabana/dbc/ai/edit", json={"base_dbc": BASE_DBC})
    self.assertEqual(resp.status, 400)
    resp = await self.client.post("/api/cabana/dbc/ai/edit", json={"base_dbc": "NoSuchDbcName", "ops": [{"op": "remove", "target": "1.A"}]})
    self.assertEqual(resp.status, 404)

  @unittest_run_loop
  async def test_ai_infer_with_mocked_frames(self):
    frames = _infer_frames()
    with patch.object(dbc_edit, "_query_frames", return_value=(frames, None)), \
         patch("ai.services.cabana.ai_explain._cabana_ai_complete", new=_no_llm):
      resp = await self.client.post("/api/cabana/dbc/ai/infer", json={"route": "r--1--0", "address": ADDR, "sample_limit": 256})
    self.assertEqual(resp.status, 200)
    body = await resp.json()
    self.assertTrue(body["ok"])
    self.assertFalse(body["llm_used"])
    self.assertEqual(body["sample_count"], len(frames))
    kinds = {c["kind"] for c in body["candidates"]}
    self.assertIn("counter", kinds)
    self.assertIn("bool", kinds)
    self.assertTrue(body["validation"]["decode_report"]["ok"])
    self.assertIn("SG_ S0_8 :", body["dbc_text_draft"])

  @unittest_run_loop
  async def test_ai_infer_missing_frames(self):
    with patch.object(dbc_edit, "_query_frames", return_value=(None, "Route not found")):
      resp = await self.client.post("/api/cabana/dbc/ai/infer", json={"route": "nope", "address": ADDR})
    self.assertEqual(resp.status, 404)
    with patch.object(dbc_edit, "_query_frames", return_value=([], None)):
      resp = await self.client.post("/api/cabana/dbc/ai/infer", json={"route": "empty", "address": ADDR})
    self.assertEqual(resp.status, 404)
    resp = await self.client.post("/api/cabana/dbc/ai/infer", json={"route": "r", "address": "x"})
    self.assertEqual(resp.status, 400)

  @unittest_run_loop
  async def test_ai_infer_constant_payload_unprocessable(self):
    frames = [{
      "time": 1000.0 + i * 0.1, "bus": 0, "address": ADDR, "data": "ff" * 8,
    } for i in range(10)]
    with patch.object(dbc_edit, "_query_frames", return_value=(frames, None)), \
         patch("ai.services.cabana.ai_explain._cabana_ai_complete", new=_no_llm):
      resp = await self.client.post("/api/cabana/dbc/ai/infer", json={"route": "r--1--0", "address": ADDR})
    self.assertEqual(resp.status, 422)


if __name__ == "__main__":
  unittest.main()
