"""Tests for OpenClaw phase-2 features."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


class SyncProtocolTests(unittest.TestCase):
  def test_validate_hello(self):
    from ai.core.sync.protocol import validate_ws_message, get_protocol_schema

    ok, err = validate_ws_message({
      "type": "hello",
      "sessions": [],
      "stateVersion": 1,
      "protocolVersion": 1,
      "config": {},
    })
    self.assertTrue(ok, err)
    self.assertIn("hello", get_protocol_schema()["messages"])

  def test_hello_merge_preserves_type(self):
    """Regression: status_payload must not overwrite hello frame type."""
    payload = {"type": "hello", "sessions": [], "protocolVersion": 1}
    status = {"type": "status", "ok": True, "driving": False, "state": {}}
    status.pop("type", None)
    payload.update(status)
    self.assertEqual(payload["type"], "hello")
    self.assertTrue(payload["driving"] is False)



class ModelRouterTests(unittest.TestCase):
  def test_fallback_chain_empty(self):
    from ai.core.llm.client import AIConfig
    from ai.core.llm.model_router import resolve_chat_config_chain

    base = AIConfig(provider="opencode-zen", model="m1", api_key="k")
    chain = resolve_chat_config_chain(base, MagicMock())
    self.assertEqual(len(chain), 1)
    self.assertEqual(chain[0].model, "m1")


class CommandQueueTests(unittest.TestCase):
  def test_queue_when_driving_followup(self):
    from ai.core.chat.command_queue import submit_chat_request, _queues

    _queues.clear()
    started = []

    async def run():
      async def start_fn(body):
        started.append(body)
        return "job_1"

      result = await submit_chat_request(
        "s1",
        {"messages": []},
        driving=True,
        queue_mode="followup",
        start_fn=start_fn,
      )
      return result

    result = asyncio.run(run())
    self.assertTrue(result["queued"])
    self.assertIsNone(result["jobId"])
    self.assertEqual(len(started), 0)


class DeviceTrustTests(unittest.TestCase):
  def test_pair_without_pin(self):
    from ai.core.sync.device_trust import pair_device

    params = MagicMock()
    r = pair_device(params, device_id="d1", label="Browser")
    self.assertTrue(r["ok"])


class CanvasStoreTests(unittest.TestCase):
  def test_capture_report(self):
    from ai.canvas.store import maybe_capture_tool_artifact, list_artifacts

    art = maybe_capture_tool_artifact("s1", "tune_report", {"report": {"score": 1}})
    self.assertIsNotNone(art)
    items = list_artifacts("s1")
    self.assertEqual(len(items), 1)


class ChatJobsWaitTests(unittest.TestCase):
  def test_wait_for_done_job(self):
    from ai.core.chat import jobs as chat_jobs

    async def run():
      chat_jobs._jobs["job_wait"] = {
        "id": "job_wait",
        "sessionId": "s",
        "status": "done",
        "events": [],
        "eventSeq": 0,
        "assistant": {},
        "updatedAt": 0,
        "lastEventAt": 0,
      }
      return await chat_jobs.wait_for_job("job_wait", timeout_ms=500)

    result = asyncio.run(run())
    self.assertEqual(result["status"], "done")



if __name__ == "__main__":
  unittest.main()
