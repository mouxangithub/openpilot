"""Unit tests for op助手 tools (no openpilot runtime required)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))


class TestFingerprintLib(unittest.TestCase):
  def test_extract_hex_ids(self):
    from ai.tools.fingerprint_lib import extract_hex_ids_from_text, extract_observed_fingerprint

    text = "addr=0x50 len=8 data=01 02\nid: 0x140"
    ids = extract_hex_ids_from_text(text)
    self.assertIn("0x50", ids)
    self.assertIn("0x140", ids)
    obs = extract_observed_fingerprint(text)
    self.assertEqual(obs.get(0x50), 8)

  def test_compare_fingerprint_empty(self):
    from ai.tools.fingerprint_lib import compare_fingerprint

    res = compare_fingerprint(hex_ids=[])
    self.assertFalse(res.get("ok"))


class TestAdaptationSignals(unittest.TestCase):
  def test_suggest_signals_invalid(self):
    try:
      from ai.tools.adaptation import suggest_signals_for_adaptation
      res = suggest_signals_for_adaptation("")
    except ModuleNotFoundError:
      self.skipTest("cabana dependencies not available")
    self.assertFalse(res.get("ok"))


class TestTuneSnapshot(unittest.TestCase):
  def test_save_and_restore_roundtrip(self):
    try:
      from openpilot.common.params import Params
    except ModuleNotFoundError:
      self.skipTest("openpilot runtime not available")
    from ai.tools.tune_snapshot_store import save_tune_snapshot, restore_tune_snapshot, list_tune_snapshots

    with tempfile.TemporaryDirectory() as td:
      snap_dir = Path(td) / "snaps"
      snap_dir.mkdir()
      import ai.tools.tune_snapshot_store as ts
      orig = ts._SNAPSHOT_DIR
      ts._SNAPSHOT_DIR = str(snap_dir)
      try:
        params = Params()
        # Put a known tune param if exists
        try:
          params.put("dp_lat_alka", "1")
        except Exception:
          self.skipTest("Params not available in this environment")
        saved = save_tune_snapshot(params, label="test")
        self.assertTrue(saved.get("ok"))
        params.put("dp_lat_alka", "0")
        restored = restore_tune_snapshot(params, saved["snapshot"]["id"])
        self.assertTrue(restored.get("ok"))
        snaps = list_tune_snapshots()
        self.assertGreaterEqual(len(snaps.get("snapshots", [])), 1)
      finally:
        ts._SNAPSHOT_DIR = orig


class TestSecocLookup(unittest.TestCase):
  def test_toyota_tier(self):
    from ai.tools.secoc_lookup import lookup_secoc_tier

    res = lookup_secoc_tier("TOYOTA COROLLA TSS2 2019", "toyota")
    self.assertEqual(res.get("tier"), "green")

  def test_non_toyota(self):
    from ai.tools.secoc_lookup import lookup_secoc_tier

    res = lookup_secoc_tier("HONDA CIVIC", "honda")
    self.assertEqual(res.get("tier"), "n/a")


class TestCarPortingTools(unittest.TestCase):
  def test_validate_route_empty(self):
    from ai.tools.car_porting_tools import car_porting_auto_fingerprint, _validate_route_ref
    from ai.tools.op_run import resolve_route_ref

    self.assertEqual(_validate_route_ref(""), "route is required")
    self.assertEqual(_validate_route_ref("../x"), "Invalid route (path traversal)")
    res = car_porting_auto_fingerprint("")
    self.assertFalse(res.get("ok"))
    self.assertEqual(resolve_route_ref("abc|2024-01-01--12-00-00/2"), "abc|2024-01-01--12-00-00/2")


class TestManeuverTools(unittest.TestCase):
  def test_maneuver_mode_status(self):
    try:
      from openpilot.common.params import Params
    except ModuleNotFoundError:
      self.skipTest("openpilot runtime not available")
    from ai.tools.maneuver_tools import maneuver_mode_status
    res = maneuver_mode_status()
    self.assertTrue(res.get("ok"))
    self.assertIn("longitudinal_maneuver_mode", res)


class TestRouteTools(unittest.TestCase):
  def test_search_local_routes_empty(self):
    from ai.tools.route_tools import search_local_routes_for_can
    res = search_local_routes_for_can([])
    self.assertFalse(res.get("ok"))


class TestPlotjugglerTools(unittest.TestCase):
  def test_read_dbc_platform_map(self):
    try:
      from ai.tools.plotjuggler_tools import read_dbc_platform_map
      res = read_dbc_platform_map(limit=5)
    except ModuleNotFoundError:
      self.skipTest("opendbc not available")
    if res.get("ok"):
      self.assertGreater(res.get("count", 0), 0)


class TestCommaCloudTools(unittest.TestCase):
  def test_comma_auth_status(self):
    from ai.tools.comma_cloud_tools import comma_auth_status
    res = comma_auth_status()
    self.assertTrue(res.get("ok"))
    self.assertIn("authenticated", res)


class TestHostEnv(unittest.TestCase):
  def test_pc_dev_on_windows(self):
    from ai.system.host_env import get_host_environment, is_pc_dev
    # Dev workspace without /TICI is treated as PC
    self.assertTrue(is_pc_dev())
    env = get_host_environment()
    self.assertTrue(env.get("ok"))
    self.assertEqual(env.get("host_kind"), "pc_dev")

  def test_paths_module(self):
    from ai.system.paths import openpilot_root, path_summary, routes_dir

    root = openpilot_root()
    self.assertTrue((root / "ai").is_dir())
    summary = path_summary()
    self.assertIn("openpilot_root", summary)
    self.assertIn("routes_dir", summary)
    self.assertIsInstance(routes_dir(), str)


class TestPcDevTools(unittest.TestCase):
  def test_require_pc_on_dev(self):
    from ai.tools.pc_dev_tools import pc_launch_replay
    res = pc_launch_replay("demo", demo=True)
    # May fail if binary not built, but should not be "comma device only"
    self.assertNotIn("only available on PC", (res.get("error") or "").lower())

  def test_capture_route_context_invalid(self):
    from ai.tools.pc_dev_tools import pc_capture_route_context
    res = pc_capture_route_context("")
    self.assertFalse(res.get("ok"))

  def test_replay_viz_stream_bad_viz(self):
    from ai.tools.pc_dev_tools import pc_launch_replay_viz_stream
    res = pc_launch_replay_viz_stream("demo", demo=True, viz="invalid")
    self.assertFalse(res.get("ok"))


class TestMpcReport(unittest.TestCase):
  def test_mpc_script_present(self):
    from ai.tools.op_run import OPENPILOT_ROOT
    script = OPENPILOT_ROOT / "tools" / "longitudinal_maneuvers" / "mpc_longitudinal_tuning_report.py"
    self.assertTrue(script.is_file())


class TestPcToolSessions(unittest.TestCase):
  def test_session_roundtrip(self):
    from ai.system.pc_tool_sessions import create_session, get_session, list_sessions

    rec = create_session(
      tool="test",
      launch_params={"route": "demo", "demo": True},
      command=["echo", "test"],
      pid=os.getpid(),
      route=None,
      capture_data=False,
    )
    sid = rec["session_id"]
    self.assertTrue(sid)
    listed = list_sessions(limit=5)
    self.assertTrue(listed.get("ok"))
    got = get_session(sid, refresh_process=True)
    self.assertTrue(got.get("ok"))
    self.assertEqual(got.get("tool"), "test")
    self.assertTrue(got.get("alive"))


class TestWorkflows(unittest.TestCase):
  def test_list_workflows(self):
    from ai.tools.workflows import list_workflows, workflow_system_prompt

    wfs = list_workflows()
    self.assertGreater(len(wfs), 0)
    self.assertTrue(workflow_system_prompt("engage_triage"))


class TestCommaDocsRag(unittest.TestCase):
  def test_comma_docs_structure(self):
    from ai.tools.comma_docs_rag import COMMA_DOCS_RAG

    self.assertGreaterEqual(len(COMMA_DOCS_RAG), 9)
    for doc in COMMA_DOCS_RAG:
      self.assertTrue(doc["id"].startswith("builtin_op_"))
      self.assertTrue(doc.get("refresh"))
      self.assertTrue(doc.get("text", "").strip())


class TestDevAssets(unittest.TestCase):
  def test_list_dev_assets(self):
    from ai.tools.dev_assets import list_dev_assets, resolve_dev_asset

    res = list_dev_assets(limit=5)
    self.assertTrue(res.get("ok"))
    self.assertIn("reports", res)
    self.assertIn("exports", res)
    self.assertIsNone(resolve_dev_asset("reports", "../evil"))
    self.assertIsNone(resolve_dev_asset("bad", "x.html"))


class TestVizLayouts(unittest.TestCase):
  def test_plotjuggler_layouts(self):
    from ai.tools.viz_layout_tools import list_plotjuggler_layouts, list_jotpluggler_layouts

    pj = list_plotjuggler_layouts()
    self.assertTrue(pj.get("ok"))
    jp = list_jotpluggler_layouts()
    self.assertTrue(jp.get("ok"))


class TestSystemInfo(unittest.TestCase):
  def test_get_build_info(self):
    from ai.tools.system_info_tools import get_build_info

    info = get_build_info()
    self.assertTrue(info.get("ok"))
    self.assertIn("git", info)
    self.assertTrue(info["git"].get("commit") or info["git"].get("branch"))


class TestRouteAnalysis(unittest.TestCase):
  def test_route_can_stats_invalid(self):
    from ai.tools.route_analysis_tools import route_can_stats, compare_route_signals

    self.assertFalse(route_can_stats("").get("ok"))
    self.assertFalse(compare_route_signals("", "b").get("ok"))

  def test_batch_route_summary(self):
    try:
      from ai.tools.route_analysis_tools import batch_route_summary
      res = batch_route_summary(limit=0)
    except ModuleNotFoundError:
      self.skipTest("openpilot runtime not available")
    self.assertIn("ok", res)


class TestWorkflowsBatch2(unittest.TestCase):
  def test_compare_and_batch_workflows(self):
    from ai.tools.workflows import list_workflows, workflow_system_prompt

    ids = {w["id"] for w in list_workflows()}
    self.assertIn("compare_routes_tune", ids)
    self.assertIn("batch_route_review", ids)
    self.assertTrue(workflow_system_prompt("compare_routes_tune"))


class TestDevsyncStatus(unittest.TestCase):
  def test_pc_devsync_status_local(self):
    from ai.tools.devops_tools import pc_devsync_status

    res = pc_devsync_status()
    self.assertTrue(res.get("ok"))
    self.assertIn("local_ready", res)
    self.assertIn("issues", res)
    self.assertIn("suggested_command", res)

  def test_pc_devsync_status_bad_ip(self):
    from ai.tools.devops_tools import pc_devsync_status

    res = pc_devsync_status(device_ip="bad ip!")
    self.assertFalse(res.get("ok"))


class TestExtensionTools(unittest.TestCase):
  def test_git_status(self):
    from ai.tools.git_tools import git_status
    res = git_status()
    self.assertIn("ok", res)

  def test_git_list_branches(self):
    from ai.tools.git_tools import git_list_branches
    res = git_list_branches(limit=10)
    self.assertTrue(res.get("ok"))
    self.assertIn("local", res)

  def test_git_checkout_invalid(self):
    from ai.tools.git_tools import git_checkout
    res = git_checkout(branch="bad branch name")
    self.assertFalse(res.get("ok"))

  def test_audit_trail_roundtrip(self):
    import ai.tools.audit_store as audit
    with tempfile.TemporaryDirectory() as td:
      audit._AUDIT_PATH = Path(td) / "audit.jsonl"
      audit.record_audit(action="test", tool="unit", detail={"x": 1})
      out = audit.list_audit_trail(limit=5)
      self.assertTrue(out.get("ok"))
      self.assertGreaterEqual(out.get("count", 0), 1)

  def test_compare_tune_ab_invalid(self):
    from ai.tools.route_analysis_tools import compare_tune_ab
    res = compare_tune_ab("", "b")
    self.assertFalse(res.get("ok"))

  def test_extension_meta_registered(self):
    from ai.tools.extensions import EXTENSION_TOOL_META, EXTENSION_SCHEMAS
    self.assertIn("reboot_device", EXTENSION_TOOL_META)
    self.assertIn("list_plugins", EXTENSION_TOOL_META)
    self.assertIn("git_checkout", EXTENSION_TOOL_META)
    self.assertIn("score_route_tune", EXTENSION_TOOL_META)
    names = {s["function"]["name"] for s in EXTENSION_SCHEMAS}
    self.assertIn("network_diagnostics", names)
    self.assertIn("git_list_branches", names)
    self.assertIn("route_event_timeline", names)
    self.assertIn("git_push", names)
    self.assertIn("search_memory_semantic", names)

  def test_plugins_registry(self):
    from ai.plugins.loader import list_plugins
    res = list_plugins()
    self.assertTrue(res.get("ok"))
    self.assertTrue(any(p.get("id") == "core-extensions" for p in res.get("plugins", [])))
    self.assertTrue(any(p.get("id") == "device-extras" for p in res.get("plugins", [])))

  def test_skills_registry_has_new_entries(self):
    from ai.skills.loader import list_skills
    ids = {s["id"] for s in list_skills()}
    for sid in (
      "network-diagnostics", "post-tune-validation", "dp-brand-hyundai",
      "dp-brand-subaru", "dp-brand-gm", "dp-brand-lexus", "dp-brand-ford",
      "dp-brand-nissan", "dp-brand-mazda", "dp-brand-chrysler", "dp-brand-tesla",
    ):
      self.assertIn(sid, ids)

  def test_batch_compare_empty(self):
    from ai.tools.route_scoring_tools import batch_compare_routes_tune
    res = batch_compare_routes_tune([])
    self.assertFalse(res.get("ok"))

  def test_ota_status(self):
    from ai.tools.ota_tools import ota_status

    class _P:
      def get(self, key):
        return b"test" if key == "Version" else None

    res = ota_status(_P())
    self.assertTrue(res.get("ok"))

  def test_ssh_blocks_destructive(self):
    from ai.tools.ssh_tools import ssh_readonly_exec
    res = ssh_readonly_exec(host="1.2.3.4", command="rm -rf /")
    self.assertFalse(res.get("ok"))

  def test_plotjuggler_apply_missing(self):
    from ai.tools.viz_layout_tools import plotjuggler_apply_layout
    res = plotjuggler_apply_layout("__no_such_layout__")
    self.assertFalse(res.get("ok"))

  def test_scheduler_defaults_helper(self):
    try:
      import ai.tools.scheduler as sched
    except ModuleNotFoundError:
      self.skipTest("openpilot runtime not available")
    with tempfile.TemporaryDirectory() as td:
      try:
        from openpilot.common.params import Params
      except ModuleNotFoundError:
        self.skipTest("openpilot runtime not available")
      params = Params()
      # Only verify function runs without error when tasks may already exist
      res = sched.ensure_default_scheduler_tasks(params)
      self.assertTrue(res.get("ok"))

  def test_model_router_auto(self):
    from ai.model_router import resolve_chat_config
    from ai.client import AIConfig
    base = AIConfig(provider="openai", model="gpt-test", api_key="k")
    class _P:
      def get(self, key):
        return None
    cfg = resolve_chat_config(base, _P(), workflow_id="post_tune_validation", user_text="调参")
    self.assertEqual(cfg.model, base.model)

  def test_tune_passport(self):
    import ai.tools.tune_passport_store as tp
    with tempfile.TemporaryDirectory() as td:
      path = Path(td) / "ai_tune_passport.jsonl"
      orig = tp._passport_path
      tp._passport_path = lambda: path
      try:
        tp.record_tune_passport(action="test", params_changed={"dp_lon_acm": 1})
        out = tp.list_tune_passport(limit=5)
        self.assertTrue(out.get("ok"))
        self.assertGreaterEqual(out.get("count", 0), 1)
      finally:
        tp._passport_path = orig

  def test_generate_pr_draft(self):
    from ai.tools.adaptation_pr_tools import generate_adaptation_pr_draft
    res = generate_adaptation_pr_draft(project_name="test-car")
    self.assertTrue(res.get("ok"))
    self.assertIn("markdown", res)

  def test_device_health(self):
    from ai.tools.device_health_tools import device_health
    res = device_health()
    self.assertTrue(res.get("ok"))

  def test_git_fetch(self):
    from ai.tools.git_tools import git_fetch
    res = git_fetch()
    self.assertIn("ok", res)

  def test_workflows_post_tune(self):
    from ai.tools.workflows import get_workflow
    wf = get_workflow("post_tune_validation")
    self.assertIsNotNone(wf)
    self.assertIn("score_tune_session", " ".join(wf.get("steps", [])))


class TestTskGuidance(unittest.TestCase):
  def test_matcher_next_steps_insufficient(self):
    from ai.tsk.guidance import enrich_failure_response, matcher_next_steps

    steps = matcher_next_steps({"status": "insufficient_oracle"})
    self.assertTrue(any("can" in s.lower() for s in steps))
    enriched = enrich_failure_response({"ok": False, "status": "not_found", "message": "x"})
    self.assertIn("debug", enriched)
    self.assertIn("next_steps", enriched)


class TestTskServiceHelpers(unittest.TestCase):
  def test_wait_for_idle_can(self):
    from ai.tsk import service as tsk_service

    with tsk_service.can_lock:
      tsk_service.can_state.update(
        status="complete", ready=True, message="ok", sync_count=50, protected_count=30,
      )
    res = tsk_service.wait_for_job(job="can", timeout_seconds=1)
    self.assertTrue(res.get("ok"))
    self.assertEqual(res.get("status"), "complete")

  def test_cancel_job_when_idle(self):
    from ai.tsk import service as tsk_service

    res = tsk_service.run_cancel_job("can")
    self.assertFalse(res.get("ok"))

  def test_offroad_alert_status(self):
    from ai.tsk import service as tsk_service

    res = tsk_service.get_offroad_alert_status()
    self.assertTrue(res.get("ok"))
    self.assertIn("alert_active", res)


class TestTskToolsMeta(unittest.TestCase):
  def test_extension_tools_registered(self):
    from ai.tools.extensions import EXTENSION_TOOL_META

    for name in (
      "tsk_wait_for_job",
      "tsk_cancel_job",
      "tsk_restart_pandad",
      "tsk_run_pipeline",
      "get_tsk_offroad_alert_status",
    ):
      self.assertIn(name, EXTENSION_TOOL_META)


if __name__ == "__main__":
  unittest.main()
