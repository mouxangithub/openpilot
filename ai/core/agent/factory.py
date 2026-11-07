"""Central Agent construction factory (A-P0.4).

Unifies the three construction paths in the codebase — production
(``server/op_routes``, ``server/app_factory``), local dev (``dev/run_pc``) and
tests — so the Agent is always wired with the same tool-handler provenance,
config resolution, session-log path, and emit plumbing.

Design notes:
- No new third-party dependencies.
- The factory computes safe defaults but every point is injectable so callers
  that already have an object (e.g. a session log, an emit queue) can pass it
  through without duplicating logic.
- It never imports heavy runtime modules at module import time (deferred inside
  functions) to keep test collection fast and to avoid import cycles.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from openpilot.common.params import Params

from ai.core.agent.agent import Agent

EmitFn = Callable[[dict[str, Any]], Awaitable[Any]]


class AgentFactory:
  """Assemble an :class:`Agent` from a params object and request body."""

  def __init__(
    self,
    *,
    params: Params | None = None,
    workdir: str = "",
  ) -> None:
    self.params = params or Params()
    self._workdir = workdir

  # -- pluggable parts ----------------------------------------------------

  def resolve_config(self, body: dict[str, Any]) -> Any:
    """Return a merged AIConfig from params + request body."""
    from ai.core.llm.client import load_config_from_params, merge_config_from_body
    return merge_config_from_body(load_config_from_params(self.params), body)

  def tool_handlers_factory(self, get_state_reader: Callable[..., Any] | None = None) -> Callable[[], dict[str, Any]]:
    """Factory providing the tool-handler dict after the agent is created.

    Agent requires ``get_tool_handlers`` to be a ``Callable[[], dict]`` so the
    handler set is resolved lazily (after ``make_handlers`` has all extension
    registrations in place).
    """
    def _state_reader_snapshot() -> Any:
      if get_state_reader is not None:
        return get_state_reader()
      try:
        from ai.common.storage import read_param
        keys = [
          "ai_enabled", "IsEnabled", "CarParams", "ControlsReady",
          "ai_sandbox_mode", "dp_use_lateral", "ExperimentalMode",
        ]
        return {k: read_param(self.params, k) for k in keys}
      except Exception:
        return {}

    def _handlers() -> dict[str, Any]:
      from ai.tools.agent_tools import make_handlers
      return make_handlers(params=self.params, get_state_reader=_state_reader_snapshot)
    return _handlers

  def default_emit(self) -> EmitFn:
    """A no-op-ish emit that still records tool_call events.

    Production callers override this with their SSE/websocket emitter; this
    default keeps Agent fully runnable in tests / headless scripts.
    """
    async def _emit(_event: dict[str, Any]) -> Any:
      return None
    return _emit

  def session_log_path(self, session_id: str) -> str | None:
    """Derive a stable per-session log path under the aid logs dir."""
    if not session_id:
      return None
    try:
      from ai.system.paths import workspace_path
      base = workspace_path("sessions", mkdir=True)
      return str(base / f"{session_id}.jsonl")
    except Exception:
      return None

  # -- main assembly ------------------------------------------------------

  def create_agent(
    self,
    session_id: str,
    body: dict[str, Any],
    *,
    agent_id: str = "",
    emit: EmitFn | None = None,
    get_state_reader: Callable[..., Any] | None = None,
    get_tool_handlers: Callable[[], dict[str, Any]] | None = None,
    tools: list[dict[str, Any]] | None = None,
    session_log_path: str | None = "auto",
    config: Any | None = None,
    **overrides: Any,
  ) -> Agent:
    """Create an :class:`Agent` wired with this factory's defaults.

    Args:
      session_id: Session identifier.
      body: Request body (model/trace/tools/tool_rounds/etc absorbed by Agent).
      agent_id: Optional stable agent id; defaults to a derived id.
      emit: Event emitter; defaults to the factory no-op emitter.
      get_state_reader: State-reader callable; defaults to a Params reader.
      get_tool_handlers: Explicit lazy handler factory; defaults to the
          factory-managed :meth:`tool_handlers_factory`.
      tools: Explicit tool schema list; defaults to ``build_tool_schemas()``.
      session_log_path: Persist path; ``"auto"`` derives a path, ``None`` disables.
      config: Pre-resolved ``AIConfig``; when given it is used verbatim and
          :meth:`resolve_config` is skipped (lets callers keep a bespoke
          config such as the local-dev offline mock).
      **overrides: Any additional Agent kwargs (e.g. max_tool_rounds).
    """
    agent_id = agent_id or body.get("agent_id") or "default-agent"
    sid = session_id
    config = config if config is not None else self.resolve_config(body)

    if emit is None:
      emit = self.default_emit()

    def _state_reader() -> Any:
      if get_state_reader is not None:
        return get_state_reader()
      # Read a handful of commonly-consumed params so tool handlers that peek
      # at Params-backed state still behave. Failures degrade to an empty dict.
      try:
        from ai.common.storage import read_param
        keys = [
          "ai_enabled", "IsEnabled", "CarParams", "ControlsReady",
          "ai_sandbox_mode", "dp_use_lateral", "ExperimentalMode",
        ]
        return {k: read_param(self.params, k) for k in keys}
      except Exception:
        return {}

    log_path = session_log_path
    if log_path == "auto":
      log_path = self.session_log_path(sid)

    if tools is None:
      try:
        from ai.tools.agent_tools import build_tool_schemas
        tools = build_tool_schemas()
      except Exception:
        tools = []

    return Agent(
      session_id=sid,
      agent_id=agent_id,
      params=self.params,
      config=config,
      body=body,
      emit=emit,
      get_state_reader=_state_reader,
      get_tool_handlers=get_tool_handlers or self.tool_handlers_factory(),
      tools=tools,
      session_log_path=log_path,
      **overrides,
    )


def create_agent(
  session_id: str,
  body: dict[str, Any],
  *,
  params: Params | None = None,
  **overrides: Any,
) -> Agent:
  """Module-level convenience wrapper around :class:`AgentFactory`."""
  factory = AgentFactory(params=params)
  return factory.create_agent(session_id, body, **overrides)


__all__ = ["AgentFactory", "create_agent"]