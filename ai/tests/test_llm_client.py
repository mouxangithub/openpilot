"""Tests for ai.core.llm.client headers and session routing."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))


class _FakeResponse:
  def __init__(self, status: int, text: str = "", json_data: dict | None = None):
    self.status = status
    self._text = text
    self._json = json_data or {}

  async def text(self) -> str:
    return self._text

  async def json(self) -> dict:
    return self._json

  async def __aenter__(self):
    return self

  async def __aexit__(self, *args):
    pass


class _AsyncIterator:
  def __init__(self, items: list):
    self._items = items
    self._idx = 0

  def __aiter__(self):
    return self

  async def __anext__(self):
    if self._idx >= len(self._items):
      raise StopAsyncIteration
    item = self._items[self._idx]
    self._idx += 1
    return item


def _make_session_mock(http_method: str, response: _FakeResponse):
  """Return an aiohttp.ClientSession mock usable as async context manager."""
  method_mock = MagicMock(return_value=response)
  session = MagicMock()
  session.__aenter__ = AsyncMock(return_value=session)
  session.__aexit__ = AsyncMock(return_value=None)
  setattr(session, http_method, method_mock)
  return session, method_mock


class TestLLMClientHeaders(unittest.TestCase):
  def _config(self, provider: str = "opencode-go", session_id: str = "sess_123"):
    from ai.core.llm.client import AIConfig

    return AIConfig(
      provider=provider,
      model="opencode-go/deepseek-v4.1-flash",
      api_key="sk-test",
      session_id=session_id,
    )

  def test_opencode_go_injects_session_and_user_agent(self):
    from ai.core.llm.client import _stream_chat_completion

    config = self._config()

    fake_resp = _FakeResponse(200)
    fake_resp.content = _AsyncIterator([
      b'data: {"choices":[{"delta":{"content":"hi"}}]}\n',
      b'data: [DONE]\n',
    ])
    session, post_mock = _make_session_mock("post", fake_resp)

    async def run():
      with patch("aiohttp.ClientSession", return_value=session):
        async for _ in _stream_chat_completion(
          config, [{"role": "user", "content": "hello"}], None, None, None, thinking_mode="user", timeout_total=10
        ):
          pass

    asyncio.run(run())
    headers = post_mock.call_args.kwargs["headers"]
    self.assertEqual(headers["x-opencode-session"], "sess_123")
    self.assertTrue(headers["User-Agent"].startswith("op-assistant/"))

  def test_non_opencode_does_not_inject_session(self):
    from ai.core.llm.client import _stream_chat_completion

    config = self._config(provider="deepseek")

    fake_resp = _FakeResponse(200)
    fake_resp.content = _AsyncIterator([
      b'data: {"choices":[{"delta":{"content":"hi"}}]}\n',
    ])
    session, post_mock = _make_session_mock("post", fake_resp)

    async def run():
      with patch("aiohttp.ClientSession", return_value=session):
        async for _ in _stream_chat_completion(
          config, [{"role": "user", "content": "hello"}], None, None, None, thinking_mode="user", timeout_total=10
        ):
          pass

    asyncio.run(run())
    headers = post_mock.call_args.kwargs["headers"]
    self.assertNotIn("x-opencode-session", headers)

  def test_list_models_injects_session_for_opencode(self):
    from ai.core.llm.client import list_models

    config = self._config()

    fake_resp = _FakeResponse(200, json_data={"data": [{"id": "opencode-go/deepseek-v4.1-flash"}]})
    session, get_mock = _make_session_mock("get", fake_resp)

    async def run():
      with patch("aiohttp.ClientSession", return_value=session):
        await list_models(config)

    asyncio.run(run())
    headers = get_mock.call_args.kwargs["headers"]
    self.assertEqual(headers["x-opencode-session"], "sess_123")
    self.assertTrue(headers["User-Agent"].startswith("op-assistant/"))

  def test_default_user_agent_reads_version(self):
    from ai.core.llm.client import DEFAULT_USER_AGENT

    self.assertTrue(DEFAULT_USER_AGENT.startswith("op-assistant/"))
    self.assertNotEqual(DEFAULT_USER_AGENT, "op-assistant/0.0.0")

  def test_chat_completion_updates_config_session_id(self):
    from ai.core.llm.client import AIConfig, chat_completion

    config = AIConfig(provider="opencode-go", model="m", api_key="k")
    self.assertEqual(config.session_id, "")

    fake_resp = _FakeResponse(200)
    fake_resp.content = _AsyncIterator([
      b'data: {"choices":[{"delta":{"content":"x"}}]}\n',
    ])
    session, _ = _make_session_mock("post", fake_resp)

    async def run():
      with patch("aiohttp.ClientSession", return_value=session):
        async for _ in chat_completion(config, [{"role": "user", "content": "h"}], session_id="sess_abc"):
          pass

    asyncio.run(run())
    self.assertEqual(config.session_id, "sess_abc")


class TestEmbeddingHeaders(unittest.TestCase):
  def test_opencode_embedding_injects_session_when_present(self):
    from ai.core.llm.embedding import EmbeddingConfig, embed_texts

    config = EmbeddingConfig(
      provider="opencode-go",
      model="opencode-go/text-embedding-3-small",
      api_key="sk-test",
      session_id="emb_sess",
    )

    fake_resp = _FakeResponse(
      200,
      json_data={"data": [{"index": 0, "embedding": [0.1, 0.2]}], "usage": {"prompt_tokens": 2, "total_tokens": 2}},
    )
    session, post_mock = _make_session_mock("post", fake_resp)

    async def run():
      with patch("aiohttp.ClientSession", return_value=session):
        await embed_texts(config, ["hello"])

    asyncio.run(run())
    headers = post_mock.call_args.kwargs["headers"]
    self.assertEqual(headers["x-opencode-session"], "emb_sess")


if __name__ == "__main__":
  unittest.main()
