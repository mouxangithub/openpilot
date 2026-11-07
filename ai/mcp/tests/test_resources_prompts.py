"""Regression tests for MCP resources/read and prompts/get (T03)."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

import ai.tests.bootstrap_pc  # noqa: F401


class MCPResourcesPromptsTests(unittest.IsolatedAsyncioTestCase):
  async def test_read_mcp_resource_host_function_exists(self):
    """T03: the host module must expose a read_mcp_resource callable."""
    from ai.mcp import host
    self.assertTrue(hasattr(host, "read_mcp_resource"))
    self.assertTrue(callable(getattr(host, "read_mcp_resource")))

  async def test_get_mcp_prompt_host_function_exists(self):
    """T03: the host module must expose a get_mcp_prompt callable."""
    from ai.mcp import host
    self.assertTrue(hasattr(host, "get_mcp_prompt"))
    self.assertTrue(callable(getattr(host, "get_mcp_prompt")))

  async def test_read_mcp_resource_returns_ok_envelope(self):
    """T03: read_mcp_resource delegates to the stdio client and wraps the result."""
    from ai.mcp import host
    from openpilot.common.params import Params

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value={"ok": True, "contents": [{"uri": "test://x", "text": "hi"}]})

    with patch.object(host, "_get_client", return_value=mock_client):
      result = await host.read_mcp_resource(Params(), "srv", "test://x", "session-1")

    self.assertTrue(result.get("ok"))
    self.assertEqual(result.get("server_id"), "srv")
    self.assertEqual(result.get("uri"), "test://x")
    self.assertEqual(result.get("contents"), {"ok": True, "contents": [{"uri": "test://x", "text": "hi"}]})
    mock_client.request.assert_awaited_once()

  async def test_get_mcp_prompt_returns_ok_envelope(self):
    """T03: get_mcp_prompt delegates to the stdio client and wraps the result."""
    from ai.mcp import host
    from openpilot.common.params import Params

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value={"ok": True, "messages": [{"role": "user", "content": {"type": "text", "text": "hi"}}]})

    with patch.object(host, "_get_client", return_value=mock_client):
      result = await host.get_mcp_prompt(Params(), "srv", "greet", {"name": "test"}, "session-1")

    self.assertTrue(result.get("ok"))
    self.assertEqual(result.get("server_id"), "srv")
    self.assertEqual(result.get("name"), "greet")
    mock_client.request.assert_awaited_once()

  async def test_read_mcp_resource_missing_server(self):
    """T03: read_mcp_resource returns an error envelope when the server is missing."""
    from ai.mcp import host
    from openpilot.common.params import Params

    with patch.object(host, "_get_client", return_value=None):
      result = await host.read_mcp_resource(Params(), "missing", "test://x", "session-1")

    self.assertFalse(result.get("ok"))
    self.assertIn("not found", result.get("error", "").lower())
    self.assertEqual(result.get("server_id"), "missing")
    self.assertEqual(result.get("uri"), "test://x")

  async def test_get_mcp_prompt_missing_server(self):
    """T03: get_mcp_prompt returns an error envelope when the server is missing."""
    from ai.mcp import host
    from openpilot.common.params import Params

    with patch.object(host, "_get_client", return_value=None):
      result = await host.get_mcp_prompt(Params(), "missing", "greet", {}, "session-1")

    self.assertFalse(result.get("ok"))
    self.assertIn("not found", result.get("error", "").lower())
    self.assertEqual(result.get("server_id"), "missing")
    self.assertEqual(result.get("name"), "greet")

  async def test_read_mcp_resource_propagates_client_error(self):
    """T03: read_mcp_resource wraps stdio client errors in the error envelope."""
    from ai.mcp import host
    from openpilot.common.params import Params

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(side_effect=RuntimeError("stdio broken"))

    with patch.object(host, "_get_client", return_value=mock_client):
      result = await host.read_mcp_resource(Params(), "srv", "test://x", "session-1")

    self.assertFalse(result.get("ok"))
    self.assertIn("stdio broken", result.get("error", ""))

  async def test_get_mcp_prompt_propagates_client_error(self):
    """T03: get_mcp_prompt wraps stdio client errors in the error envelope."""
    from ai.mcp import host
    from openpilot.common.params import Params

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(side_effect=RuntimeError("stdio broken"))

    with patch.object(host, "_get_client", return_value=mock_client):
      result = await host.get_mcp_prompt(Params(), "srv", "greet", {}, "session-1")

    self.assertFalse(result.get("ok"))
    self.assertIn("stdio broken", result.get("error", ""))


if __name__ == "__main__":
  unittest.main()
