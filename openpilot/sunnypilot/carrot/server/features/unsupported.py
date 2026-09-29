"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""The CarrotPilot routes this fork does not run, answered instead of left dangling.

A client that gets 404 has no way to tell "this fork is old" from "the URL is wrong", so it
shows a broken link. Every route below therefore exists and answers 501 with a note saying
why. That is the whole point of the module: the surface is complete, and what is missing
says so.

What is not ported, and why:

  dashcam / screenrecord / replay
      A ~30-file media subsystem built on ffmpeg pipelines and its own replay index. It
      needs ffmpeg on the device and a second, independent way to enumerate segments, and
      sunnypilot already has its own route storage and viewer.

  terminal / support_terminal
      A remote shell over plain HTTP on port 7000, which has no authentication. Anything on
      the car network could run commands on the computer that controls the car.

  youtube_live / vision_diag / vision_test / compact_state
      Cloud streaming and Carrot Vision's packed binary HUD protocol. `compact_state` is a
      byte-packed Carrot-Vision format with no equivalent cereal message, and guessing one
      would give the app a stream that decodes to the wrong numbers.

The xiaoge V-ASM page is the exception: it already runs on this device on 127.0.0.1:8082,
so `/xiaoge` proxies it rather than answering 501. That port is loopback-only on purpose;
the proxy is what makes it reachable from the phone without exposing it on the LAN.
"""

from aiohttp import web

XIAOGE_UPSTREAM = "http://127.0.0.1:8082"
XIAOGE_TIMEOUT_SEC = 10

NOT_IMPLEMENTED = {
  "dashcam": " ".join((
    "not implemented: the dashcam replay subsystem (ffmpeg pipelines plus its own segment",
    "index) is not part of this fork. Use sunnypilot's own route viewer.",
  )),
  "screenrecord": "not implemented: screen recording is not ported.",
  "terminal": "not implemented: this fork does not expose a remote shell over port 7000.",
  "support_terminal": "not implemented: this fork does not expose a remote shell over port 7000.",
  "youtube": "not implemented: cloud streaming is not ported.",
  "vision_diag": "not implemented: vision diagnostics upload is not ported.",
  "vision_test": "not implemented: vision test harness is not ported.",
  "compact_state": " ".join((
    "not implemented: Carrot Vision's packed binary HUD protocol has no cereal counterpart",
    "here. /ws/raw_multiplex carries the same messages as JSON.",
  )),
  "carrot_navi_media": " ".join((
    "not implemented: fMP4 media pipeline is not ported.",
    "/ws/carrot_navi/state carries the navigation state.",
  )),
  "web_sound": "not implemented: the web HUD is not ported, so there is nothing to play sound on.",
  "stream": "not implemented: the /stream endpoint belongs to the web HUD, which is not ported.",
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


async def api_xiaoge(request: web.Request) -> web.Response:
  """Proxy the xiaoge V-ASM page so the phone can reach it without opening 8082 on the LAN."""
  import aiohttp

  # The mount point is stripped before the path is forwarded: upstream serves the page at
  # "/", and passing "/xiaoge/" through unchanged makes it answer 404 for its own index.
  tail = request.path_qs[len("/xiaoge"):]
  upstream = f"{XIAOGE_UPSTREAM}{tail if tail else '/'}"
  timeout = aiohttp.ClientTimeout(total=XIAOGE_TIMEOUT_SEC)
  try:
    async with aiohttp.ClientSession(timeout=timeout) as session:
      async with session.request(request.method, upstream, data=await request.read(),
                                headers={"Accept": request.headers.get("Accept", "*/*")}) as resp:
        body = await resp.read()
        content_type = resp.content_type or "text/html"
  except Exception as exc:
    return web.json_response({"ok": False, "error": f"xiaoge service unavailable: {exc}"}, status=502)
  return web.Response(body=body, status=200, content_type=content_type)


def register(app: web.Application) -> None:
  # --- media / replay --------------------------------------------------------
  app.router.add_route("GET", "/api/dashcam/{tail:.*}", _refusal("dashcam"))
  app.router.add_route("POST", "/api/dashcam/{tail:.*}", _refusal("dashcam"))
  app.router.add_route("GET", "/api/screenrecord/{tail:.*}", _refusal("screenrecord"))
  app.router.add_route("POST", "/api/screenrecord/{tail:.*}", _refusal("screenrecord"))

  # --- remote shells ---------------------------------------------------------
  app.router.add_route("GET", "/ws/terminal", _refusal("terminal"))
  app.router.add_route("GET", "/ws/terminal_pty", _refusal("terminal"))
  app.router.add_route("GET", "/ws/support_terminal/{tail:.*}", _refusal("support_terminal"))
  app.router.add_route("GET", "/support/terminal/{session_id}", _refusal("support_terminal"))
  app.router.add_route("GET", "/support-terminal-assets/{asset_name}", _refusal("support_terminal"))
  app.router.add_get("/api/terminal_commands", _refusal("terminal"))
  app.router.add_post("/api/terminal_commands/run", _refusal("terminal"))
  app.router.add_get("/api/terminal_pty/status", _refusal("terminal"))
  app.router.add_get("/api/support_terminal/status", _refusal("support_terminal"))
  app.router.add_post("/api/support_terminal/start", _refusal("support_terminal"))
  app.router.add_post("/api/support_terminal/stop", _refusal("support_terminal"))
  app.router.add_route("POST", "/api/support_terminal/commands/{tail:.*}", _refusal("support_terminal"))

  # --- cloud / vision --------------------------------------------------------
  app.router.add_route("GET", "/api/youtube_live/{tail:.*}", _refusal("youtube"))
  app.router.add_route("POST", "/api/youtube_live/{tail:.*}", _refusal("youtube"))
  app.router.add_route("GET", "/api/vision_diag/{tail:.*}", _refusal("vision_diag"))
  app.router.add_route("POST", "/api/vision_diag/{tail:.*}", _refusal("vision_diag"))
  app.router.add_get("/api/vision_test/status", _refusal("vision_test"))

  # --- binary / web-HUD transports -------------------------------------------
  app.router.add_get("/ws/compact_state", _refusal("compact_state"))
  app.router.add_get("/ws/carrot_navi/media", _refusal("carrot_navi_media"))
  app.router.add_get("/ws/web_sound", _refusal("web_sound"))
  app.router.add_post("/stream", _refusal("stream"))

  # --- xiaoge V-ASM, which does run here --------------------------------------
  app.router.add_get("/xiaoge", api_xiaoge)
  app.router.add_get("/xiaoge/", api_xiaoge)
