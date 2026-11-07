"""Plan store — durable JSON persistence for plans."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from ai.plan.models import Plan, PlanModeState, PlanProjection, PlanStep


class PlanStore:
  def __init__(self, base_dir: Path | str) -> None:
    self.base_dir = Path(base_dir)
    self.base_dir.mkdir(parents=True, exist_ok=True)
    self._lock = threading.Lock()
    self._event_sink: Any = None

  def set_event_sink(self, sink: Any) -> None:
    """Bind an optional domain-event sink: sink(snapshot_dict, tombstone).

    Every successful create/update/set_step_status emits a full-snapshot
    ``plan/change`` event; delete emits a tombstone. Unbound stores keep
    the legacy JSON-only behavior.
    """
    self._event_sink = sink

  def _emit_domain(self, snapshot: Any, tombstone: bool = False) -> None:
    sink = self._event_sink
    if sink is None:
      return
    try:
      sink(snapshot, tombstone)
    except Exception:
      # Best-effort projection; JSON store remains authoritative for now.
      pass

  @property
  def _plans_path(self) -> Path:
    return self.base_dir / "plans.json"

  @property
  def _mode_path(self) -> Path:
    return self.base_dir / "mode.json"

  def _load_plans(self) -> dict[str, Any]:
    if not self._plans_path.exists():
      return {"plans": {}}
    try:
      with open(self._plans_path, encoding="utf-8") as f:
        return json.load(f)
    except (json.JSONDecodeError, OSError):
      return {"plans": {}}

  def _save_plans(self, data: dict[str, Any]) -> None:
    tmp = self._plans_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
      json.dump(data, f, ensure_ascii=False, indent=2)
      f.flush()
      os.fsync(f.fileno())
    tmp.replace(self._plans_path)

  def _load_mode(self) -> PlanModeState:
    if not self._mode_path.exists():
      return PlanModeState()
    try:
      with open(self._mode_path, encoding="utf-8") as f:
        return PlanModeState.from_dict(json.load(f))
    except (json.JSONDecodeError, OSError):
      return PlanModeState()

  def _save_mode(self, state: PlanModeState) -> None:
    tmp = self._mode_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
      json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)
      f.flush()
      os.fsync(f.fileno())
    tmp.replace(self._mode_path)

  def _now(self) -> int:
    return int(time.monotonic() * 1000)

  def create(
    self,
    title: str,
    steps: list[dict[str, Any]] | None = None,
    goal_id: str | None = None,
    metadata: dict[str, Any] | None = None,
  ) -> Plan:
    plan = Plan(
      id=f"plan-{uuid.uuid4()}",
      title=title.strip(),
      status="draft",
      steps=[PlanStep.from_dict(s) if isinstance(s, dict) else s for s in (steps or [])],
      goal_id=goal_id,
      created_at=self._now(),
      updated_at=self._now(),
      metadata=dict(metadata or {}),
    )
    if not plan.title:
      raise ValueError("plan title must be non-empty")
    with self._lock:
      data = self._load_plans()
      data["plans"][plan.id] = plan.to_dict()
      self._save_plans(data)
    self._emit_domain(plan.to_dict())
    return plan

  def get(self, plan_id: str) -> Plan | None:
    data = self._load_plans()
    raw = data["plans"].get(plan_id)
    return Plan.from_dict(raw) if raw else None

  def update(self, plan_id: str, patch: dict[str, Any]) -> Plan:
    with self._lock:
      data = self._load_plans()
      raw = data["plans"].get(plan_id)
      if not raw:
        raise KeyError(f"plan {plan_id} not found")
      plan = Plan.from_dict(raw)
      if "title" in patch:
        plan.title = str(patch["title"]).strip()
      if "status" in patch:
        plan.status = str(patch["status"])
      if "steps" in patch:
        plan.steps = [PlanStep.from_dict(s) if isinstance(s, dict) else s for s in patch["steps"]]
      if "goalId" in patch or "goal_id" in patch:
        plan.goal_id = patch.get("goalId") or patch.get("goal_id")
      if "metadata" in patch:
        plan.metadata = dict(patch["metadata"])
      plan.updated_at = self._now()
      data["plans"][plan_id] = plan.to_dict()
      self._save_plans(data)
    self._emit_domain(plan.to_dict())
    return plan

  def delete(self, plan_id: str) -> bool:
    with self._lock:
      data = self._load_plans()
      if plan_id not in data["plans"]:
        return False
      deleted = data["plans"][plan_id]
      del data["plans"][plan_id]
      self._save_plans(data)
    self._emit_domain({"id": plan_id, "deleted": True}, tombstone=True)
    return True

  def list_all(self) -> list[Plan]:
    data = self._load_plans()
    return [Plan.from_dict(p) for p in data["plans"].values()]

  def set_step_status(self, plan_id: str, step_id: str, status: str) -> Plan:
    with self._lock:
      data = self._load_plans()
      raw = data["plans"].get(plan_id)
      if not raw:
        raise KeyError(f"plan {plan_id} not found")
      plan = Plan.from_dict(raw)
      step = plan.step_by_id(step_id)
      if step is None:
        raise KeyError(f"step {step_id} not found in plan {plan_id}")
      step.status = str(status)
      if plan.is_complete and plan.status == "active":
        plan.status = "complete"
      plan.updated_at = self._now()
      data["plans"][plan_id] = plan.to_dict()
      self._save_plans(data)
    self._emit_domain(plan.to_dict())
    return plan

  def activate(self, plan_id: str) -> Plan:
    return self.update(plan_id, {"status": "active"})

  def pause(self, plan_id: str) -> Plan:
    return self.update(plan_id, {"status": "paused"})

  def complete(self, plan_id: str) -> Plan:
    return self.update(plan_id, {"status": "complete"})

  def cancel(self, plan_id: str) -> Plan:
    return self.update(plan_id, {"status": "cancelled"})

  def get_mode(self) -> PlanProjection:
    state = self._load_mode()
    wanted = state.running_wanted if state.running_command_id else state.wanted
    return PlanProjection(
      active=state.active,
      pending=wanted is not None and wanted != state.active,
    )

  def set_mode(self, active: bool) -> PlanProjection:
    state = self._load_mode()
    state.active = bool(active)
    state.wanted = None
    self._save_mode(state)
    return self.get_mode()

  def select_mode(self, active: bool, command_id: str | None = None) -> PlanProjection:
    state = self._load_mode()
    if command_id:
      state.running_command_id = command_id
      state.running_wanted = active
    else:
      state.wanted = active
    self._save_mode(state)
    return self.get_mode()


_store: PlanStore | None = None


def set_plan_base_dir(base_dir: Path | str) -> None:
  global _store
  _store = PlanStore(base_dir)


def get_plan_store(base_dir: Path | str | None = None) -> PlanStore:
  global _store
  if base_dir is not None:
    return PlanStore(base_dir)
  if _store is None:
    default = Path(os.environ.get("AI_WORKSPACE", ".")) / "workspace" / "ai_plans"
    _store = PlanStore(default)
  return _store
