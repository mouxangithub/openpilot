"""WorkflowEngine interpreter for the P2 incremental runtime.

The engine runs ``WorkflowDefinition`` objects step by step, emitting lifecycle
events to registered sinks and producing a structured ``WorkflowResult``.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from ai.core.workflow.context import RunContext, Scope
from ai.core.workflow.definition import Step, StepKind, WorkflowDefinition
from ai.core.workflow.errors import WorkflowError, WorkflowErrorCode
from ai.core.workflow.events import WorkflowEvent, WorkflowEventFactory


EventSink = Callable[[WorkflowEvent], Awaitable[None]]
ToolRunner = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]
AgentRunner = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
GraphRunner = Callable[[str, dict[str, Any] | None], Awaitable[dict[str, Any]]]


@dataclass
class WorkflowResult:
  """Outcome of running a workflow definition."""

  ok: bool = True
  output: Any = None
  error: WorkflowErrorCode = WorkflowErrorCode.INVALID_DEFINITION
  message: str = ""
  phases: list[dict[str, Any]] = field(default_factory=list)
  logs: list[str] = field(default_factory=list)

  def to_dict(self) -> dict[str, Any]:
    return {
      "ok": self.ok,
      "output": self.output,
      "error": self.error.value,
      "message": self.message,
      "phases": list(self.phases),
      "logs": list(self.logs),
    }


class StepExecutor:
  """Executes a single step within a ``RunContext``.

  Tool/agent/graph runners are injected so the engine stays testable without
  touching real infrastructure.
  """

  def __init__(
    self,
    tool_runner: ToolRunner | None = None,
    agent_runner: AgentRunner | None = None,
    graph_runner: GraphRunner | None = None,
  ) -> None:
    self.tool_runner = tool_runner
    self.agent_runner = agent_runner
    self.graph_runner = graph_runner

  async def execute(
    self,
    step: Step,
    ctx: RunContext,
    emit: Callable[[WorkflowEvent], Awaitable[None]],
    factory: WorkflowEventFactory,
  ) -> Any:
    """Execute ``step`` and return its result value."""
    phase_id = f"{ctx.run_id}:{step.id}"
    phase = ctx.enter_phase(phase_id, step.id, step.kind.value)
    await emit(factory.phase_start(phase_id, step.id, step.kind.value))

    try:
      ctx.check_cancelled()
      result = await self._execute_body(step, ctx, emit, factory, phase_id)
      phase["ok"] = True
      phase["output"] = result
      if step.output_binding:
        ctx.set(step.output_binding, result)
      ctx.bind_step_output(step.id, result)
      await emit(factory.phase_log(phase_id, f"step '{step.id}' completed", extra={"kind": step.kind.value}))
      await emit(factory.phase_end(phase_id, ok=True, output=result))
      return result
    except WorkflowError:
      raise
    except Exception as exc:
      phase["ok"] = False
      phase["error"] = str(exc)
      ctx.log(f"step '{step.id}' failed: {exc}")
      await emit(factory.phase_log(phase_id, f"step '{step.id}' failed: {exc}", level="error"))
      await emit(factory.phase_end(phase_id, ok=False, output={"error": str(exc)}))
      if step.retry.on_error == "continue":
        return {"ok": False, "error": str(exc)}
      raise WorkflowError(
        f"step '{step.id}' failed: {exc}",
        WorkflowErrorCode.TOOL_FAILED if step.kind == StepKind.TOOL else WorkflowErrorCode.AGENT_FAILED,
      ) from exc

  async def _execute_body(
    self,
    step: Step,
    ctx: RunContext,
    emit: Callable[[WorkflowEvent], Awaitable[None]],
    factory: WorkflowEventFactory,
    phase_id: str,
  ) -> Any:
    if step.kind == StepKind.TOOL:
      return await self._run_tool(step, ctx)
    if step.kind == StepKind.AGENT:
      return await self._run_agent(step, ctx, emit, factory, phase_id)
    if step.kind == StepKind.PARALLEL:
      return await self._run_parallel(step, ctx, emit, factory)
    if step.kind == StepKind.CONDITION:
      return await self._run_condition(step, ctx, emit, factory)
    if step.kind == StepKind.LOOP:
      return await self._run_loop(step, ctx, emit, factory)
    if step.kind == StepKind.GRAPH:
      return await self._run_graph(step, ctx)
    if step.kind == StepKind.LOG:
      return await self._run_log(step, ctx)
    raise WorkflowError(
      f"unsupported step kind '{step.kind.value}'",
      WorkflowErrorCode.INVALID_DEFINITION,
    )

  async def _run_tool(self, step: Step, ctx: RunContext) -> Any:
    inputs = ctx.resolve_value(dict(step.inputs))
    tool_name = str(inputs.pop("tool", "") or step.id)
    if not tool_name:
      raise WorkflowError("tool step missing tool name", WorkflowErrorCode.TOOL_NOT_FOUND)
    if self.tool_runner is None:
      raise WorkflowError("no tool runner configured", WorkflowErrorCode.TOOL_NOT_FOUND)
    # Allow cancellation/dispose to interrupt slow tool calls.
    result = await self.tool_runner(tool_name, inputs)
    ctx.check_cancelled()
    return result

  async def _run_agent(
    self,
    step: Step,
    ctx: RunContext,
    emit: Callable[[WorkflowEvent], Awaitable[None]],
    factory: WorkflowEventFactory,
    phase_id: str,
  ) -> Any:
    if self.agent_runner is None:
      raise WorkflowError("no agent runner configured", WorkflowErrorCode.AGENT_FAILED)
    prompt = str(step.agent.get("prompt") or "")
    agent_id = str(step.agent.get("id") or f"agent-{step.id}")
    await emit(factory.agent_start(phase_id, agent_id, prompt))
    try:
      result = await self.agent_runner(step.agent)
    except Exception as exc:
      await emit(factory.agent_end(phase_id, agent_id, ok=False, result={"error": str(exc)}))
      raise
    await emit(factory.agent_end(phase_id, agent_id, ok=True, result=result))
    return result

  async def _run_parallel(
    self,
    step: Step,
    ctx: RunContext,
    emit: Callable[[WorkflowEvent], Awaitable[None]],
    factory: WorkflowEventFactory,
  ) -> dict[str, Any]:
    if not step.parallel:
      return {}

    async def _run_branch(branch: Step) -> dict[str, Any]:
      child_ctx = RunContext(
        run_id=ctx.run_id,
        inputs=ctx.inputs,
        scope=Scope(parent=ctx.scope),
        cancelled=ctx.cancelled,
        disposed=ctx.disposed,
        cancel_event=ctx.cancel_event,
      )
      executor = StepExecutor(
        tool_runner=self.tool_runner,
        agent_runner=self.agent_runner,
        graph_runner=self.graph_runner,
      )
      try:
        value = await executor.execute(branch, child_ctx, emit, factory)
        return {"id": branch.id, "ok": True, "output": value}
      except WorkflowError as we:
        return {"id": branch.id, "ok": False, "error": str(we), "code": we.code.value}
      except Exception as exc:
        return {"id": branch.id, "ok": False, "error": str(exc)}

    results = await asyncio.gather(*[_run_branch(b) for b in step.parallel])
    merged: dict[str, Any] = {"results": results}
    for r in results:
      if r.get("ok") and r.get("id"):
        merged[r["id"]] = r.get("output")
    return merged

  async def _run_condition(
    self,
    step: Step,
    ctx: RunContext,
    emit: Callable[[WorkflowEvent], Awaitable[None]],
    factory: WorkflowEventFactory,
  ) -> Any:
    taken = ctx.evaluate_condition(step.condition)
    branch_step = None
    # Evaluate branches in order and take the first whose own condition is true.
    # The first branch with no explicit condition acts as a default/else.
    default_branch: Step | None = None
    for branch in step.branches:
      if branch.condition:
        if ctx.evaluate_condition(branch.condition):
          branch_step = branch
          break
      elif default_branch is None:
        default_branch = branch
    if branch_step is None:
      branch_step = default_branch
    if branch_step is None:
      return {"taken": taken}
    executor = StepExecutor(
      tool_runner=self.tool_runner,
      agent_runner=self.agent_runner,
      graph_runner=self.graph_runner,
    )
    value = await executor.execute(branch_step, ctx, emit, factory)
    return {"taken": taken, "branch": branch_step.id, "output": value}

  async def _run_loop(
    self,
    step: Step,
    ctx: RunContext,
    emit: Callable[[WorkflowEvent], Awaitable[None]],
    factory: WorkflowEventFactory,
  ) -> list[Any]:
    iterable = self._parse_loop(step.for_each, ctx)
    collected: list[Any] = []
    executor = StepExecutor(
      tool_runner=self.tool_runner,
      agent_runner=self.agent_runner,
      graph_runner=self.graph_runner,
    )
    for item in iterable:
      ctx.check_cancelled()
      loop_scope = Scope(parent=ctx.scope)
      loop_scope.set("item", item)
      loop_ctx = RunContext(
        run_id=ctx.run_id,
        inputs=ctx.inputs,
        scope=loop_scope,
        cancelled=ctx.cancelled,
        disposed=ctx.disposed,
        cancel_event=ctx.cancel_event,
      )
      # Copy accumulated outputs/phases/logs references so child steps append.
      loop_ctx.outputs = ctx.outputs
      loop_ctx.phases = ctx.phases
      loop_ctx.logs = ctx.logs
      value = await executor.execute(step.branches[0], loop_ctx, emit, factory)
      collected.append(value)
    return collected

  def _parse_loop(self, for_each: str, ctx: RunContext) -> list[Any]:
    """Parse ``for_each`` like ``item in ${steps.list.output.args.items}``."""
    if " in " not in for_each:
      raise WorkflowError(f"invalid for_each expression: {for_each}", WorkflowErrorCode.INVALID_DEFINITION)
    var_name, _, expr = for_each.partition(" in ")
    var_name = var_name.strip()
    expr = expr.strip()
    if not var_name or not expr:
      raise WorkflowError(f"invalid for_each expression: {for_each}", WorkflowErrorCode.INVALID_DEFINITION)
    # If the expression is a single ${...}, resolve_value returns the raw
    # structured value rather than a JSON string.
    iterable = ctx.resolve_value(expr)
    if iterable is None:
      return []
    if isinstance(iterable, dict):
      return [iterable]
    if not isinstance(iterable, list):
      return [iterable]
    return list(iterable)

  async def _run_graph(self, step: Step, ctx: RunContext) -> Any:
    if self.graph_runner is None:
      raise WorkflowError("no graph runner configured", WorkflowErrorCode.AGENT_FAILED)
    inputs = ctx.resolve_value(dict(step.inputs))
    return await self.graph_runner(step.graph_id, inputs)

  async def _run_log(self, step: Step, ctx: RunContext) -> Any:
    message = str(ctx.resolve_value(step.inputs.get("message") or step.description or ""))
    ctx.log(message)
    return {"logged": message}


class WorkflowEngine:
  """Entry point for workflow runs."""

  def __init__(self) -> None:
    self._runs: dict[str, RunContext] = {}
    self._sinks: list[EventSink] = []
    self._tool_runner: ToolRunner | None = None
    self._agent_runner: AgentRunner | None = None
    self._graph_runner: GraphRunner | None = None

  def register_event_sink(self, sink: EventSink) -> None:
    """Register an async callback that receives every workflow event."""
    self._sinks.append(sink)

  def set_tool_runner(self, runner: ToolRunner) -> None:
    """Set the async callable used for TOOL steps."""
    self._tool_runner = runner

  def set_agent_runner(self, runner: AgentRunner) -> None:
    """Set the async callable used for AGENT steps."""
    self._agent_runner = runner

  def set_graph_runner(self, runner: GraphRunner) -> None:
    """Set the async callable used for GRAPH steps."""
    self._graph_runner = runner

  async def _emit(self, event: WorkflowEvent) -> None:
    for sink in self._sinks:
      try:
        await sink(event)
      except Exception:
        pass

  async def run(
    self,
    definition: dict[str, Any] | WorkflowDefinition,
    inputs: dict[str, Any] | None = None,
    *,
    cancel_event: asyncio.Event | None = None,
  ) -> WorkflowResult:
    """Run a workflow definition to completion.

    Returns a ``WorkflowResult`` with ``ok``, ``output``, ``error``, ``message``,
    ``phases`` and ``logs``.
    """
    run_id = uuid.uuid4().hex
    inputs = dict(inputs or {})

    try:
      if isinstance(definition, dict):
        defn = WorkflowDefinition.from_dict(definition)
      else:
        defn = definition
      errors = defn.validate()
      if errors:
        return WorkflowResult(
          ok=False,
          error=WorkflowErrorCode.INVALID_DEFINITION,
          message="; ".join(errors),
        )
    except WorkflowError as we:
      return WorkflowResult(ok=False, error=we.code, message=we.message)
    except Exception as exc:
      return WorkflowResult(
        ok=False,
        error=WorkflowErrorCode.INVALID_DEFINITION,
        message=f"invalid definition: {exc}",
      )

    ctx = RunContext(run_id=run_id, inputs=inputs, cancel_event=cancel_event or asyncio.Event())
    self._runs[run_id] = ctx
    factory = WorkflowEventFactory(run_id)

    await self._emit(factory.workflow_start(defn.id, defn.name, inputs))

    if ctx.disposed:
      await self._emit(factory.workflow_end(False, error="disposed", code=WorkflowErrorCode.DISPOSED.value))
      del self._runs[run_id]
      return WorkflowResult(
        ok=False,
        error=WorkflowErrorCode.DISPOSED,
        message="workflow disposed before run",
      )

    executor = StepExecutor(
      tool_runner=self._tool_runner,
      agent_runner=self._agent_runner,
      graph_runner=self._graph_runner,
    )

    try:
      for step in defn.steps:
        ctx.check_cancelled()
        await executor.execute(step, ctx, self._emit, factory)

      # Compute outputs from output expressions
      outputs: dict[str, Any] = {}
      for key, expr in (defn.outputs or {}).items():
        outputs[key] = ctx.resolve_value(expr)

      await self._emit(factory.workflow_end(True, output=outputs, code=""))
      return WorkflowResult(
        ok=True,
        output=outputs,
        error=WorkflowErrorCode.INVALID_DEFINITION,
        message="workflow completed",
        phases=list(ctx.phases),
        logs=list(ctx.logs),
      )
    except WorkflowError as we:
      await self._emit(factory.workflow_end(False, error=we.message, code=we.code.value))
      return WorkflowResult(
        ok=False,
        error=we.code,
        message=we.message,
        phases=list(ctx.phases),
        logs=list(ctx.logs),
      )
    except Exception as exc:
      await self._emit(factory.workflow_end(False, error=str(exc), code=WorkflowErrorCode.TOOL_FAILED.value))
      return WorkflowResult(
        ok=False,
        error=WorkflowErrorCode.TOOL_FAILED,
        message=str(exc),
        phases=list(ctx.phases),
        logs=list(ctx.logs),
      )
    finally:
      if run_id in self._runs:
        del self._runs[run_id]

  def cancel(self, run_id: str) -> bool:
    """Request cancellation of an in-flight run."""
    run = self._runs.get(run_id)
    if run is None:
      return False
    run.cancelled = True
    run.cancel_event.set()
    return True

  def dispose(self, run_id: str) -> bool:
    """Dispose a run so it cannot proceed past its next checkpoint."""
    run = self._runs.get(run_id)
    if run is None:
      return False
    run.disposed = True
    run.cancel_event.set()
    return True

  def get_run_context(self, run_id: str) -> RunContext | None:
    """Return the active run context for inspection (AgentLoop integration)."""
    return self._runs.get(run_id)
