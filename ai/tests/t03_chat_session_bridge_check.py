"""Check whether chat-created sessions can be paused/disposed via HTTP."""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import requests

from ai.system.paths import workspace_path

BASE = "http://127.0.0.1:5091"


def main() -> int:
  session_id = f"bridge-{uuid.uuid4().hex[:8]}"
  # Create a chat-style durable log file without registering with SessionManager
  log_dir = workspace_path("ai_session_logs", mkdir=True)
  log_path = log_dir / f"{session_id}.jsonl"
  log_path.write_text('{"type":"request/header","sessionId":"' + session_id + '"}\n', encoding="utf-8")

  failed = False
  for action in ("pause", "dispose"):
    url = f"{BASE}/api/ai/sessions/{session_id}/{action}"
    try:
      r = requests.post(url, json={}, timeout=30)
      data = r.json()
    except Exception as e:
      print(f"[{action}] request error: {e}")
      failed = True
      continue
    print(f"[{action}] status={r.status_code} body={json.dumps(data, ensure_ascii=False)}")
    if not data.get("ok"):
      failed = True

  # cleanup
  try:
    log_path.unlink(missing_ok=True)
  except Exception:
    pass

  if failed:
    print("FAIL: chat-created session lifecycle did not fully succeed")
    return 1
  print("PASS: chat-created session lifecycle works")
  return 0


if __name__ == "__main__":
  sys.exit(main())
