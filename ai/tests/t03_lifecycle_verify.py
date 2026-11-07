"""T03 真实持久化会话生命周期端到端验证（需本地 dev 服务跑在 5090）。"""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

import requests

BASE = "http://127.0.0.1:5090"


def post_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
  r = requests.post(f"{BASE}{path}", json=payload, timeout=30, proxies={"no": "*"})
  r.raise_for_status()
  return r.json()


def get_json(path: str) -> dict[str, Any]:
  r = requests.get(f"{BASE}{path}", timeout=30, proxies={"no": "*"})
  r.raise_for_status()
  return r.json()


def chat_stream(payload: dict[str, Any]) -> list[dict[str, Any]]:
  r = requests.post(
    f"{BASE}/api/ai/chat",
    json=payload,
    stream=True,
    timeout=120,
    proxies={"no": "*"},
  )
  r.raise_for_status()
  events: list[dict[str, Any]] = []
  for line in r.iter_lines():
    if not line:
      continue
    text = line.decode("utf-8")
    if text.startswith("data:"):
      text = text[5:]
    try:
      events.append(json.loads(text))
    except json.JSONDecodeError:
      pass
  return events


def main() -> int:
  session_id = f"t03-{uuid.uuid4().hex[:8]}"
  print(f"[T03] session_id={session_id}")

  # 1. chat with explicit session_id -> durable log is created
  events = chat_stream({
    "messages": [{"role": "user", "content": "hello, run a quick echo"}],
    "session_id": session_id,
    "stream": True,
  })
  types = {e.get("type") for e in events}
  print(f"[T03] chat event types: {types}")
  assert "agent_done" in types or "done" in types, "chat did not finish"

  # give filesystem a moment
  time.sleep(0.5)

  # 2. read durable log
  log = get_json(f"/api/ai/sessions/{session_id}/log")
  assert log.get("ok"), f"log read failed: {log}"
  assert log.get("sessionId") == session_id
  ev_types = [e.get("type") for e in log.get("events", [])]
  print(f"[T03] persisted event types: {ev_types[:20]}...")
  assert "request/header" in ev_types
  assert "user/message" in ev_types
  assert "assistant/message" in ev_types

  # 3. resume
  resume = post_json(f"/api/ai/sessions/{session_id}/resume", {})
  assert resume.get("ok"), f"resume failed: {resume}"
  assert resume.get("replayedEvents") >= 1

  # 4. repair
  repair = post_json(f"/api/ai/sessions/{session_id}/repair", {})
  assert repair.get("ok"), f"repair failed: {repair}"

  # 5. fork by count
  fork = post_json(f"/api/ai/sessions/{session_id}/fork", {"count": 3})
  assert fork.get("ok"), f"fork failed: {fork}"
  assert fork.get("count") == 3

  # 6. pause
  pause = post_json(f"/api/ai/sessions/{session_id}/pause", {})
  assert pause.get("ok"), f"pause failed: {pause}"
  assert pause.get("state") == "paused"

  # 7. dispose
  dispose = post_json(f"/api/ai/sessions/{session_id}/dispose", {})
  assert dispose.get("ok"), f"dispose failed: {dispose}"
  assert dispose.get("state") == "disposed"

  # 8. after dispose, pause should 404
  paused2 = post_json(f"/api/ai/sessions/{session_id}/pause", {})
  assert not paused2.get("ok"), f"expected pause to fail after dispose: {paused2}"

  print("[T03] all lifecycle checks passed")
  return 0


if __name__ == "__main__":
  sys.exit(main())
