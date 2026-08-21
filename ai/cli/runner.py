"""Shared OP chat streaming — used by ``op`` CLI and web terminal."""

from __future__ import annotations

import json
from typing import Any, Iterator

from ai.cli.main import DEFAULT_BASE


def build_chat_request_body(
  message: str,
  *,
  messages: list[dict[str, Any]] | None = None,
  workflow: str = "",
  consumer_mode: bool = False,
  session_id: str = "",
) -> dict[str, Any]:
  msgs = list(messages or [])
  if not msgs:
    msgs = [{"role": "user", "content": message}]
  body: dict[str, Any] = {
    "messages": msgs,
    "tools": True,
    "source": "op",
  }
  if workflow:
    body["workflow"] = workflow
  if consumer_mode:
    body["consumerMode"] = True
  if session_id:
    body["sessionId"] = session_id
  return body


def parse_op_command(line: str) -> dict[str, Any] | None:
  """Parse ``op <subcmd> [message]`` for terminal routing."""
  raw = (line or "").strip()
  if not raw.lower().startswith("op"):
    return None
  parts = raw.split(maxsplit=2)
  if len(parts) == 1 or parts[0].lower() != "op":
    return None
  sub = parts[1].lower() if len(parts) > 1 else "help"
  rest = parts[2] if len(parts) > 2 else ""
  aliases = {
    "doctor": ("cant_engage", "engage_triage", True),
    "tune": ("tune_feel", "tune_session", True),
    "adapt": ("adapt_new_car", "vehicle_adaptation", True),
    "review": ("review_trip", "post_drive_review", True),
    "trip": ("review_trip", "post_drive_review", True),
    "chat": ("", "", True),
  }
  if sub in aliases:
    _wid, wf, consumer = aliases[sub]
    return {
      "subcommand": sub,
      "message": rest or _default_prompt(sub),
      "workflow": wf,
      "consumer_mode": consumer,
    }
  return {"subcommand": sub, "message": rest, "workflow": "", "consumer_mode": True}


def _default_prompt(sub: str) -> str:
  return {
    "doctor": "车开不起来，请帮我排查。",
    "tune": "帮我调驾驶手感。",
    "adapt": "我要适配一辆新车。",
    "review": "帮我复盘最近一趟路。",
    "trip": "帮我复盘最近一趟路。",
    "chat": "",
  }.get(sub, "")


def iter_sse_events(raw_line: bytes | str) -> Iterator[dict[str, Any]]:
  line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else raw_line
  line = line.strip()
  if not line.startswith("data:"):
    return
  payload = line[5:].strip()
  if not payload:
    return
  try:
    data = json.loads(payload)
  except json.JSONDecodeError:
    return
  yield data


def stream_chat_http(body: dict[str, Any], *, base_url: str | None = None) -> Iterator[dict[str, Any]]:
  """Yield SSE events from ``POST /api/ai/chat`` (sync, for CLI)."""
  import urllib.error
  import urllib.request

  base = (base_url or DEFAULT_BASE).rstrip("/")
  url = f"{base}/api/ai/chat"
  data = json.dumps(body, ensure_ascii=False).encode("utf-8")
  req = urllib.request.Request(
    url,
    data=data,
    headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    method="POST",
  )
  with urllib.request.urlopen(req, timeout=600) as resp:
    for raw_line in resp:
      yield from iter_sse_events(raw_line)


def terminal_op_url(base_url: str | None = None) -> str:
  base = (base_url or DEFAULT_BASE).rstrip("/")
  return f"{base}/api/ai/terminal/op"
