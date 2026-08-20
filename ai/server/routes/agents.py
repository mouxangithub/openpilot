"""Agent API routes."""

from __future__ import annotations

from aiohttp import web

from ai.agents.config import agents_enabled_payload, load_disabled_agent_ids, save_disabled_agent_ids
from ai.agents.office import office_snapshot
from ai.agents.registry import list_agents, orchestrator_id


def register_agent_routes(app: web.Application, *, json_response) -> None:
  params = app["params"]

  async def api_agents(request: web.Request) -> web.Response:
    if request.method == "POST":
      try:
        body = await request.json()
      except Exception:
        return json_response({"ok": False, "error": "Invalid JSON"}, status=400)
      disabled = body.get("disabled") or []
      if not isinstance(disabled, list):
        return json_response({"ok": False, "error": "disabled must be a list"}, status=400)
      save_disabled_agent_ids(params, disabled)
      return json_response({
        "ok": True,
        **agents_enabled_payload(params),
        "agents": list_agents(include_orchestrator=True),
        "office": office_snapshot(),
      })

    return json_response({
      "ok": True,
      "orchestratorId": orchestrator_id(),
      "agents": list_agents(include_orchestrator=True),
      "office": office_snapshot(),
      **agents_enabled_payload(params),
    })

  app.router.add_get("/api/ai/agents", api_agents)
  app.router.add_post("/api/ai/agents", api_agents)
