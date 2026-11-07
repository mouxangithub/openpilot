"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""`/api/opui/*` - pass-through to the 5080 webui daemon's own API.

The webui submodule already implements the interactive surfaces sunnypilot's
on-device settings have and this panel's generic param rows cannot express:
the model manager (bundle tree, selection, favorites, download state,
accelerator link) and the sunnypilot vehicle selection. Rather than
duplicating 1,400 lines of SubMaster-reading bridge code, the panel proxies
the daemon on loopback. The daemon is optional: absent it, every route here
answers 502 and the pages fall back to the generic rendering.
"""
from aiohttp import web

from ..config import WEBUI_PROXY_TARGET

PROXY_TIMEOUT_SECONDS = 30
_FORWARD_HEADERS = ("Content-Type", "Accept")


async def proxy_opui(request: web.Request) -> web.Response:
  tail = request.match_info["tail"]
  url = f"{WEBUI_PROXY_TARGET}/api/opui/{tail}"
  if request.query_string:
    url += f"?{request.query_string}"

  session = request.app.get("http")
  if session is None:
    return web.json_response({"ok": False, "error": "webui proxy unavailable"}, status=502)

  body = await request.read() if request.method in ("POST", "PUT", "PATCH") else None
  headers = {name: request.headers[name] for name in _FORWARD_HEADERS if name in request.headers}

  try:
    async with session.request(request.method, url, data=body, headers=headers,
                               timeout=PROXY_TIMEOUT_SECONDS) as resp:
      payload = await resp.read()
      out = web.Response(status=resp.status, body=payload)
      content_type = resp.headers.get("Content-Type")
      if content_type:
        out.headers["Content-Type"] = content_type
      return out
  except TimeoutError:
    return web.json_response({"ok": False, "error": "webui proxy timeout"}, status=504)
  except Exception as exc:
    return web.json_response({"ok": False, "error": f"webui proxy: {exc}"}, status=502)


def register(app: web.Application) -> None:
  app.router.add_route("*", "/api/opui/{tail:.*}", proxy_opui)
