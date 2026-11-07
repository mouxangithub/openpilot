"""Independent QA contracts for G3/G6/G7/G8 and Web settings."""
from __future__ import annotations

import asyncio
import importlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import ai.tests.bootstrap_pc  # noqa: F401
from ai.bundle.profile import ProfileError, apply_patch, compose_profile
from ai.core.session.log import EventType, SessionLog
from ai.core.session.pruner import ToolResultPruner, prune_events
from ai.schedule.runtime import SchedulerRuntime
from ai.schedule.store import ScheduleStore
from ai.subagent.capabilities import SubagentCapabilities, validate_request
from ai.subagent.models import SubagentTask


class FakeBundle:
  def __init__(self, extra=None):
    self.extra = extra or {}


class FakeBundleStore:
  def __init__(self, bundles=None):
    self.bundles = bundles or {}

  def get_bundle(self, bundle_id):
    return self.bundles.get(bundle_id)


class CompactionReplayContracts(unittest.TestCase):
  def test_unicode_prune_is_replay_safe_and_idempotent(self) -> None:
    log = SessionLog("qa-compaction", strict=True)
    text = "始" + "😀" * 60 + "终"
    log.append(EventType.TOOL_RESULT, {"tool_call_id": "c1", "content": text},
               surface_op="append")
    pruner = ToolResultPruner(threshold_chars=60, head_chars=3, tail_chars=3)
    first = pruner.prune_session(log)
    second = pruner.prune_session(log)
    self.assertEqual(len(first.pruned), 1)
    self.assertEqual(second.pruned, [])
    self.assertEqual(len(log.surface), 1)
    self.assertEqual(prune_events(list(log.events))["shadowedSeqs"], [0])
    self.assertIn("😀", log.surface[0].data["content"])


class SchedulerRestartContracts(unittest.TestCase):
  def test_persisted_schedule_survives_store_restart_and_dispatches_once(self) -> None:
    now = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory() as tmp:
      store = ScheduleStore(tmp)
      record = store.create_after("重启后提醒", 1,
                                  now=datetime(2026, 9, 5, 11, 59, tzinfo=timezone.utc))
      restarted = ScheduleStore(tmp)
      self.assertEqual(restarted.get(record.id).prompt, "重启后提醒")
      seen = []

      async def dispatch(item):
        seen.append(item.id)

      asyncio.run(SchedulerRuntime("s", store=restarted, dispatch=dispatch,
                                   now_fn=lambda: now).tick())
      self.assertEqual(seen, [record.id])
      self.assertIsNone(restarted.get(record.id))
      asyncio.run(SchedulerRuntime("s", store=restarted, dispatch=dispatch,
                                   now_fn=lambda: now).tick())
      self.assertEqual(seen, [record.id])


class SubagentCapabilityContracts(unittest.TestCase):
  def test_all_capability_requirements_refuse_in_priority_order(self) -> None:
    task = SubagentTask(id="t", agent_id="a", prompt="p", tools=["x"],
                        output_schema={"type": "object"},
                        metadata={"persona": "p", "agent_options": {}})
    rejection = validate_request(task, SubagentCapabilities())
    self.assertIsNotNone(rejection)
    self.assertEqual(rejection.code, "SUBAGENT_CAPABILITY_MISSING")
    self.assertEqual(rejection.capability, "outputSchema")

  def test_task_lineage_fields_round_trip(self) -> None:
    task = SubagentTask(id="child", agent_id="a", prompt="p", parent_id="parent",
                        depth=2, max_depth=4, metadata={"origin": "spawn"})
    restored = SubagentTask.from_dict(task.to_dict())
    self.assertEqual(restored.parent_id, "parent")
    self.assertEqual(restored.depth, 2)
    self.assertEqual(restored.metadata["origin"], "spawn")


class ProfileCompositionContracts(unittest.TestCase):
  def test_patch_order_and_idempotence(self) -> None:
    base = apply_patch([], {"include": [{"id": "x", "options": {"a": 1}}]})
    merged = apply_patch(base, {"include": [{"id": "x", "options": {"b": 2}}]})
    self.assertEqual(merged, [{"id": "x", "options": {"a": 1, "b": 2}}])
    self.assertEqual(apply_patch(merged, None), merged)
    self.assertEqual(apply_patch(merged, {"exclude": ["x"]}), [])

  def test_compose_conflict_diagnostics(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
      base = Path(tmp)
      profile = base / "testprof"
      profile.mkdir()
      (profile / "profile.json").write_text(
        json.dumps({"name": "testprof", "bundles": ["dup", "dup"]}), encoding="utf-8")
      (profile / "cordis.patch.json").write_text(
        json.dumps({"include": [{"id": "z"}]}), encoding="utf-8")
      store = FakeBundleStore({"dup": FakeBundle({"patch": {"include": ["a"]}})})
      with self.assertRaises(ProfileError) as cm:
        compose_profile("testprof", base=base, store=store)
      self.assertEqual(cm.exception.code, "duplicate_bundle")

  def test_compose_dry_run_preview_layers(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
      base = Path(tmp)
      profile = base / "previewprof"
      profile.mkdir()
      (profile / "profile.json").write_text(
        json.dumps({"name": "previewprof", "bundles": ["b1", "b2"]}), encoding="utf-8")
      (profile / "cordis.patch.json").write_text(
        json.dumps({"include": [{"id": "z", "options": {"final": True}}]}), encoding="utf-8")
      store = FakeBundleStore({
        "b1": FakeBundle({"patch": {"include": [{"id": "x", "options": {"src": "b1"}}]}}),
        "b2": FakeBundle({"patch": {"include": [{"id": "y", "options": {"src": "b2"}}]}}),
      })
      out = compose_profile("previewprof", base=base, store=store)
      self.assertTrue(out["ok"])
      ids = [e["id"] for e in out["entries"]]
      self.assertEqual(ids, ["x", "y", "z"])
      self.assertEqual(len(out["layers"]), 3)
      self.assertEqual(out["layers"][0]["source"], "bundle:b1")
      self.assertEqual(out["layers"][2]["source"], "profile")
      self.assertFalse(out["entries"][2]["options"]["final"] is None)


class ConfigRegistryContracts(unittest.TestCase):
  def test_register_get_all_roundtrip(self) -> None:
    from ai.config.registry import ConfigRegistry, SchemaField
    r = ConfigRegistry(schema_dir=str(Path(tempfile.mkdtemp())))
    r.register_schema("conversation", {
      "ai_model": SchemaField("ai_model", "enum", default="flash", enum=["flash", "pro"]),
      "ai_max_tokens": SchemaField("ai_max_tokens", "number", min=1, max=100000),
    }, revision=3)
    schema = r.get_schema("conversation")
    self.assertEqual(schema["revision"], 3)
    self.assertEqual(schema["fields"]["ai_model"]["type"], "enum")
    self.assertEqual(schema["fields"]["ai_max_tokens"]["max"], 100000)
    self.assertIn("conversation", r.all())

  def test_stale_revision_downgrade_refused(self) -> None:
    from ai.config.registry import ConfigRegistry, SchemaField
    r = ConfigRegistry(schema_dir=str(Path(tempfile.mkdtemp())))
    r.register_schema("ns", {"k": SchemaField("k", "string")}, revision=5)
    r.register_schema("ns", {"k": SchemaField("k", "number")}, revision=4)
    self.assertEqual(r.get_schema("ns")["revision"], 5)
    self.assertEqual(r.get_schema("ns")["fields"]["k"]["type"], "string")


class ConfigValidatorContracts(unittest.TestCase):
  def test_unknown_key_and_out_of_range_return_stable_code(self) -> None:
    from ai.config.validator import validate_payload
    from ai.core.errors import ERR_CONFIG_INVALID
    schema = {"fields": {"n": {"key": "n", "type": "number", "min": 0, "max": 10}}}
    errors = validate_payload(schema, {"n": 99, "bogus": 1})
    codes = {e["field"]: e["code"] for e in errors}
    self.assertEqual(codes["n"], ERR_CONFIG_INVALID)
    self.assertEqual(codes["bogus"], ERR_CONFIG_INVALID)

  def test_type_enum_and_valid_pass(self) -> None:
    from ai.config.validator import validate_payload
    schema = {"fields": {
      "m": {"key": "m", "type": "enum", "enum": ["a", "b"]},
      "on": {"key": "on", "type": "boolean"},
      "t": {"key": "t", "type": "string"},
    }}
    self.assertEqual(validate_payload(schema, {"m": "a", "on": True, "t": "x"}), [])
    self.assertEqual([e["field"] for e in validate_payload(schema, {"m": "c"})], ["m"])
    self.assertEqual([e["field"] for e in validate_payload(schema, {"on": "yes"})], ["on"])


class CompactionServiceContracts(unittest.TestCase):
  def test_compaction_lifecycle_and_single_replace(self) -> None:
    import asyncio
    from ai.core.session.compaction import CompactionService
    log = SessionLog("qa-compact-svc")
    big = "😀" * 9000
    log.append(EventType.TOOL_RESULT, {"tool_call_id": "c", "content": big}, surface_op="append")
    svc = CompactionService(log, config=None)

    async def llm_stream(messages):
      return "real summary"

    svc.llm_stream = llm_stream
    result = asyncio.run(svc.compact_now(None))
    self.assertIsNotNone(result)
    self.assertTrue(result.compaction_id)
    self.assertTrue(result.summary)
    self.assertIn(result.replacement_seq, [e.seq for e in log.events])
    replace_events = [e for e in log.events if e.type == EventType.USER_MESSAGE]
    self.assertEqual(len(replace_events), 1, "exactly one surface REPLACE produced")

  def test_lock_prevents_reentrant_compact(self) -> None:
    import asyncio
    from ai.core.session.compaction import CompactionService
    log = SessionLog("qa-compact-lock")
    svc = CompactionService(log)
    svc._locked = True
    self.assertIsNone(asyncio.run(svc.compact_now(None)))


class ErrorCodeContracts(unittest.TestCase):
  NEW_CODES = {
    "ERR_CONFIG_INVALID": "CONFIG_INVALID",
    "ERR_CONFIG_STALE": "CONFIG_STALE",
    "ERR_SCHEDULE_INVALID": "SCHEDULE_INVALID",
    "ERR_SUBAGENT_CAPABILITY": "SUBAGENT_CAPABILITY",
    "ERR_PROFILE_CONFLICT": "PROFILE_CONFLICT",
    "ERR_STARTUP_DIAG": "STARTUP_DIAG",
  }

  def test_design_error_codes_exist_in_core_errors(self) -> None:
    """Design (system_design.md) requires six new stable codes in core.errors."""
    errors = importlib.import_module("ai.core.errors")
    missing = {name for name in self.NEW_CODES if not hasattr(errors, name)}
    self.assertFalse(missing, f"missing error-code constants in core/errors.py: {missing}")

  def test_tool_error_contract(self) -> None:
    from ai.core.errors import tool_error
    err = tool_error("bad", code="X")
    self.assertEqual(err, {"ok": False, "error": "bad", "error_code": "X"})


class NotImplementedSurfaceContracts(unittest.TestCase):
  """Architect-specified seams not yet present in the codebase.

  These fail loudly (no silent skip) so the report exposes implementation gaps
  without pretending the surface exists. Absence is routed to the engineer.
  """

  MODULES = {
    "subagent.lineage": "subagent/lineage.py",
    "bundle.profile_compose": "bundle/profile_compose.py",
  }

  def test_pending_backend_modules_importable(self) -> None:
    missing = {}
    for mod, path in self.MODULES.items():
      try:
        importlib.import_module(f"ai.{mod}")
      except ModuleNotFoundError:
        missing[mod] = path
    self.assertFalse(missing, f"design-specified modules not implemented: {missing}")


class WebSettingsStaticContracts(unittest.TestCase):
  ROOT = Path(__file__).resolve().parents[1]
  DOMAINS = {"conversation", "evolution", "vehicle", "data_backup", "scheduler", "dev_diagnostics"}
  MODULES = {"registry.js", "schema.js", "render.js", "save.js", "search.js",
             "dangerous.js", "scheduler-view.js", "index.js"}

  def test_settings_modules_and_six_domains_exist(self) -> None:
    settings = self.ROOT / "web" / "static" / "js" / "settings"
    missing = sorted(name for name in self.MODULES if not (settings / name).is_file())
    self.assertFalse(missing, f"missing settings modules: {missing}")
    source = "\n".join((settings / name).read_text(encoding="utf-8") for name in self.MODULES)
    missing_domains = [d for d in self.DOMAINS if d not in source]
    self.assertFalse(missing_domains, f"6-domain ids not registered in settings js: {missing_domains}")

  def test_index_contains_settings_root_and_search(self) -> None:
    index = (self.ROOT / "web" / "static" / "index.html").read_text(encoding="utf-8")
    self.assertRegex(index, r"settings")
    self.assertRegex(index, r"search")


if __name__ == "__main__":
  unittest.main()
