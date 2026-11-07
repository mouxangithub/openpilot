"""Tests for the shared chat handler module (A-P0.5)."""
from __future__ import annotations

import unittest

import aiohttp
from aiohttp import web

import ai.tests.bootstrap_pc  # noqa: F401  (installs openpilot mocks)


class TestPureHelpers(unittest.TestCase):
  def test_extract_prompt_prefers_last_user(self):
    from ai.server.handlers.chat import extract_prompt
    messages = [
      {"role": "system", "content": "sys"},
      {"role": "user", "content": "first"},
      {"role": "assistant", "content": "ok"},
      {"role": "user", "content": "second"},
    ]
    self.assertEqual(extract_prompt(messages), "second")

  def test_extract_prompt_multimodal(self):
    from ai.server.handlers.chat import extract_prompt
    messages = [
      {"role": "user", "content": [{"type": "text", "text": "hello"}, {"type": "image", "url": "x"}]},
    ]
    self.assertEqual(extract_prompt(messages), "hello")

  def test_extract_prompt_empty(self):
    from ai.server.handlers.chat import extract_prompt
    self.assertEqual(extract_prompt([]), "")

  def test_extract_reply_from_agent(self):
    from ai.server.handlers.chat import extract_reply
    self.assertEqual(extract_reply({"agent": {"reply": "hi"}}), "hi")

  def test_extract_reply_from_fallback(self):
    from ai.server.handlers.chat import extract_reply
    self.assertEqual(extract_reply({"fallback": True, "result": {"answer": "fb"}}), "fb")

  def test_extract_reply_non_dict(self):
    from ai.server.handlers.chat import extract_reply
    self.assertEqual(extract_reply("plain"), "plain")

  def test_build_completion_response_shape(self):
    from ai.server.handlers.chat import build_completion_response
    resp = build_completion_response("hello", model="offline-mock", created=123)
    self.assertEqual(resp["object"], "chat.completion")
    self.assertEqual(resp["model"], "offline-mock")
    self.assertEqual(resp["created"], 123)
    self.assertEqual(resp["choices"][0]["message"]["content"], "hello")
    self.assertTrue(resp["id"].startswith("chatcmpl-"))

  def test_completion_sse_frames(self):
    from ai.server.handlers.chat import build_completion_response, completion_sse_frames
    resp = build_completion_response("hi", model="m", created=1)
    frames = completion_sse_frames(resp, "hi")
    self.assertEqual(len(frames), 3)
    self.assertTrue(all(f.startswith(b"data: ") for f in frames))
    self.assertEqual(frames[-1], b"data: [DONE]\n\n")

  def test_session_log_path(self):
    from ai.server.handlers.chat import session_log_path
    self.assertIsNone(session_log_path(""))
    path = session_log_path("sess-abc")
    self.assertIsInstance(path, str)
    self.assertIn("sess-abc", path)


class TestRouteWiring(unittest.TestCase):
  def test_op_routes_api_chat_is_shared_handler(self):
    from ai.server import op_routes
    from ai.server.handlers import chat as shared
    self.assertIs(op_routes.api_chat, shared.api_chat_local_dev)
    self.assertIs(op_routes.api_chat_completions, shared.api_chat_completions_local_dev)
    # Historical private aliases still resolve to the shared runner.
    self.assertIs(op_routes._run_chat_local_dev, shared.run_chat_local_dev)
    self.assertIs(op_routes._extract_prompt, shared.extract_prompt)

  def test_bind_local_dev_chat_routes(self):
    from ai.server.handlers.chat import bind_local_dev_chat_routes
    app = web.Application()
    bind_local_dev_chat_routes(app)
    paths = {(r.method, r.resource.canonical) for r in app.router.routes()}
    self.assertIn(("POST", "/api/ai/chat"), paths)
    self.assertIn(("POST", "/api/ai/chat/completions"), paths)


class TestCompletionEndpoint(unittest.IsolatedAsyncioTestCase):
  async def test_completions_handler_uses_app_config(self):
    import json as _json
    from ai.core.config.schema import AIOPConfig
    from ai.server.handlers import chat as shared

    async def fake_run(cwd, config, body, prompt, session_id):
      return {"agent": {"reply": f"echo:{prompt}"}}

    original = shared.run_chat_local_dev
    shared.run_chat_local_dev = fake_run
    try:
      app = web.Application()
      app["config"] = AIOPConfig()
      request = _make_request(app, {"messages": [{"role": "user", "content": "ping"}], "cwd": "."})
      resp = await shared.api_chat_completions_local_dev(request)
      self.assertEqual(resp.status, 200)
      payload = _json.loads(resp.body)
      self.assertEqual(payload["choices"][0]["message"]["content"], "echo:ping")
    finally:
      shared.run_chat_local_dev = original


def _make_request(app: web.Application, body: dict):
  """Build a minimal aiohttp Request bound to ``app`` whose json() returns body."""
  from unittest.mock import AsyncMock
  request = AsyncMock()
  request.app = app
  request.json = AsyncMock(return_value=body)
  return request


if __name__ == "__main__":
  unittest.main()
