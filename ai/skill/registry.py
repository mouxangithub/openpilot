"""Skill registry with policy-aware invocation."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from ai.skill.conflicts import SkillConflictReport, check_conflicts
from ai.skill.diagnostics import SkillDiagnosticsReport, diagnose_skill
from ai.skill.models import (
  Skill,
  SkillError,
  SkillInvocation,
  SkillParameter,
  SkillPolicy,
)
from ai.skill.session_registry import SessionSkillRegistry
from ai.skill.semver import Semver

_SKILL_BASE_DIR: Path | None = None


def set_skill_base_dir(path: Path | str) -> None:
  global _SKILL_BASE_DIR
  _SKILL_BASE_DIR = Path(path)


def get_skill_registry() -> SkillRegistry:
  base = _SKILL_BASE_DIR
  if base is None:
    from ai.system.paths import workspace_path
    base = Path(workspace_path()) / "ai_skills"
  return SkillRegistry(base)


class SkillRegistry:
  """In-memory skill registry with JSON manifest persistence."""

  def __init__(self, base_dir: Path | str) -> None:
    self.base_dir = Path(base_dir)
    self.base_dir.mkdir(parents=True, exist_ok=True)
    self._lock = threading.RLock()
    self._skills: dict[str, Skill] = {}
    self._revision: int = 0
    self._change_listeners: list[Callable[[str], None]] = []
    self._load_manifest()

  def on_change(self, listener: Callable[[str], None]) -> Callable[[], None]:
    """Subscribe to ``skills/change``-style notifications (D-P0.3).

    Called with the event name (e.g. ``"skill/register"`` / ``"skill/remove"``)
    whenever the registry mutates. Returns an unsubscribe callable.
    """
    with self._lock:
      self._change_listeners.append(listener)
    return lambda: self._notify_remove_listener(listener)

  def _notify_remove_listener(self, listener: Callable[[str], None]) -> None:
    with self._lock:
      if listener in self._change_listeners:
        self._change_listeners.remove(listener)

  def _notify_change(self, event: str) -> None:
    self._revision += 1
    with self._lock:
      listeners = list(self._change_listeners)
    for listener in listeners:
      try:
        listener(event)
      except Exception:
        pass

  @property
  def revision(self) -> int:
    """Monotonic revision counter; consumers use it to invalidate caches."""
    return self._revision

  @property
  def _manifest_path(self) -> Path:
    return self.base_dir / "manifest.json"

  def _load_manifest(self) -> None:
    if not self._manifest_path.exists():
      return
    try:
      with open(self._manifest_path, encoding="utf-8") as f:
        data = json.load(f)
      for item in data.get("skills", []):
        self._skills[item["id"]] = Skill.from_dict(item)
    except (json.JSONDecodeError, OSError, KeyError):
      pass

  def _save_manifest(self) -> None:
    data = {"skills": [s.to_dict() for s in self._skills.values()]}
    tmp = self._manifest_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
      json.dump(data, f, ensure_ascii=False, indent=2)
      f.flush()
      os.fsync(f.fileno())
    tmp.replace(self._manifest_path)

  def register(
    self,
    skill: Skill,
    handler: Callable[..., Any] | None = None,
  ) -> Skill:
    if handler is not None:
      skill.handler = handler
    with self._lock:
      self._skills[skill.id] = skill
      self._save_manifest()
    self._notify_change("skill/register")
    return skill

  def register_from_dict(
    self,
    data: dict[str, Any],
    handler: Callable[..., Any] | None = None,
  ) -> Skill:
    skill = Skill.from_dict(data, handler=handler)
    return self.register(skill)

  def unregister(self, skill_id: str) -> bool:
    with self._lock:
      removed = self._skills.pop(skill_id, None) is not None
      if removed:
        self._save_manifest()
    if removed:
      self._notify_change("skill/remove")
    return removed

  def get(self, skill_id: str) -> Skill:
    with self._lock:
      skill = self._skills.get(skill_id)
    if skill is None:
      raise SkillError(f"skill {skill_id} not found", "SKILL_NOT_FOUND")
    return skill

  def list_skills(self) -> list[Skill]:
    with self._lock:
      return list(self._skills.values())

  def list_skills_sorted(self) -> list[Skill]:
    """Skills ordered by rank asc (lower rank = higher priority), then id.

    Mirrors the dsh ``compareIndexedCandidates`` ordering (D-P0.3) so toolsets
    and the Web panel can present skills deterministically.
    """
    return sorted(self.list_skills(), key=lambda s: (int(getattr(s, "rank", 600)), s.id))

  def _validate_args(self, skill: Skill, args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for param in skill.parameters:
      if param.name in args:
        out[param.name] = args[param.name]
      elif param.required:
        raise SkillError(
          f"missing required parameter {param.name}",
          "SKILL_INVALID_ARGS",
        )
    return out

  def request_invocation(
    self,
    skill_id: str,
    args: dict[str, Any],
    request_id: str | None = None,
    auto_confirm: bool = False,
    *,
    caller: str = "model",
  ) -> SkillInvocation:
    """Policy-aware invocation. Returns pending for confirm skills unless auto_confirm."""
    skill = self.get(skill_id)
    if skill.policy == "disabled":
      raise SkillError(f"skill {skill_id} is disabled", "SKILL_DISABLED")

    # D-P1.3: enforce explicit model/user invocation policy. Legacy skills
    # deserialize with the permissive default for backwards compatibility.
    invocation_policy = getattr(skill, "invocation_policy", None)
    if invocation_policy is not None:
      if caller == "model" and not invocation_policy.model_invocable:
        raise SkillError(f"skill {skill_id} is not model-invocable", "SKILL_REQUIRES_CONFIRMATION")
      if caller == "user" and not invocation_policy.user_invocable:
        raise SkillError(f"skill {skill_id} is not user-invocable", "SKILL_REQUIRES_CONFIRMATION")

    validated = self._validate_args(skill, args)
    invocation = SkillInvocation(
      skill_id=skill_id,
      args=validated,
      status="pending",
      request_id=request_id or uuid.uuid4().hex,
    )

    if skill.policy == "confirm" and not auto_confirm:
      invocation.status = "pending"
      return invocation

    return self._execute(skill, invocation)

  def _execute(self, skill: Skill, invocation: SkillInvocation) -> SkillInvocation:
    if skill.handler is None:
      invocation.status = "error"
      invocation.error = f"skill {skill.id} has no handler"
      return invocation
    invocation.status = "running"
    try:
      invocation.result = skill.handler(**invocation.args)
      invocation.status = "success"
    except Exception as e:
      invocation.status = "error"
      invocation.error = str(e)
    return invocation

  def confirm_invocation(self, request_id: str) -> SkillInvocation | None:
    """Synchronous confirmation placeholder; real flow would persist pending requests."""
    return None

  def for_session(self, session_id: str) -> SessionSkillRegistry:
    """Create a session-local overlay view of this registry."""
    return SessionSkillRegistry(session_id, self)

  def dispose(self, skill_id: str) -> dict[str, Any]:
    """Dispose a global skill by calling its dispose handler if present.

    The skill remains registered but marked disabled if dispose fails.
    """
    try:
      skill = self.get(skill_id)
    except SkillError as e:
      return {"ok": False, "skill_id": skill_id, "error": e.message}

    error = ""
    try:
      if skill.handler is not None and hasattr(skill.handler, "dispose"):
        dispose_fn = getattr(skill.handler, "dispose")
        if callable(dispose_fn):
          dispose_fn()
    except Exception as e:
      error = str(e)
      skill.policy = "disabled"
      self._save_manifest()

    return {"ok": not bool(error), "skill_id": skill_id, "error": error or None}

  def diagnose(self, skill_id: str) -> SkillDiagnosticsReport:
    """Return a structured diagnostics report for a skill."""
    try:
      skill = self.get(skill_id)
    except SkillError as e:
      return SkillDiagnosticsReport(
        skill_id=skill_id,
        ok=False,
        error=e.message,
      )
    return diagnose_skill(skill, resolve_dependency=self.get)

  def check_conflicts(self) -> SkillConflictReport:
    """Detect duplicate skill ids, cyclic dependencies and missing deps."""
    return check_conflicts(self.list_skills(), resolve_dependency=self.get)

  def build_tool_definitions(self) -> list[dict[str, Any]]:
    """Return OpenAI-style function definitions for registered skills."""
    tools = []
    for skill in self.list_skills():
      if skill.policy == "disabled":
        continue
      properties: dict[str, Any] = {}
      required: list[str] = []
      for param in skill.parameters:
        properties[param.name] = {
          "type": param.type,
          "description": param.description,
        }
        if param.required:
          required.append(param.name)
      tools.append({
        "type": "function",
        "function": {
          "name": skill.id,
          "description": skill.description,
          "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
          },
        },
      })
    return tools
