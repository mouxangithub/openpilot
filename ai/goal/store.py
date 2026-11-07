"""Goal store — durable JSON persistence with compare-and-set mutations."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from ai.goal.models import (
  CreateGoalRequest,
  EditGoalRequest,
  GoalActivation,
  GoalBlockReason,
  GoalError,
  GoalOperation,
  GoalPhase,
  GoalProjection,
  GoalRef,
  GoalSnapshot,
  GoalView,
)


_DEFAULT_MAX_GOAL_ROUNDS = 256


class GoalStore:
  def __init__(self, base_dir: Path | str) -> None:
    self.base_dir = Path(base_dir)
    self.base_dir.mkdir(parents=True, exist_ok=True)
    self._lock = threading.RLock()
    self._event_sink: Any = None

  def set_event_sink(self, sink: Any) -> None:
    """Bind an optional domain-event sink: sink(snapshot_dict, tombstone).

    When bound, every successful mutation emits a full-snapshot
    ``goal/change`` session event so state is replayable from the log.
    Unbound stores keep the legacy JSON-only behavior.
    """
    self._event_sink = sink

  def _emit_domain(self, snapshot: dict[str, Any], tombstone: bool = False) -> None:
    sink = self._event_sink
    if sink is None:
      return
    try:
      sink(snapshot, tombstone)
    except Exception:
      # Best-effort projection: the JSON store remains authoritative until
      # resume switches to fold-first replay.
      pass

  @property
  def _state_path(self) -> Path:
    return self.base_dir / "state.json"

  def _load_state(self) -> dict[str, Any]:
    if not self._state_path.exists():
      return {"current": None, "seenGoalIds": [], "failure": None}
    try:
      with open(self._state_path, encoding="utf-8") as f:
        return json.load(f)
    except (json.JSONDecodeError, OSError):
      return {"current": None, "seenGoalIds": [], "failure": None}

  def _save_state(self, state: dict[str, Any]) -> None:
    tmp = self._state_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
      json.dump(state, f, ensure_ascii=False, indent=2)
      f.flush()
      os.fsync(f.fileno())
    tmp.replace(self._state_path)

  def _current_projection(self) -> GoalProjection | None:
    current = self._load_state().get("current")
    return GoalProjection.from_dict(current) if current else None

  def _expect_current(self, ref: GoalRef) -> GoalProjection:
    current = self._current_projection()
    if current is None:
      raise GoalError("no current goal", "GOAL_NOT_FOUND")
    if current.goal.id != ref.id or current.goal.revision != ref.revision:
      raise GoalError(
        f"stale goal ref {ref.id} revision {ref.revision}; "
        f"current is {current.goal.id} revision {current.goal.revision}",
        "GOAL_STALE_REVISION",
      )
    return current

  @staticmethod
  def _resolve_objective(value: str) -> str:
    text = str(value).strip()
    if not text:
      raise GoalError("goal objective must be a non-empty string", "GOAL_INVALID_OBJECTIVE")
    return text

  @staticmethod
  def _resolve_max_rounds(value: int) -> int:
    if not isinstance(value, int) or value < 1:
      raise GoalError("maxGoalRounds must be a positive integer", "GOAL_INVALID_MAX_ROUNDS")
    return value

  @staticmethod
  def _resolve_block_reason(reason: dict[str, Any]) -> GoalBlockReason:
    code = str(reason.get("code", ""))
    message = str(reason.get("message", "")).strip()
    if not code or not message:
      raise GoalError(
        "goal block reason requires a code and a non-empty message",
        "GOAL_INVALID_BLOCK_REASON",
      )
    return GoalBlockReason(code=code, message=message)

  def _with_phase(self, current: GoalSnapshot, phase: GoalPhase) -> GoalSnapshot:
    return GoalSnapshot(
      id=current.id,
      revision=current.revision + 1,
      objective=current.objective,
      phase=phase,
      max_goal_rounds=current.max_goal_rounds,
      blocked_reason=current.blocked_reason,
    )

  def _commit(
    self,
    operation: GoalOperation,
    goal: GoalSnapshot,
    rounds_started: int,
    created_at: int,
    updated_at: int,
    activation: GoalActivation,
  ) -> GoalView:
    with self._lock:
      state = self._load_state()
      state["current"] = {
        "goal": goal.to_dict(),
        "roundsStarted": rounds_started,
        "createdAt": created_at,
        "updatedAt": updated_at,
      }
      if goal.id not in state["seenGoalIds"]:
        state["seenGoalIds"].append(goal.id)
      self._save_state(state)
    self._emit_domain(goal.to_dict())
    return GoalView(
      id=goal.id,
      revision=goal.revision,
      objective=goal.objective,
      phase=goal.phase,
      max_goal_rounds=goal.max_goal_rounds,
      blocked_reason=goal.blocked_reason,
      rounds_started=rounds_started,
      created_at=created_at,
      updated_at=updated_at,
      activation=activation,
    )

  def get(self) -> GoalView | None:
    current = self._current_projection()
    if current is None:
      return None
    return GoalView(
      id=current.goal.id,
      revision=current.goal.revision,
      objective=current.goal.objective,
      phase=current.goal.phase,
      max_goal_rounds=current.goal.max_goal_rounds,
      blocked_reason=current.goal.blocked_reason,
      rounds_started=current.rounds_started,
      created_at=current.created_at,
      updated_at=current.updated_at,
      activation="disarmed",
    )

  def create(self, request: CreateGoalRequest | dict[str, Any]) -> GoalView:
    req = request if isinstance(request, CreateGoalRequest) else CreateGoalRequest(**request)
    objective = self._resolve_objective(req.objective)
    max_rounds = self._resolve_max_rounds(req.max_goal_rounds or _DEFAULT_MAX_GOAL_ROUNDS)
    with self._lock:
      current = self._current_projection()
      if current is not None and current.goal.phase != "complete":
        raise GoalError(
          f"goal {current.goal.id} already exists with phase {current.goal.phase}",
          "GOAL_ALREADY_EXISTS",
        )
      now = int(time.monotonic() * 1000)
      goal = GoalSnapshot(
        id=f"goal-{uuid.uuid4()}",
        revision=1,
        objective=objective,
        phase="active",
        max_goal_rounds=max_rounds,
      )
      return self._commit("create", goal, 0, now, now, "armed")

  def edit(self, ref: GoalRef | dict[str, Any], request: EditGoalRequest | dict[str, Any]) -> GoalView:
    if isinstance(ref, dict):
      ref = GoalRef.from_dict(ref)
    req = request if isinstance(request, EditGoalRequest) else EditGoalRequest(**request)
    if req.objective is None and req.max_goal_rounds is None:
      raise GoalError("goal edit requires objective and/or maxGoalRounds", "GOAL_INVALID_EDIT")
    current = self._expect_current(ref)
    objective = self._resolve_objective(req.objective) if req.objective is not None else current.goal.objective
    max_rounds = self._resolve_max_rounds(req.max_goal_rounds) if req.max_goal_rounds is not None else current.goal.max_goal_rounds
    goal = GoalSnapshot(
      id=current.goal.id,
      revision=current.goal.revision + 1,
      objective=objective,
      phase=current.goal.phase,
      max_goal_rounds=max_rounds,
      blocked_reason=current.goal.blocked_reason,
    )
    return self._commit(
      "edit",
      goal,
      current.rounds_started,
      current.created_at,
      max(int(time.monotonic() * 1000), current.updated_at + 1),
      "disarmed",
    )

  def _transition(
    self,
    ref: GoalRef | dict[str, Any],
    operation: GoalOperation,
    allowed: set[GoalPhase],
    phase: GoalPhase,
    activation: GoalActivation,
  ) -> GoalView:
    if isinstance(ref, dict):
      ref = GoalRef.from_dict(ref)
    current = self._expect_current(ref)
    if current.goal.phase not in allowed:
      raise GoalError(
        f"cannot {operation} goal {current.goal.id} from phase {current.goal.phase}; "
        f"expected {', '.join(sorted(allowed))}",
        "GOAL_INVALID_TRANSITION",
      )
    goal = self._with_phase(current.goal, phase)
    return self._commit(
      operation,
      goal,
      current.rounds_started,
      current.created_at,
      max(int(time.monotonic() * 1000), current.updated_at + 1),
      activation,
    )

  def pause(self, ref: GoalRef | dict[str, Any]) -> GoalView:
    return self._transition(ref, "pause", {"active"}, "paused", "disarmed")

  def resume(self, ref: GoalRef | dict[str, Any]) -> GoalView:
    ref = GoalRef.from_dict(ref) if isinstance(ref, dict) else ref
    current = self._expect_current(ref)
    allowed: set[GoalPhase] = {"active", "paused", "blocked"}
    if current.goal.phase not in allowed:
      raise GoalError(
        f"cannot resume goal {current.goal.id} from phase {current.goal.phase}; "
        "expected active, paused or blocked",
        "GOAL_INVALID_TRANSITION",
      )
    if current.rounds_started >= current.goal.max_goal_rounds:
      raise GoalError(
        f"goal {current.goal.id} exhausted {current.goal.max_goal_rounds} goal rounds; "
        "increase maxGoalRounds before resuming",
        "GOAL_INVALID_TRANSITION",
      )
    goal = self._with_phase(current.goal, "active")
    return self._commit(
      "resume",
      goal,
      current.rounds_started,
      current.created_at,
      max(int(time.monotonic() * 1000), current.updated_at + 1),
      "armed",
    )

  def complete(self, ref: GoalRef | dict[str, Any]) -> GoalView:
    return self._transition(ref, "complete", {"active", "paused", "blocked"}, "complete", "disarmed")

  def block(self, ref: GoalRef | dict[str, Any], reason: dict[str, Any]) -> GoalView:
    ref = GoalRef.from_dict(ref) if isinstance(ref, dict) else ref
    current = self._expect_current(ref)
    if current.goal.phase != "active":
      raise GoalError(
        f"cannot block goal {current.goal.id} from phase {current.goal.phase}; expected active",
        "GOAL_INVALID_TRANSITION",
      )
    block_reason = self._resolve_block_reason(reason)
    goal = GoalSnapshot(
      id=current.goal.id,
      revision=current.goal.revision + 1,
      objective=current.goal.objective,
      phase="blocked",
      max_goal_rounds=current.goal.max_goal_rounds,
      blocked_reason=block_reason,
    )
    return self._commit(
      "block",
      goal,
      current.rounds_started,
      current.created_at,
      max(int(time.monotonic() * 1000), current.updated_at + 1),
      "disarmed",
    )

  def clear(self, ref: GoalRef | dict[str, Any]) -> GoalRef:
    ref = GoalRef.from_dict(ref) if isinstance(ref, dict) else ref
    current = self._expect_current(ref)
    tombstone = GoalRef(id=current.goal.id, revision=current.goal.revision + 1)
    with self._lock:
      state = self._load_state()
      state["current"] = None
      if tombstone.id not in state["seenGoalIds"]:
        state["seenGoalIds"].append(tombstone.id)
      self._save_state(state)
    return tombstone

  def increment_round(self) -> GoalView | None:
    with self._lock:
      state = self._load_state()
      current = state.get("current")
      if not current:
        return None
      proj = GoalProjection.from_dict(current)
      if proj.rounds_started >= proj.goal.max_goal_rounds:
        return None
      updated_proj = GoalProjection(
        goal=proj.goal,
        rounds_started=proj.rounds_started + 1,
        created_at=proj.created_at,
        updated_at=proj.updated_at,
      )
      state["current"] = updated_proj.to_dict()
      self._save_state(state)
      return GoalView(
        id=updated_proj.goal.id,
        revision=updated_proj.goal.revision,
        objective=updated_proj.goal.objective,
        phase=updated_proj.goal.phase,
        max_goal_rounds=updated_proj.goal.max_goal_rounds,
        blocked_reason=updated_proj.goal.blocked_reason,
        rounds_started=updated_proj.rounds_started,
        created_at=updated_proj.created_at,
        updated_at=updated_proj.updated_at,
        activation="disarmed",
      )

  def list_all(self) -> list[GoalView]:
    current = self.get()
    return [current] if current else []


_store: GoalStore | None = None


def set_goal_base_dir(base_dir: Path | str) -> None:
  global _store
  _store = GoalStore(base_dir)


def get_goal_store(base_dir: Path | str | None = None) -> GoalStore:
  global _store
  if base_dir is not None:
    return GoalStore(base_dir)
  if _store is None:
    default = Path(os.environ.get("AI_WORKSPACE", ".")) / "workspace" / "ai_goals"
    _store = GoalStore(default)
  return _store
