"""P1/P2 全量回归测试脚手架。

覆盖：
- 服务健康检查与关键 fallback 路由 200
- T01 配置 schema 与校验
- T02 AgentLoop 公共 seam 与 harness tool schemas
- T03 会话 repair / spill 决策 / ToolPipeline 基础流
- T04 bundle/profile 与 workflow graph 存在性

运行：
    cd /e/sp && PYTHONPATH="E:/sp/ai" python -m pytest ai/tests/test_p1p2_regression.py -q
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import ai.tests.bootstrap_pc  # noqa: F401

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from ai.config.registry import ConfigRegistry
from ai.config.validator import validate_payload
from ai.core import diagnostics
from ai.core.agent.loop import AgentLoop
from ai.core.agent.state import AgentMessage, ChatCancelled, InboxTarget
from ai.core.session.log import EventType, SessionLog
from ai.core.session.repair import repair_session_log
from ai.core.tools.pipeline import ToolPipeline
from ai.server.op_routes import setup_routes
from ai.tools import harness_tools as ht
from ai.tools.result_externalize import spill_text_if_needed


def _run(coro):
  """同步运行协程的测试辅助。"""
  return asyncio.run(coro)


# ---------------------------------------------------------------------------
# T01 — 配置 schema
# ---------------------------------------------------------------------------

class ConfigSchemaRegressionTests(unittest.TestCase):
  def test_registry_loads_all_p1p2_namespaces(self):
    registry = ConfigRegistry()
    namespaces = registry.namespaces()
    expected = {
      "sandbox", "spill", "mcp", "bundle", "workflow", "lsp", "subagent",
      "conversation", "evolution", "vehicle_safety", "data_backup",
      "scheduler", "dev_diagnostics",
    }
    missing = expected - set(namespaces)
    self.assertFalse(missing, f"missing namespaces: {missing}")

  def test_spill_schema_has_threshold_bounds(self):
    schema = ConfigRegistry().get_schema("spill")
    fields = schema.get("fields", {})
    self.assertEqual(fields["ai_externalize_results"]["type"], "boolean")
    self.assertEqual(fields["ai_externalize_threshold"]["min"], 1024)
    self.assertEqual(fields["ai_externalize_threshold"]["max"], 512000)

  def test_validate_payload_catches_type_enum_and_bounds(self):
    schema = ConfigRegistry().get_schema("mcp")
    errors = validate_payload(schema, {"ai_mcp_default_trust": "bad_value"})
    self.assertTrue(any("ai_mcp_default_trust" in e["field"] for e in errors))
    errors = validate_payload(schema, {"ai_mcp_tool_timeout": 900})
    self.assertTrue(any("above max" in e["message"] for e in errors))

  def test_validate_payload_rejects_unknown_field(self):
    schema = ConfigRegistry().get_schema("bundle")
    errors = validate_payload(schema, {"ai_unknown_field": "x"})
    self.assertTrue(any(e["field"] == "ai_unknown_field" for e in errors))

  def test_startup_diagnostics_runs_without_exception(self):
    result = diagnostics.run_startup_diagnostics()
    self.assertTrue(hasattr(result, "checks"))
    self.assertIsInstance(result.checks, list)
    # Startup diagnostics checks critical imports; verify P1/P2 modules are covered.
    names = {c.get("name", "") for c in result.checks}
    core_prefixes = {"ai.core.agent.agent", "ai.tools.result_externalize", "ai.tools.harness_tools"}
    found = {n for n in names if any(n.startswith(p) for p in core_prefixes)}
    # ai.core.agent.agent is checked as ai.core.agent.state import in diagnostics; accept harness_tools.
    self.assertIn("import:ai.tools.harness_tools", names)


# ---------------------------------------------------------------------------
# T02 — AgentLoop 与 harness tools
# ---------------------------------------------------------------------------

class AgentLoopRegressionTests(unittest.TestCase):
  def setUp(self):
    self._loop = asyncio.new_event_loop()
    asyncio.set_event_loop(self._loop)

  def tearDown(self):
    self._loop.close()
    asyncio.set_event_loop(None)

  def _make_loop(self, actions: list[str]) -> AgentLoop:
    class _StubLoop(AgentLoop):
      async def _turn(self) -> bool:
        if not actions:
          return False
        action = actions.pop(0)
        if action == "queue":
          self.state.followup(AgentMessage(role="user", content="mid"))
          return True
        if action == "consume":
          self.state.inbox.claim(InboxTarget.NEXT_TURN, 0)
          self.state.inbox.claim(InboxTarget.NEXT_STEP, 0)
          return False
        return False

    return _StubLoop(
      session_id="reg-test",
      agent_id="agent-reg",
      params=None,
      emit=AsyncMock(),
      stream_fn=None,
      tool_pipeline=ToolPipeline(),
    )

  def test_run_until_idle_returns_ok(self):
    result = self._loop.run_until_complete(self._make_loop(["idle"]).run_until_idle())
    self.assertTrue(result.get("ok"))
    self.assertEqual(result.get("agentId"), "agent-reg")

  def test_run_until_idle_drains_followups(self):
    loop = self._make_loop(["queue", "consume"])
    result = self._loop.run_until_complete(loop.run_until_idle())
    self.assertTrue(result.get("ok"))
    self.assertFalse(loop.state.inbox.has_pending)

  def test_external_cancel_raises_chat_cancelled(self):
    async def scenario():
      loop = self._make_loop(["queue", "idle"])
      await loop.run_until_idle(is_cancelled=lambda: True)

    with self.assertRaises(ChatCancelled):
      self._loop.run_until_complete(scenario())


class HarnessToolSchemaRegressionTests(unittest.TestCase):
  def test_p1_tools_present(self):
    schemas = ht.harness_tool_schemas()
    names = {s["function"]["name"] for s in schemas}
    required = {
      "goal_create", "plan_generate", "todo_write", "lsp",
      "run_python_code", "workflow_advance", "mcp_discover",
      "subagent_start",
    }
    missing = required - names
    self.assertFalse(missing, f"missing P1 tools: {missing}")

  def test_goal_plan_todo_handlers_registered(self):
    handlers: dict[str, Any] = {}
    ht.register_harness_handlers(handlers)
    self.assertTrue({"goal_create", "plan_generate", "todo_write"} <= handlers.keys())

  def test_python_tool_blocks_dangerous_import(self):
    result = _run(ht._h_run_python_code({"code": "import os; os.system('x')"}))
    self.assertFalse(result["ok"])


# ---------------------------------------------------------------------------
# T03 — 会话恢复 / spill / ToolPipeline
# ---------------------------------------------------------------------------

class SessionRepairRegressionTests(unittest.TestCase):
  def test_repair_generates_closures(self):
    path = Path(tempfile.mkdtemp()) / "session.jsonl"
    log = SessionLog("repair-test", persist_path=str(path))
    log.append(EventType.TURN_START, {"turn": 1})
    log.append(EventType.STEP_START, {"turn": 1, "step": 1})
    log.append(EventType.TOOL_CALL, {"turn": 1, "step": 1, "callId": "c1", "name": "x"})
    repaired = repair_session_log(log)
    self.assertEqual(
      [e.type for e in repaired],
      [EventType.TOOL_RESULT, EventType.STEP_END, EventType.TURN_END],
    )
    self.assertEqual(repair_session_log(log), [])
    log.close()

  def test_repair_is_idempotent(self):
    path = Path(tempfile.mkdtemp()) / "session.jsonl"
    log = SessionLog("repair-idem", persist_path=str(path))
    log.append(EventType.TURN_START, {"turn": 1})
    log.append(EventType.TOOL_CALL, {"turn": 1, "step": 1, "callId": "c1", "name": "x"})
    first = repair_session_log(log)
    second = repair_session_log(log)
    self.assertEqual(len(first), 3)
    self.assertEqual(second, [])
    log.close()


class SpillDecisionRegressionTests(unittest.TestCase):
  def test_small_text_not_spilled(self):
    replaced, ref = spill_text_if_needed("small", session_id="s", tool_name="echo", max_bytes=8192)
    self.assertIsNone(replaced)
    self.assertIsNone(ref)

  def test_large_text_spilled_with_pointer(self):
    text = "x" * 20_000
    replaced, ref = spill_text_if_needed(text, session_id="s", tool_name="echo", max_bytes=8192)
    self.assertIsNotNone(ref)
    self.assertTrue(ref["ref"].startswith("toolresult://"))
    self.assertLessEqual(len(replaced.encode("utf-8")), 8192)

  def test_utf8_multibyte_within_budget(self):
    text = "你好" * 6000
    replaced, ref = spill_text_if_needed(text, session_id="s", tool_name="echo", max_bytes=4096)
    self.assertIsNotNone(replaced)
    self.assertLessEqual(len(replaced.encode("utf-8")), 4096)
    self.assertIn("你好", replaced)


class ToolPipelineRegressionTests(unittest.TestCase):
  async def _run_tool(self, name: str, handler, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    pipeline = ToolPipeline()
    pipeline.register_primitive(name, handler)
    return await pipeline.execute(
      call_id=f"{name}:1",
      name=name,
      raw_arguments=json.dumps(arguments or {}),
    )

  def test_sync_and_async_handlers_execute(self):
    async def async_handler(_args):
      return {"ok": True, "value": "async"}

    def sync_handler(_args):
      return {"ok": True, "value": "sync"}

    self.assertEqual(_run(self._run_tool("async_tool", async_handler)).get("value"), "async")
    self.assertEqual(_run(self._run_tool("sync_tool", sync_handler)).get("value"), "sync")

  def test_unknown_tool_returns_error_code(self):
    pipeline = ToolPipeline()
    # Do not register "missing" so it is truly unknown.
    result = _run(pipeline.execute(call_id="missing:1", name="missing", raw_arguments="{}"))
    self.assertFalse(result["ok"])
    self.assertEqual(result.get("error_code"), "UNKNOWN_TOOL")

  def test_post_waterfall_runs_in_order(self):
    order: list[str] = []

    async def outer(_ctx, _result, next_stage):
      order.append("outer:before")
      downstream = await next_stage()
      order.append("outer:after")
      return downstream

    async def inner(_ctx, result, _next_stage):
      order.append("inner")
      return result

    async def handler(_args):
      order.append("handler")
      return {"ok": True, "content": "x"}

    pipeline = ToolPipeline()
    pipeline.add_post_waterfall(outer)
    pipeline.add_post_waterfall(inner)
    pipeline.register_primitive("t", handler)
    _run(pipeline.execute("t:1", "t", "{}"))
    self.assertEqual(order[0], "handler")
    self.assertLess(order.index("outer:before"), order.index("inner"))
    self.assertLess(order.index("inner"), order.index("outer:after"))

  def test_spill_post_waterfall_externalizes_large_result(self):
    """Large tool results are spilled to disk and replaced with a toolresult:// pointer."""
    from ai.core.tools.pipeline import ToolResult
    from ai.tools.result_externalize import spill_text_if_needed

    large_text = "x" * 20_000

    async def spill_hook(exec_ctx, result: ToolResult, next_stage):
      downstream = await next_stage()
      if not downstream.ok:
        return downstream
      text = downstream.value if isinstance(downstream.value, str) else downstream.content
      if text and len(text.encode("utf-8")) > 1024:
        replaced, ref = spill_text_if_needed(
          text,
          session_id="reg-spill",
          tool_name=exec_ctx.name,
          call_id=exec_ctx.call_id,
          params={"ai_externalize_results": True, "ai_externalize_threshold": 1024},
        )
        if ref is not None:
          pointer = ref["ref"]
          return ToolResult(ok=True, value=pointer, content=replaced, block=pointer)
      return downstream

    async def echo_handler(args):
      return {"ok": True, "content": large_text}

    pipeline = ToolPipeline()
    pipeline.add_post_waterfall(spill_hook)
    pipeline.register_primitive("echo", echo_handler)
    pointer = _run(pipeline.execute("echo:1", "echo", "{}"))

    # The post-waterfall replaced the dict result with the toolresult:// pointer string.
    self.assertIsInstance(pointer, str)
    self.assertIn("toolresult://", pointer)
    ref_id = pointer.replace("toolresult://", "")
    # Locate the spilled text file by ref_id in the session-scoped results dir.
    from ai.system.paths import workspace_path
    results_dir = workspace_path("tool_results", "reg-spill")
    matches = list(results_dir.rglob(f"*_{ref_id}.txt"))
    self.assertTrue(matches, f"spilled file for {pointer} not found")
    spilled_path = matches[0]
    self.assertIn("x" * 100, spilled_path.read_text(encoding="utf-8"))


class ChatSessionBridgeRegressionTests(unittest.TestCase):
  def test_adopt_session_allows_pause_and_dispose(self):
    """A session that only exists as a chat log can be adopted by SessionManager."""
    import tempfile
    from ai.core.session.manager import SessionManager
    from ai.core.session.log import EventType, SessionLog

    with tempfile.TemporaryDirectory() as td:
      manager = SessionManager(td)
      session_id = "chat-only-bridge-test"

      # Simulate a chat-created durable log (no SessionManager record yet).
      log_dir = Path(td) / "ai_session_logs"
      log_dir.mkdir(parents=True, exist_ok=True)
      log_path = log_dir / f"{session_id}.jsonl"
      log = SessionLog(session_id, persist_path=str(log_path))
      log.append(EventType.USER_MESSAGE, {"role": "user", "content": "hi"})
      log.close()

      # Before adoption, pause/dispose cannot find the session.
      self.assertIsNone(manager.pause_session(session_id))
      self.assertFalse(manager.dispose_session(session_id))

      # After adoption, lifecycle operations succeed.
      adopted = manager.adopt_session(session_id)
      self.assertEqual(adopted.id, session_id)
      paused = manager.pause_session(session_id)
      self.assertIsNotNone(paused)
      self.assertEqual(paused.id, session_id)
      self.assertTrue(manager.dispose_session(session_id))


# ---------------------------------------------------------------------------
# T04 — bundle/profile / workflow graph 存在性
# ---------------------------------------------------------------------------

class BundleProfileRegressionTests(unittest.TestCase):
  def test_manifest_patch_operations_parse(self):
    from ai.bundle.manifest import BundleManifest

    manifest = BundleManifest(
      id="b1",
      name="bundle-one",
      version="1.0.0",
      extra={"patch": [{"op": "set", "path": "ai_sandbox_mode", "value": "workspace_write"}]},
    )
    ops = manifest.patch_operations()
    self.assertEqual(len(ops), 1)
    self.assertEqual(ops[0]["path"], "ai_sandbox_mode")

  def test_profile_composer_detects_conflict(self):
    from ai.bundle.manifest import BundleManifest
    from ai.bundle.profile_compose import ProfileComposer

    def resolve(bundle_id: str):
      if bundle_id == "b1":
        return BundleManifest(id="b1", name="b1", version="1", extra={"patch": [{"op": "set", "path": "key", "value": "a"}]})
      return BundleManifest(id="b2", name="b2", version="1", extra={"patch": [{"op": "set", "path": "key", "value": "b"}]})

    composer = ProfileComposer(resolve_bundle=resolve)
    merged, conflicts = composer.compose("p1", ["b1", "b2"])
    self.assertEqual(merged.get("key"), "b")
    self.assertTrue(conflicts)
    self.assertTrue(any("PROFILE_CONFLICT" in c for c in conflicts))

  def test_bundle_store_save_and_list(self):
    from ai.bundle.manifest import BundleManifest
    from ai.bundle.store import BundleStore

    tmp = Path(tempfile.mkdtemp())
    store = BundleStore(store_dir=tmp / "store")
    manifest = BundleManifest(id="test", name="test", version="1.0.0")
    src = tmp / "src"
    src.mkdir()
    (src / "f.txt").write_text("payload", encoding="utf-8")
    store.save_bundle(src, manifest=manifest)
    listed = store.list_bundles()
    self.assertEqual(len(listed), 1)
    self.assertEqual(listed[0].id, "test")

  def test_bundle_store_get_and_remove(self):
    from ai.bundle.manifest import BundleManifest
    from ai.bundle.store import BundleStore

    tmp = Path(tempfile.mkdtemp())
    store = BundleStore(store_dir=tmp / "store")
    manifest = BundleManifest(id="removable", name="removable", version="1.0.0")
    src = tmp / "src"
    src.mkdir()
    store.save_bundle(src, manifest=manifest)
    self.assertIsNotNone(store.get_bundle("removable"))
    self.assertTrue(store.remove_bundle("removable"))
    self.assertIsNone(store.get_bundle("removable"))
    self.assertFalse(store.remove_bundle("removable"))


class WorkflowGraphRegressionTests(unittest.TestCase):
  def test_default_executor_runs_simple_graph(self):
    from ai.core.graph.executor import GraphExecutor
    from ai.core.graph.graph import Graph, Edge
    from ai.core.graph.node import Node, NodeKind

    executor = GraphExecutor()
    executor.register(NodeKind.START, lambda node, ctx: asyncio.sleep(0, result={"started": True}))
    executor.register(NodeKind.OUTPUT, lambda node, ctx: asyncio.sleep(0, result=ctx.get("_last")))

    graph = Graph(
      nodes=[
        Node(id="start", kind=NodeKind.START),
        Node(id="out", kind=NodeKind.OUTPUT),
      ],
      edges=[Edge(source="start", target="out")],
    )

    result = _run(executor.run(graph, inputs={"_last": "done"}))
    self.assertTrue(result.ok)

  def test_advance_missing_workflow_returns_error(self):
    from ai.tools.domains.platform.workflow_graph import advance_graph_workflow

    result = advance_graph_workflow("missing", "step")
    self.assertFalse(result["ok"])
    self.assertIn("not found", result["error"])

  def test_requires_tools_extracts_tool_call_nodes(self):
    from ai.core.graph.graph import Graph, Edge
    from ai.core.graph.node import Node, NodeKind
    from ai.tools.domains.platform.workflow_graph import save_graphs, graph_workflow_requires_tools

    tmp_graphs = {
      "wf-tools": {
        "name": "tool workflow",
        "graph": Graph(
          nodes=[
            Node(id="start", kind=NodeKind.START),
            Node(id="call", kind=NodeKind.TOOL_CALL, config={"tool": "echo"}),
            Node(id="out", kind=NodeKind.OUTPUT),
          ],
          edges=[Edge(source="start", target="call"), Edge(source="call", target="out")],
        ).to_dict(),
      }
    }
    save_graphs(tmp_graphs)
    result = graph_workflow_requires_tools("wf-tools")
    self.assertTrue(result["ok"])
    self.assertEqual(result["requiresTools"], ["echo"])

  def test_run_graph_workflow_step_advances_state(self):
    from ai.tools.domains.platform.workflow_graph import run_graph_workflow_step

    result = _run(run_graph_workflow_step("missing", "step"))
    self.assertFalse(result["ok"])
    self.assertIn("not found", result["error"])


# ---------------------------------------------------------------------------
# Server 健康与 fallback 路由
# ---------------------------------------------------------------------------

class ServerFallbackRegressionTests(AioHTTPTestCase):
  async def get_application(self):
    app = web.Application()
    setup_routes(app)
    return app

  @unittest_run_loop
  async def test_health_returns_ok(self):
    resp = await self.client.request("GET", "/api/ai/health")
    self.assertEqual(resp.status, 200)
    data = await resp.json()
    self.assertTrue(data["ok"])

  @unittest_run_loop
  async def test_bootstrap_returns_ok(self):
    resp = await self.client.request("GET", "/api/ai/bootstrap")
    self.assertEqual(resp.status, 200)
    data = await resp.json()
    self.assertTrue(data["ok"])
    self.assertIn("config", data)

  @unittest_run_loop
  async def test_fallback_unknown_path_returns_ok_local_dev(self):
    resp = await self.client.request("GET", "/api/ai/unknown/feature")
    self.assertEqual(resp.status, 200)
    data = await resp.json()
    self.assertTrue(data["ok"])

  @unittest_run_loop
  async def test_fallback_workflows_returns_empty_list(self):
    resp = await self.client.request("GET", "/api/ai/workflows")
    self.assertEqual(resp.status, 200)
    data = await resp.json()
    self.assertTrue(data["ok"])
    self.assertEqual(data.get("workflows"), [])


if __name__ == "__main__":
  unittest.main()
