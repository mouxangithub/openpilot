"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""The read-only "Tools > Info" endpoints, plus the honest answer for the ones we refuse.

CarrotPilot's Tools page can run arbitrary shell actions on the device (`/api/tools`,
`/api/tools/start`, the terminal). This fork will not expose a remote shell over plain HTTP
on the car network - there is no authentication on port 7000 - so those routes exist and
answer 501 with a reason rather than 404, which is what lets a client grey the button out
instead of showing a broken link.
"""

import asyncio
import os
import subprocess

from aiohttp import web

from ..services.device_info import get_device_network_snapshot

TMUX_LOG_PATH = "/data/log/tmux.log"
TMUX_START_DIR = "/data/openpilot"

REGULATORY_ASSET_CANDIDATES = (
  "/data/openpilot/openpilot/selfdrive/assets/offroad/fcc.html",
  "/data/openpilot/selfdrive/assets/offroad/fcc.html",
)

TOOLS_REFUSAL = " ".join((
  "not implemented: this fork does not expose a remote shell over port 7000. The port has no",
  "authentication, so any device on the car network could run commands on the computer that",
  "controls the car.",
))


def _git(args: list[str], timeout: float = 3.0) -> str:
  try:
    out = subprocess.check_output(["git", *args], cwd=TMUX_START_DIR, stderr=subprocess.DEVNULL, timeout=timeout)
    return out.decode("utf-8", "replace").strip()
  except Exception:
    return ""


def _git_status() -> dict:
  branch = _git(["branch", "--show-current"])
  commit = _git(["rev-parse", "HEAD"])
  return {
    "branch": branch,
    "commit": commit,
    "commit_short": commit[:7] if commit else "",
    "commit_date": _git(["show", "-s", "--format=%cI", "HEAD"]),
    "remote": _git(["config", "--get", "remote.origin.url"]),
    "dirty": bool(_git(["status", "--porcelain"])),
    "ahead": _git(["rev-list", "--count", "@{u}..HEAD"]),
    "behind": _git(["rev-list", "--count", "HEAD..@{u}"]),
  }


def _device_info() -> dict:
  network = get_device_network_snapshot()
  info: dict = {"network": network}
  try:
    with open("/VERSION", encoding="utf-8") as f:
      info["agnos_version"] = f.read().strip()
  except Exception:
    info["agnos_version"] = ""
  try:
    info["uname"] = os.uname().release
  except Exception:
    info["uname"] = ""
  try:
    with open("/proc/uptime", encoding="utf-8") as f:
      info["uptime_sec"] = float(f.read().split()[0])
  except Exception:
    info["uptime_sec"] = None
  return info


async def api_tools_device_info(request: web.Request) -> web.Response:
  return web.json_response({"ok": True, "info": await asyncio.to_thread(_device_info)})


async def api_tools_git_status(request: web.Request) -> web.Response:
  return web.json_response({"ok": True, **await asyncio.to_thread(_git_status)})


def _read_regulatory() -> tuple[str, str]:
  for path in REGULATORY_ASSET_CANDIDATES:
    if not os.path.isfile(path):
      continue
    try:
      with open(path, encoding="utf-8", errors="replace") as f:
        return f.read(), path
    except Exception:
      continue
  return "", ""


async def api_regulatory(request: web.Request) -> web.Response:
  """The FCC / regulatory notice the settings screen shows, if the asset is present."""
  html, path = await asyncio.to_thread(_read_regulatory)
  if not html:
    return web.json_response({"ok": False, "error": "regulatory info unavailable"}, status=404)
  return web.json_response({"ok": True, "html": html, "path": path})


async def api_tmux_log(request: web.Request) -> web.Response:
  if not await asyncio.to_thread(os.path.isfile, TMUX_LOG_PATH):
    return web.json_response({"ok": False, "error": "log file not found"}, status=404)
  return web.FileResponse(TMUX_LOG_PATH, headers={"Content-Disposition": "attachment; filename=tmux.log"})


async def api_tools_jobs(request: web.Request) -> web.Response:
  """There are no tool jobs because there are no tools. Answer the shape, not a 404."""
  return web.json_response({"ok": True, "jobs": [], "note": TOOLS_REFUSAL})


async def api_tools_job(request: web.Request) -> web.Response:
  return web.json_response({"ok": False, "error": "job not found", "note": TOOLS_REFUSAL}, status=404)


def _refuse(request: web.Request) -> web.Response:
  return web.json_response({"ok": False, "error": "not implemented", "note": TOOLS_REFUSAL}, status=501)


def register(app: web.Application) -> None:
  app.router.add_get("/api/tools/device_info", api_tools_device_info)
  app.router.add_get("/api/tools/git_status", api_tools_git_status)
  app.router.add_get("/api/tools/job", api_tools_job)
  app.router.add_get("/api/tools/jobs", api_tools_jobs)
  app.router.add_delete("/api/tools/jobs", _refuse)
  app.router.add_post("/api/tools", _refuse)
  app.router.add_post("/api/tools/start", _refuse)
  app.router.add_post("/api/tools/jobs/notice", _refuse)
  app.router.add_get("/api/regulatory", api_regulatory)
  app.router.add_get("/download/tmux.log", api_tmux_log)
