"""Subagent pool — bounded concurrency and status tracking."""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from ai.subagent.lineage import SubagentLineage
from ai.subagent.models import SubagentResult, SubagentTask
from ai.subagent.runner import SubagentRunner, run_subagent


class SubagentPool:
  """Runs subagent tasks with a concurrency limit and tracks their status."""

  def __init__(
    self,
    *,
    max_concurrency: int = 4,
    runner: SubagentRunner | None = None,
    params: Any = None,
    tools: list[dict[str, Any]] | None = None,
    max_tool_rounds: int = 24,
    emit: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
  ) -> None:
    self.max_concurrency = max(1, max_concurrency)
    self.runner = runner or SubagentRunner()
    self.params = params
    self.tools = tools
    self.max_tool_rounds = max_tool_rounds
    self.emit = emit
    self._semaphore = asyncio.Semaphore(self.max_concurrency)
    self._tasks: dict[str, SubagentTask] = {}
    self._results: dict[str, SubagentResult] = {}
    self._lock = threading.Lock()
    self._cancelled: set[str] = set()
    self.lineage = SubagentLineage()

  def list_tasks(self) -> list[SubagentTask]:
    with self._lock:
      return list(self._tasks.values())

  def get_task(self, task_id: str) -> SubagentTask | None:
    with self._lock:
      return self._tasks.get(task_id)

  def get_result(self, task_id: str) -> SubagentResult | None:
    with self._lock:
      return self._results.get(task_id)

  def create_task(
    self,
    agent_id: str,
    prompt: str,
    *,
    session_id: str = "",
    workflow: str = "",
    tools: list[str] | None = None,
    output_schema: dict[str, Any] | None = None,
    parent_id: str | None = None,
    depth: int = 0,
    max_depth: int = 3,
    provider: str = "in-process",
    metadata: dict[str, Any] | None = None,
  ) -> SubagentTask:
    task = SubagentTask(
      id=f"sub-{uuid.uuid4()}",
      agent_id=agent_id,
      prompt=prompt,
      session_id=session_id,
      workflow=workflow,
      tools=tools,
      output_schema=output_schema,
      parent_id=parent_id,
      depth=depth,
      max_depth=max_depth,
      provider=provider,
      origin=str((metadata or {}).get("origin") or "user"),
      delegation_depth=depth,
      metadata=dict(metadata or {}),
    )
    with self._lock:
      self._tasks[task.id] = task
    try:
      self.lineage.add_edge(
        parent_task=parent_id or "",
        child_task=task.id,
        run_id=task.id,
        depth=depth,
        origin=str(task.origin or ((metadata or {}).get("origin")) or "tool"),
      )
    except Exception:
      pass  # lineage is best-effort
    return task

  def is_cancelled(self, task_id: str) -> bool:
    with self._lock:
      return task_id in self._cancelled

  def cancel(self, task_id: str) -> bool:
    with self._lock:
      if task_id not in self._tasks:
        return False
      self._cancelled.add(task_id)
      task = self._tasks[task_id]
      if task.status in ("completed", "failed", "cancelled"):
        return True
      task.status = "cancelled"
      return True

  async def submit(
    self,
    task: SubagentTask | dict[str, Any],
    *,
    params: Any | None = None,
    tools: list[dict[str, Any]] | None = None,
    max_tool_rounds: int | None = None,
    session_log: Any = None,
  ) -> asyncio.Task[SubagentResult]:
    if isinstance(task, dict):
      task = SubagentTask.from_dict(task)
    with self._lock:
      self._tasks[task.id] = task
      task.status = "pending"

    async def _run() -> SubagentResult:
      async with self._semaphore:
        with self._lock:
          if task.id in self._cancelled:
            task.status = "cancelled"
            result = SubagentResult(
              task_id=task.id,
              ok=False,
              stop_reason="aborted",
              error="cancelled before start",
            )
            self._results[task.id] = result
            return result
          task.status = "running"

        result = await run_subagent(
          task,
          params=params if params is not None else self.params,
          tools=tools if tools is not None else self.tools,
          max_tool_rounds=max_tool_rounds if max_tool_rounds is not None else self.max_tool_rounds,
          emit=self.emit,
          is_cancelled=lambda: self.is_cancelled(task.id),
          session_log=session_log,
          runner=self.runner,
        )

        with self._lock:
          self._results[task.id] = result
          task.status = "completed" if result.ok else "failed"
          if result.stop_reason == "aborted" or task.id in self._cancelled:
            task.status = "cancelled"
          task.result_summary = result.output[:200]
        return result

    return asyncio.create_task(_run())

  async def run(
    self,
    task: SubagentTask | dict[str, Any],
    *,
    params: Any | None = None,
    tools: list[dict[str, Any]] | None = None,
    max_tool_rounds: int | None = None,
    session_log: Any = None,
  ) -> SubagentResult:
    t = await self.submit(
      task,
      params=params,
      tools=tools,
      max_tool_rounds=max_tool_rounds,
      session_log=session_log,
    )
    return await t

  async def run_many(
    self,
    tasks: list[SubagentTask | dict[str, Any]],
    *,
    params: Any | None = None,
    tools: list[dict[str, Any]] | None = None,
    max_tool_rounds: int | None = None,
    session_log: Any = None,
  ) -> list[SubagentResult]:
    submitted = await asyncio.gather(*[
      self.submit(t, params=params, tools=tools, max_tool_rounds=max_tool_rounds, session_log=session_log)
      for t in tasks
    ])
    return await asyncio.gather(*submitted, return_exceptions=True)


_pool: SubagentPool | None = None


def get_subagent_pool(
  *,
  max_concurrency: int = 4,
  params: Any = None,
  tools: list[dict[str, Any]] | None = None,
) -> SubagentPool:
  global _pool
  if _pool is None:
    _pool = SubagentPool(
      max_concurrency=max_concurrency,
      params=params,
      tools=tools,
    )
  return _pool
