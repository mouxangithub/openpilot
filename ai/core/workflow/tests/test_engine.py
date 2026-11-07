"""WorkflowEngine interpreter tests for T04."""

from __future__ import annotations

import asyncio
import unittest
from typing import Any

import ai.tests.bootstrap_pc  # noqa: F401

from ai.core.workflow import WorkflowDefinition, WorkflowEngine, WorkflowErrorCode
from ai.core.workflow.definition import StepKind


async def _echo_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
  return {"ok": True, "tool": name, "args": args}


async def _add_tool(_name: str, args: dict[str, Any]) -> dict[str, Any]:
  a = args.get("a", 0)
  b = args.get("b", 0)
  if a == "" or a is None:
    a = 0
  if b == "" or b is None:
    b = 0
  try:
    result = float(a) + float(b)
  except Exception:
    result = 0
  return {"ok": True, "result": result}


async def _fake_agent(agent: dict[str, Any]) -> dict[str, Any]:
  return {"ok": True, "agent_id": agent.get("id", "fake"), "prompt": agent.get("prompt", "")}


async def _fake_graph(graph_id: str, inputs: dict[str, Any] | None) -> dict[str, Any]:
  return {"ok": True, "graph_id": graph_id, "inputs": inputs or {}}


class WorkflowEngineToolTests(unittest.IsolatedAsyncioTestCase):
  async def test_tool_step_runs_and_binds_output(self):
    engine = WorkflowEngine()
    engine.set_tool_runner(_echo_tool)

    definition = {
      "id": "tool-test",
      "steps": [
        {"id": "hello", "kind": "tool", "inputs": {"tool": "echo", "message": "hi"}},
      ],
      "outputs": {"reply": "${steps.hello.output}"},
    }

    result = await engine.run(definition)
    self.assertTrue(result.ok)
    self.assertEqual(result.output["reply"]["tool"], "echo")

  async def test_tool_not_found_returns_error(self):
    engine = WorkflowEngine()

    async def missing(_name: str, _args: dict[str, Any]) -> dict[str, Any]:
      raise RuntimeError("not found")

    engine.set_tool_runner(missing)
    result = await engine.run({
      "id": "missing-tool",
      "steps": [{"id": "x", "kind": "tool", "inputs": {"tool": "missing"}}],
    })
    self.assertFalse(result.ok)

  async def test_variable_binding_between_steps(self):
    engine = WorkflowEngine()
    engine.set_tool_runner(_add_tool)

    definition = {
      "id": "bind-test",
      "inputs_schema": {"a": "number", "b": "number"},
      "steps": [
        {"id": "sum", "kind": "tool", "inputs": {"tool": "add", "a": "${inputs.a}", "b": "${inputs.b}"}},
        {"id": "double", "kind": "tool", "inputs": {"tool": "add", "a": "${steps.sum.output.result}", "b": "${steps.sum.output.result}"}},
      ],
      "outputs": {"final": "${steps.double.output.result}"},
    }

    result = await engine.run(definition, {"a": 2, "b": 3})
    self.assertTrue(result.ok)
    self.assertEqual(result.output["final"], 10)


class WorkflowEngineConditionTests(unittest.IsolatedAsyncioTestCase):
  async def test_condition_takes_true_branch(self):
    engine = WorkflowEngine()
    engine.set_tool_runner(_echo_tool)

    definition = {
      "id": "cond-test",
      "steps": [
        {
          "id": "branch",
          "kind": "condition",
          "condition": "${inputs.go} == true",
          "branches": [
            {"id": "yes", "kind": "tool", "condition": "${inputs.go} == true", "inputs": {"tool": "echo", "value": "yes"}},
            {"id": "no", "kind": "tool", "condition": "${inputs.go} != true", "inputs": {"tool": "echo", "value": "no"}},
          ],
        },
      ],
      "outputs": {"out": "${steps.branch.output.output.args.value}"},
    }

    result = await engine.run(definition, {"go": True})
    self.assertTrue(result.ok)
    self.assertEqual(result.output["out"], "yes")

  async def test_condition_false_falls_back(self):
    engine = WorkflowEngine()
    engine.set_tool_runner(_echo_tool)

    definition = {
      "id": "cond-false",
      "steps": [
        {
          "id": "branch",
          "kind": "condition",
          "condition": "${inputs.go} == true",
          "branches": [
            {"id": "yes", "kind": "tool", "condition": "${inputs.go} == true", "inputs": {"tool": "echo", "value": "yes"}},
            {"id": "no", "kind": "tool", "condition": "${inputs.go} != true", "inputs": {"tool": "echo", "value": "no"}},
          ],
        },
      ],
      "outputs": {"out": "${steps.branch.output.output.args.value}"},
    }

    result = await engine.run(definition, {"go": False})
    self.assertTrue(result.ok)
    self.assertEqual(result.output["out"], "no")


class WorkflowEngineLoopTests(unittest.IsolatedAsyncioTestCase):
  async def test_loop_collects_results(self):
    engine = WorkflowEngine()

    async def runner(name: str, args: dict[str, Any]) -> dict[str, Any]:
      if name == "list_items":
        return {"ok": True, "args": args}
      if name == "add":
        a = args.get("a", 0)
        b = args.get("b", 0)
        if a == "" or a is None:
          a = 0
        if b == "" or b is None:
          b = 0
        try:
          result = float(a) + float(b)
        except Exception:
          result = 0
        return {"ok": True, "result": result}
      return {"ok": False, "error": "unknown"}

    engine.set_tool_runner(runner)

    definition = {
      "id": "loop-test",
      "steps": [
        {"id": "list", "kind": "tool", "inputs": {"tool": "list_items", "items": [1, 2, 3]}},
        {
          "id": "sum_each",
          "kind": "loop",
          "for_each": "item in ${steps.list.output.args.items}",
          "branches": [
            {"id": "inc", "kind": "tool", "inputs": {"tool": "add", "a": "${item}", "b": 10}},
          ],
        },
      ],
      "outputs": {"values": "${steps.sum_each.output}"},
    }

    result = await engine.run(definition)
    self.assertTrue(result.ok)
    self.assertEqual(result.output["values"], [{"ok": True, "result": 11.0}, {"ok": True, "result": 12.0}, {"ok": True, "result": 13.0}])


class WorkflowEngineParallelTests(unittest.IsolatedAsyncioTestCase):
  async def test_parallel_runs_branches(self):
    engine = WorkflowEngine()

    async def slow_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
      await asyncio.sleep(0.01)
      return {"ok": True, "name": name, "args": args}

    engine.set_tool_runner(slow_tool)

    definition = {
      "id": "parallel-test",
      "steps": [
        {
          "id": "fan",
          "kind": "parallel",
          "parallel": [
            {"id": "a", "kind": "tool", "inputs": {"tool": "echo", "v": 1}},
            {"id": "b", "kind": "tool", "inputs": {"tool": "echo", "v": 2}},
          ],
        },
      ],
      "outputs": {"a": "${steps.fan.output.a.args.v}", "b": "${steps.fan.output.b.args.v}"},
    }

    result = await engine.run(definition)
    self.assertTrue(result.ok)
    self.assertEqual(result.output["a"], 1)
    self.assertEqual(result.output["b"], 2)


class WorkflowEngineAgentTests(unittest.IsolatedAsyncioTestCase):
  async def test_agent_step_invokes_runner(self):
    engine = WorkflowEngine()
    engine.set_agent_runner(_fake_agent)

    definition = {
      "id": "agent-test",
      "steps": [
        {
          "id": "sub",
          "kind": "agent",
          "agent": {"id": "checker", "prompt": "check this", "tools": ["echo"], "max_rounds": 3},
        },
      ],
      "outputs": {"agent": "${steps.sub.output.agent_id}"},
    }

    result = await engine.run(definition)
    self.assertTrue(result.ok)
    self.assertEqual(result.output["agent"], "checker")


class WorkflowEngineGraphTests(unittest.IsolatedAsyncioTestCase):
  async def test_graph_step_invokes_runner(self):
    engine = WorkflowEngine()
    engine.set_graph_runner(_fake_graph)

    definition = {
      "id": "graph-test",
      "steps": [
        {"id": "g", "kind": "graph", "graph_id": "my-graph", "inputs": {"x": 1}},
      ],
      "outputs": {"graph_id": "${steps.g.output.graph_id}"},
    }

    result = await engine.run(definition)
    self.assertTrue(result.ok)
    self.assertEqual(result.output["graph_id"], "my-graph")


class WorkflowEngineLifecycleTests(unittest.IsolatedAsyncioTestCase):
  async def test_cancel_stops_run(self):
    engine = WorkflowEngine()

    async def slow_tool(_name: str, _args: dict[str, Any]) -> dict[str, Any]:
      await asyncio.sleep(5)
      return {"ok": True}

    engine.set_tool_runner(slow_tool)

    async def run_and_cancel() -> Any:
      nonlocal run_id
      task = asyncio.create_task(engine.run({
        "id": "cancel-test",
        "steps": [{"id": "slow", "kind": "tool", "inputs": {"tool": "sleep"}}],
      }))
      # Wait until the run context is registered so cancel() has a target.
      for _ in range(50):
        if engine.get_run_context(run_id) is not None:
          break
        await asyncio.sleep(0.001)
      engine.cancel(run_id)
      return await task

    run_id = ""
    events: list[dict[str, Any]] = []

    async def sink(event: Any) -> None:
      nonlocal run_id
      d = event.to_dict()
      events.append(d)
      if d.get("type") == "workflow/start":
        run_id = d.get("run_id", "")

    engine.register_event_sink(sink)
    result = await run_and_cancel()
    self.assertFalse(result.ok)
    self.assertEqual(result.error, WorkflowErrorCode.CANCELLED)

  async def test_dispose_stops_run(self):
    engine = WorkflowEngine()

    async def slow_tool(_name: str, _args: dict[str, Any]) -> dict[str, Any]:
      await asyncio.sleep(5)
      return {"ok": True}

    engine.set_tool_runner(slow_tool)
    events: list[dict[str, Any]] = []

    async def sink(event: Any) -> None:
      events.append(event.to_dict())

    engine.register_event_sink(sink)

    async def run_and_dispose() -> Any:
      nonlocal run_id
      task = asyncio.create_task(engine.run({
        "id": "dispose-test",
        "steps": [{"id": "slow", "kind": "tool", "inputs": {"tool": "sleep"}}],
      }))
      for _ in range(50):
        if engine.get_run_context(run_id) is not None:
          break
        await asyncio.sleep(0.001)
      engine.dispose(run_id)
      return await task

    run_id = ""
    events: list[dict[str, Any]] = []

    async def sink(event: Any) -> None:
      nonlocal run_id
      d = event.to_dict()
      events.append(d)
      if d.get("type") == "workflow/start":
        run_id = d.get("run_id", "")

    engine.register_event_sink(sink)
    result = await run_and_dispose()
    self.assertFalse(result.ok)
    self.assertEqual(result.error, WorkflowErrorCode.DISPOSED)


class WorkflowEngineDefinitionTests(unittest.IsolatedAsyncioTestCase):
  async def test_invalid_definition_returns_error(self):
    engine = WorkflowEngine()
    result = await engine.run({"id": "bad", "steps": []})
    self.assertFalse(result.ok)
    self.assertEqual(result.error, WorkflowErrorCode.INVALID_DEFINITION)

  async def test_duplicate_step_id_invalid(self):
    engine = WorkflowEngine()
    result = await engine.run({
      "id": "dup",
      "steps": [
        {"id": "x", "kind": "log"},
        {"id": "x", "kind": "log"},
      ],
    })
    self.assertFalse(result.ok)
    self.assertEqual(result.error, WorkflowErrorCode.INVALID_DEFINITION)


class WorkflowDefinitionParserTests(unittest.TestCase):
  def test_step_kind_enum(self):
    self.assertEqual(StepKind.TOOL.value, "tool")

  def test_from_dict_parses_nested(self):
    data = {
      "id": "parser-test",
      "steps": [
        {
          "id": "branch",
          "kind": "condition",
          "condition": "${inputs.ok} == true",
          "branches": [
            {"id": "yes", "kind": "tool", "inputs": {"tool": "echo"}},
          ],
        },
      ],
    }
    definition = WorkflowDefinition.from_dict(data)
    self.assertEqual(definition.steps[0].kind, StepKind.CONDITION)
    self.assertEqual(definition.steps[0].branches[0].kind, StepKind.TOOL)


if __name__ == "__main__":
  unittest.main()
