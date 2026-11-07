"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""The CarrotPilot routes this fork still does not run, answered instead of left dangling.

A client that gets 404 has no way to tell "this fork is old" from "the URL is wrong", so it
shows a broken link. Every route below therefore exists and answers 501 with a note saying
why. That is the whole point of the module: the surface is complete, and what is missing
says so.

After the full port this is a short list. What used to be here - dashcam, screenrecord,
terminal, support_terminal, tools' write actions, vision_diag, vision_test, compact_state,
web_sound and `/stream` - now has a real implementation, so those refusals were removed
rather than left to shadow it.

What is left:

  youtube_live
      CarrotPilot does not ship it either; the routes exist only so a client built against
      the older cloud-streaming build gets a reason instead of a 404.
"""

from aiohttp import web

NOT_IMPLEMENTED = {
  "youtube": " ".join((
    "not implemented: cloud streaming is not ported, and CarrotPilot no longer ships it.",
  )),
}


def _refusal(kind: str):
  async def handler(request: web.Request) -> web.Response:
    return web.json_response({
      "ok": False,
      "error": "not implemented",
      "path": request.path,
      "note": NOT_IMPLEMENTED.get(kind, "not implemented"),
    }, status=501)

  return handler


def register(app: web.Application) -> None:
  app.router.add_route("GET", "/api/youtube_live/{tail:.*}", _refusal("youtube"))
  app.router.add_route("POST", "/api/youtube_live/{tail:.*}", _refusal("youtube"))
