"""Built-in skill handlers and registration helper."""

from __future__ import annotations

import time
from typing import Any

from ai.skill.models import Skill, SkillDependency, SkillParameter
from ai.skill.registry import SkillRegistry


def _echo(message: str = "") -> str:
  return message


def _get_time() -> dict[str, Any]:
  return {"iso": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "timestamp": time.time()}


def _workspace_summary() -> dict[str, Any]:
  from ai.system.paths import path_summary
  return path_summary()


def register_builtins(registry: SkillRegistry) -> None:
  """Register safe built-in skills that do not require external APIs."""
  builtins = [
    Skill(
      id="echo",
      name="Echo",
      description="Returns the input message unchanged. Useful for testing.",
      policy="auto",
      parameters=[SkillParameter(name="message", type="string", description="Message to echo")],
      handler=_echo,
      scope="global",
      version="1.0.0",
      capabilities=["io"],
      source="builtin:core",
    ),
    Skill(
      id="get_time",
      name="Get time",
      description="Returns current local time.",
      policy="auto",
      parameters=[],
      handler=_get_time,
      scope="global",
      version="1.0.0",
      capabilities=["time"],
      source="builtin:core",
    ),
    Skill(
      id="workspace_summary",
      name="Workspace summary",
      description="Returns AI workspace path summary.",
      policy="auto",
      parameters=[],
      handler=_workspace_summary,
      scope="global",
      version="1.0.0",
      capabilities=["fs", "diagnostics"],
      source="builtin:core",
    ),
  ]
  for skill in builtins:
    registry.register(skill)
