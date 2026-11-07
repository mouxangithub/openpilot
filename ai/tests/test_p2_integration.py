"""P2 T05 end-to-end integration tests.

Covers:
- WorkflowEngine invoked through the `run_workflow` platform tool.
- Skill lifecycle HTTP routes (dispose, diagnose, diagnose-all).
- SessionSkillRegistry session isolation via HTTP session register.
- MCP resources/read and prompts/get HTTP handler with a mocked stdio client.

Run:
    cd /e/sp && PYTHONPATH="E:\\sp\\ai" python -m pytest ai/tests/test_p2_integration.py -q
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import ai.tests.bootstrap_pc  # noqa: F401

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from ai.core.workflow import WorkflowEngine
from ai.server.handlers import skills as skills_lifecycle_handlers
from ai.server.handlers import phase2 as phase2_handlers
from ai.skill.models import Skill, SkillDependency
from ai.skill.registry import SkillRegistry
from ai.skill.session_registry import SessionSkillRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _echo_tool(name: str, args: dict[str, object]) -> dict[str, object]:
    """Fake tool used by WorkflowEngine integration tests."""
    return {"ok": True, "tool": name, "args": args}


def _fake_state_reader() -> SimpleNamespace:
    """Return a state reader that claims the vehicle is stationary."""
    return SimpleNamespace(
        update=lambda timeout=0: SimpleNamespace(is_driving=False, v_ego=0.0, ignition=False),
    )


# ---------------------------------------------------------------------------
# WorkflowEngine via platform tool
# ---------------------------------------------------------------------------

class WorkflowPlatformToolIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_workflow_tool_executes_definition(self):
        """T05: the platform `run_workflow` handler runs an inline WorkflowEngine definition."""
        from ai.tools.domains.platform.platform_extensions import make_platform_handlers
        from openpilot.common.params import Params

        handlers = make_platform_handlers(params=Params())
        self.assertIn("run_workflow", handlers)

        definition = {
            "id": "int-tool-test",
            "steps": [
                {"id": "hello", "kind": "tool", "inputs": {"tool": "echo", "message": "hi"}},
            ],
            "outputs": {"reply": "${steps.hello.output.args.message}"},
        }

        with patch("ai.tools.domains.platform.platform_extensions._dispatch_workflow_tool") as mock_dispatch:
            mock_dispatch.return_value = {"ok": True, "tool": "echo", "args": {"message": "hi"}}
            result = await handlers["run_workflow"]({
                "definition": definition,
                "inputs": {},
            })

        self.assertTrue(result.get("ok"), f"workflow failed: {result}")
        self.assertEqual(result["output"]["reply"], "hi")

    async def test_run_workflow_tool_needs_definition_or_id(self):
        """T05: run_workflow returns an error when neither definition nor workflow_id is provided."""
        from ai.tools.domains.platform.platform_extensions import make_platform_handlers
        from openpilot.common.params import Params

        handlers = make_platform_handlers(params=Params())
        result = await handlers["run_workflow"]({"inputs": {}})
        self.assertFalse(result.get("ok"))
        self.assertIn("required", result.get("error", "").lower())


# ---------------------------------------------------------------------------
# Skill lifecycle HTTP handlers
# ---------------------------------------------------------------------------

class SkillLifecycleHttpIntegrationTests(AioHTTPTestCase):
    async def get_application(self) -> web.Application:
        """Build a minimal aiohttp app with only the P2 skill lifecycle routes."""
        app = web.Application()
        app["params"] = None
        app.router.add_post("/api/ai/skills/{id}/dispose", skills_lifecycle_handlers.api_skill_dispose)
        app.router.add_get("/api/ai/skills/{id}/diagnose", skills_lifecycle_handlers.api_skill_diagnose)
        app.router.add_post("/api/ai/skills/diagnose-all", skills_lifecycle_handlers.api_skill_diagnose_all)
        app.router.add_post("/api/ai/skills/session/register", skills_lifecycle_handlers.api_skill_session_register)
        return app

    def setUp(self):
        super().setUp()
        self._tmp = Path(tempfile.mkdtemp()) / "skills"
        self._registry = SkillRegistry(self._tmp)
        self._registry.register(Skill(
            id="global_skill",
            name="Global Skill",
            description="A global skill for HTTP tests",
            policy="auto",
            parameters=[],
            version="1.0.0",
            scope="global",
            capabilities=["demo"],
            source="builtin:test",
        ))
        self._patch_base = patch.object(
            skills_lifecycle_handlers,
            "_skill_registry",
            return_value=self._registry,
        )
        self._patch_base.start()

    def tearDown(self):
        self._patch_base.stop()
        super().tearDown()

    @unittest_run_loop
    async def test_diagnose_existing_skill(self):
        resp = await self.client.request("GET", "/api/ai/skills/global_skill/diagnose")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["skill_id"], "global_skill")
        self.assertTrue(data["report"]["ok"])

    @unittest_run_loop
    async def test_diagnose_missing_skill(self):
        resp = await self.client.request("GET", "/api/ai/skills/missing/diagnose")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["skill_id"], "missing")

    @unittest_run_loop
    async def test_diagnose_all_returns_global_report(self):
        resp = await self.client.request("POST", "/api/ai/skills/diagnose-all")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["ok"])
        self.assertIn("global_skill", data["reports"])
        self.assertTrue(data["conflicts"]["ok"])

    @unittest_run_loop
    async def test_session_register_isolates_from_global(self):
        skill_payload = {
            "id": "session_skill",
            "name": "Session Skill",
            "description": "A session-local skill",
            "policy": "auto",
            "parameters": [],
            "version": "0.5.0",
            "scope": "session",
        }
        resp = await self.client.request(
            "POST",
            "/api/ai/skills/session/register",
            data=json.dumps({"session_id": "s1", "skill": skill_payload}),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["session_id"], "s1")
        self.assertEqual(data["skill"]["id"], "session_skill")

    @unittest_run_loop
    async def test_session_register_requires_session_id(self):
        resp = await self.client.request(
            "POST",
            "/api/ai/skills/session/register",
            data=json.dumps({"skill": {"id": "x"}}),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(resp.status, 400)
        data = await resp.json()
        self.assertFalse(data["ok"])
        self.assertIn("session_id", data.get("error", "").lower())

    @unittest_run_loop
    async def test_dispose_missing_skill_returns_404(self):
        resp = await self.client.request("POST", "/api/ai/skills/unknown/dispose")
        self.assertEqual(resp.status, 404)
        data = await resp.json()
        self.assertFalse(data["ok"])


# ---------------------------------------------------------------------------
# SessionSkillRegistry isolation
# ---------------------------------------------------------------------------

class SessionSkillRegistryIntegrationTests(unittest.TestCase):
    def test_session_overlay_shadows_global(self):
        tmp = Path(tempfile.mkdtemp()) / "skills"
        registry = SkillRegistry(tmp)
        registry.register(Skill(
            id="shared",
            name="Shared Global",
            description="x",
            policy="auto",
            parameters=[],
            version="1.0.0",
            scope="global",
        ))

        session = registry.for_session("session-42")
        session.register(Skill(
            id="shared",
            name="Shared Session",
            description="y",
            policy="auto",
            parameters=[],
            version="2.0.0",
            scope="session",
        ))

        # Session view prefers the local shadow.
        self.assertEqual(session.get("shared").scope, "session")
        self.assertEqual(session.get("shared").version, "2.0.0")
        # Global registry is untouched.
        self.assertEqual(registry.get("shared").scope, "global")
        self.assertEqual(registry.get("shared").version, "1.0.0")

    def test_session_diagnose_and_conflicts(self):
        tmp = Path(tempfile.mkdtemp()) / "skills"
        registry = SkillRegistry(tmp)
        session = registry.for_session("session-43")
        session.register(Skill(
            id="local",
            name="Local",
            description="x",
            policy="auto",
            parameters=[],
            dependencies=[SkillDependency(name="missing")],
        ))

        diag = session.diagnose("local")
        self.assertFalse(diag["deps_ok"])
        conflicts = session.check_conflicts()
        self.assertFalse(conflicts["ok"])


# ---------------------------------------------------------------------------
# MCP resources/read and prompts/get HTTP handler (mock client)
# ---------------------------------------------------------------------------

class McpHttpIntegrationTests(AioHTTPTestCase):
    async def get_application(self) -> web.Application:
        app = web.Application()
        app["params"] = None
        app.router.add_get("/api/ai/mcp", phase2_handlers.api_platform_mcp)
        app.router.add_post("/api/ai/mcp", phase2_handlers.api_platform_mcp)
        return app

    @unittest_run_loop
    async def test_read_resource_http_handler(self):
        # api_platform_mcp imports read_mcp_resource inside the function body,
        # so we patch the module-level target that the local import resolves to.
        with patch("ai.mcp.host.read_mcp_resource") as mock_read:
            mock_read.return_value = {
                "ok": True,
                "server_id": "srv",
                "uri": "test://x",
                "contents": [{"uri": "test://x", "text": "hello"}],
            }
            resp = await self.client.request(
                "POST",
                "/api/ai/mcp",
                data=json.dumps({
                    "operation": "read_resource",
                    "server_id": "srv",
                    "uri": "test://x",
                    "session_id": "session-1",
                }),
                headers={"Content-Type": "application/json"},
            )

        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["server_id"], "srv")
        self.assertEqual(data["uri"], "test://x")

    @unittest_run_loop
    async def test_get_prompt_http_handler(self):
        with patch("ai.mcp.host.get_mcp_prompt") as mock_get:
            mock_get.return_value = {
                "ok": True,
                "server_id": "srv",
                "name": "greet",
                "messages": [{"role": "user", "content": {"type": "text", "text": "hi"}}],
            }
            resp = await self.client.request(
                "POST",
                "/api/ai/mcp",
                data=json.dumps({
                    "operation": "get_prompt",
                    "server_id": "srv",
                    "name": "greet",
                    "arguments": {"name": "test"},
                    "session_id": "session-1",
                }),
                headers={"Content-Type": "application/json"},
            )

        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["name"], "greet")

    @unittest_run_loop
    async def test_read_resource_requires_uri(self):
        resp = await self.client.request(
            "POST",
            "/api/ai/mcp",
            data=json.dumps({"operation": "read_resource", "server_id": "srv"}),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(resp.status, 400)
        data = await resp.json()
        self.assertFalse(data["ok"])
        self.assertIn("uri", data.get("error", "").lower())

    @unittest_run_loop
    async def test_get_prompt_requires_name(self):
        resp = await self.client.request(
            "POST",
            "/api/ai/mcp",
            data=json.dumps({"operation": "get_prompt", "server_id": "srv"}),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(resp.status, 400)
        data = await resp.json()
        self.assertFalse(data["ok"])
        self.assertIn("name", data.get("error", "").lower())


# ---------------------------------------------------------------------------
# Local dev server smoke test
# ---------------------------------------------------------------------------

class LocalDevServerSmokeTests(unittest.TestCase):
    def test_health_route_responds_ok(self):
        """T05: create_app produces an app whose /api/ai/health returns ok in local-dev mode."""
        from ai.server.op_routes import setup_routes
        app = web.Application()
        setup_routes(app)

        async def _probe() -> dict[str, object]:
            from aiohttp.test_utils import TestClient, TestServer
            server = TestServer(app)
            client = TestClient(server)
            await client.start_server()
            try:
                resp = await client.request("GET", "/api/ai/health")
                return await resp.json()
            finally:
                await client.close()

        result = asyncio.run(_probe())
        self.assertTrue(result.get("ok"))


if __name__ == "__main__":
    unittest.main()
