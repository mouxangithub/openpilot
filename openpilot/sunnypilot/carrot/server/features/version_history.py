"""
Copyright (c) 2021-, Haibin Wen, sunnypilot and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""

"""Version history / rollback-target routes.

Strategy layer only: browsing, target persistence and preflight happen here;
the install itself is delegated to the existing tools dispatcher
(``git_checkout`` job) so every repo-lock / guard it has stays in force.
"""

import asyncio
import time
import uuid

from aiohttp import web

from .tools import jobs
from .tools.dispatcher import run_tool_job
from ..services import version_history as vh


async def api_version_history(request: web.Request) -> web.Response:
  repo = (request.query.get("repo") or "").strip() or await asyncio.to_thread(vh.default_repo)
  if not repo:
    return web.json_response({"ok": False, "error": "cannot determine GitHub repo (origin is not a GitHub remote)"}, status=404)
  result = await asyncio.to_thread(vh.fetch_releases, repo)
  return web.json_response(result, status=200 if result.get("ok") else 502)


async def api_rollback_target(request: web.Request) -> web.Response:
  if request.method == "POST":
    body = await request.json()
    try:
      target = vh.set_rollback_target(body.get("ref") or "", body.get("note") or "")
    except ValueError as exc:
      return web.json_response({"ok": False, "error": str(exc)}, status=400)
    return web.json_response({"ok": True, "rollback_target": target})
  if request.method == "DELETE":
    vh.clear_rollback_target()
    return web.json_response({"ok": True})
  target = vh.get_rollback_target()
  return web.json_response({"ok": True, "rollback_target": target})


async def api_version_preflight(request: web.Request) -> web.Response:
  body = await request.json()
  ref = str(body.get("ref") or "").strip()
  if not ref:
    return web.json_response({"ok": False, "error": "missing ref"}, status=400)
  result = await asyncio.to_thread(vh.preflight, "/data/openpilot", ref)
  return web.json_response(result, status=200 if result.get("ok") else 409)


async def api_version_install(request: web.Request) -> web.Response:
  """Preflight, persist the rollback target, then hand off to git_checkout."""
  body = await request.json()
  ref = str(body.get("ref") or "").strip()
  if not ref:
    return web.json_response({"ok": False, "error": "missing ref"}, status=400)

  result = await asyncio.to_thread(vh.preflight, "/data/openpilot", ref)
  if not result.get("ok"):
    return web.json_response(result, status=409)

  previous = vh.get_rollback_target()
  vh.set_rollback_target(ref, note=str(body.get("note") or "install"))
  vh.record_install({"ref": ref, "kind": "install", "previous": (previous or {}).get("ref"),
                     "commit": result.get("commit")})

  job_id = uuid.uuid4().hex[:12]
  now = time.time()
  job = {
    "id": job_id,
    "action": "git_checkout",
    "payload": {"action": "git_checkout", "branch": ref},
    "status": "running",
    "log": "",
    "progress": 0,
    "message": "",
    "step_current": 0,
    "step_total": 0,
    "error": None,
    "error_code": None,
    "error_detail": None,
    "result": None,
    "created_at": now,
    "updated_at": now,
  }
  jobs.jobs()[job_id] = job
  jobs.prune()
  jobs.persist_now()
  asyncio.create_task(run_tool_job(job))
  return web.json_response({"ok": True, "job_id": job_id, "preflight": result})


async def api_version_history_log(request: web.Request) -> web.Response:
  return web.json_response({"ok": True, "history": vh.install_history()})


def register(app: web.Application) -> None:
  app.router.add_get("/api/version_history", api_version_history)
  app.router.add_get("/api/version_history/install_log", api_version_history_log)
  app.router.add_route("*", "/api/version_history/rollback_target", api_rollback_target)
  app.router.add_post("/api/version_history/preflight", api_version_preflight)
  app.router.add_post("/api/version_history/install", api_version_install)
