"""HTTP response helpers."""
from __future__ import annotations
import json
from typing import Any
from aiohttp import web


def json_response(data: Any, status: int = 200) -> web.Response:
  return web.Response(
    text=json.dumps(data, ensure_ascii=False, default=str),
    status=status,
    content_type="application/json",
  )


_json_response = json_response
