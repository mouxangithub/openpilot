"""Subagent provider registry.

Alignment with deepseek-harness' subagent provider family (in-process / fork /
ACP / Codex / dsh SDK): instead of hard-coding a single execution path, tasks
carry a ``provider`` name and the runner dispatches through this registry.

The default ``in-process`` provider runs the task with the existing
orchestrator chat loop (same behaviour as before). Additional providers can be
registered at runtime (e.g. a pool-backed or external-protocol provider).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from ai.subagent.capabilities import SubagentCapabilities
from ai.subagent.models import SubagentResult, SubagentTask

ProviderFn = Callable[..., Awaitable[SubagentResult]]

_PROVIDERS: dict[str, ProviderFn] = {}
_PROVIDER_CAPABILITIES: dict[str, SubagentCapabilities] = {}


def register_provider(
  name: str,
  fn: ProviderFn,
  capabilities: SubagentCapabilities | None = None,
) -> None:
  """Register a subagent provider implementation with its capability matrix."""
  _PROVIDERS[name] = fn
  _PROVIDER_CAPABILITIES[name] = capabilities or SubagentCapabilities()


def get_provider(name: str) -> ProviderFn | None:
  return _PROVIDERS.get(name)


def get_provider_capabilities(name: str) -> SubagentCapabilities:
  """Declared capability matrix; unknown providers get an all-off matrix."""
  return _PROVIDER_CAPABILITIES.get(name, SubagentCapabilities())


def list_providers() -> list[str]:
  return sorted(_PROVIDERS.keys())


def _register_defaults() -> None:
  if "in-process" in _PROVIDERS:
    return

  async def in_process(
    task: SubagentTask,
    *,
    params: Any,
    tools: list[dict[str, Any]] | None = None,
    max_tool_rounds: int = 24,
    emit: Callable | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    session_log_path: str | None = None,
    runner: Any = None,
  ) -> SubagentResult:
    """Default provider: delegate to the orchestrator chat loop (no recursion).

    Builds the same request the legacy runner built and returns a normalized
    SubagentResult. ``runner`` is ignored here — this provider IS the default
    in-process execution path.
    """
    # Imported at call time: keeps module import cheap so capability checks
    # and registration work on hosts without the openpilot/cereal toolchain.
    from ai.agents.orchestrator import run_chat_with_agents
    from ai.subagent.runner import SubagentRunner
    from ai.subagent.models import SubagentResult as SR

    events: list[dict[str, Any]] = []

    async def _emit(event: dict[str, Any]) -> None:
      events.append(event)
      if emit is not None:
        await emit(event)

    body = SubagentRunner()._build_body(task)
    try:
      result = await run_chat_with_agents(
        body,
        params,
        _emit,
        get_state_reader=getattr(runner, "get_state_reader", None) if runner else None,
        get_tool_handlers=getattr(runner, "get_tool_handlers", None) if runner else None,
        tools=tools,
        max_tool_rounds=max_tool_rounds,
        is_cancelled=is_cancelled,
        session_log_path=session_log_path,
      )
    except Exception as e:
      return SR(task_id=task.id, ok=False, stop_reason="error", error=str(e), events=events)

    ok = bool(result.get("ok", False))
    output = "".join(str(e.get("delta") or "") for e in events if e.get("type") == "content").strip()
    return SR(task_id=task.id, ok=ok, output=output, stop_reason="completed" if ok else "error", error=result.get("error", ""), events=events)

  register_provider(
    "in-process",
    in_process,
    SubagentCapabilities(
      agent_options=False,
      output_schema=True,
      depth_limit=True,
      tool_filter=True,
      persona=False,
    ),
  )

  # Capability matrices for the external provider family. Their EXECUTION is
  # externally blocked (G13 ACP / G14 Codex need an external harness binary),
  # so no provider fn is registered — only the declared capability matrix, so
  # a capability check can still reject unsupported requests loudly when one
  # of these providers is later wired in. These are NOT faked executions.
  _PROVIDER_CAPABILITIES.setdefault(
    "fork", SubagentCapabilities(agent_options=True, output_schema=True,
                                 depth_limit=True, tool_filter=True, persona=True)
  )
  _PROVIDER_CAPABILITIES.setdefault(
    "acp", SubagentCapabilities(agent_options=True, output_schema=True,
                                depth_limit=True, tool_filter=True, persona=True)
  )
  _PROVIDER_CAPABILITIES.setdefault(
    "codex", SubagentCapabilities(agent_options=True, output_schema=True,
                                  depth_limit=True, tool_filter=True, persona=True)
  )


_register_defaults()
