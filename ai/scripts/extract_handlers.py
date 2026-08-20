"""One-off: extract HTTP handlers from aid.py into server/handlers/api.py."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
aid_path = ROOT / "aid.py"
text = aid_path.read_text(encoding="utf-8")

start = text.index("async def api_workflows")
end = text.index("DEFAULT_PORT = 5090")
handlers_block = text[start:end]

sched_start = text.index("async def _scheduler_execute_action")
sched_end = text.index("async def _parse_chat_body")
sched_block = text[sched_start:sched_end]

chat_start = text.index("async def _parse_chat_body")
chat_end = text.index("async def api_shell")
chat_block = text[chat_start:chat_end]

header = '''"""HTTP API handlers (extracted from aid.py)."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web

from openpilot.common.swaglog import cloudlog

from ai.server import deps
from ai.server.deps import (
  filter_tools,
  get_state_reader,
  get_tool_handlers,
  json_response,
  mask_key,
  openpilot_root,
  read_ai_config,
  read_param_bool_val,
  read_param_str,
  resolve_max_tool_rounds,
  sse,
)

_PARAMS = deps.params()
_get_state_reader = get_state_reader
_json_response = json_response
_sse = sse
_read_param_str = read_param_str
_read_param_bool = read_param_bool_val
_mask_key = mask_key
_read_ai_config = read_ai_config
_get_tool_handlers = get_tool_handlers
_resolve_max_tool_rounds = resolve_max_tool_rounds
_filter_tools = filter_tools
'''

handlers_block = handlers_block.replace(
  "Path(__file__).resolve().parent.parent",
  "openpilot_root()",
)

body = header + "\n" + sched_block + "\n" + chat_block + "\n" + handlers_block
out = ROOT / "server" / "handlers" / "api.py"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(body, encoding="utf-8")
print(f"wrote {out} ({len(body.splitlines())} lines)")
