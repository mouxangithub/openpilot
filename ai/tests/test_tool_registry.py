"""Tests for the unified ToolRegistry (M1 / A-P0.1).

These tests are dependency-free: ``ai.tools.tool_registry`` imports only the
standard library, so no openpilot transitive dependency (zmq / capnp / Crypto)
is required. The ``registry_from_agent_tools`` bridge is exercised both with
injected providers (always) and against the real ``agent_tools`` when its
imports are available (skipped otherwise).
"""

from __future__ import annotations

import unittest

import ai.tests.bootstrap_pc  # noqa: F401  (install PC openpilot mocks)

from ai.tools.tool_registry import (
  ToolEntry,
  ToolRegistry,
  registry_from_agent_tools,
)


def _spec(name: str, description: str = "") -> dict:
  return {
    "type": "function",
    "function": {
      "name": name,
      "description": description,
      "parameters": {"type": "object", "properties": {}, "required": []},
    },
  }


def _echo(args: dict) -> dict:
  return {"ok": True, "echo": args}


class ToolRegistryCoreTests(unittest.TestCase):
  def test_register_and_lookup(self):
    reg = ToolRegistry()
    reg.register("echo", _echo, _spec("echo"), {"group": "read", "driving": True})
    self.assertIn("echo", reg)
    self.assertEqual(len(reg), 1)
    self.assertIs(reg.get("echo"), _echo)
    self.assertIs(reg.get_handler("echo"), _echo)
    self.assertEqual(reg.get_schema("echo")["function"]["name"], "echo")
    self.assertEqual(reg.get_capability("echo")["group"], "read")

  def test_register_fills_missing_function_name(self):
    reg = ToolRegistry()
    reg.register("bare", _echo, {})
    self.assertEqual(reg.get_schema("bare")["function"]["name"], "bare")
    self.assertEqual(reg.get_schema("bare")["type"], "function")

  def test_register_rejects_empty_name(self):
    reg = ToolRegistry()
    with self.assertRaises(ValueError):
      reg.register("", _echo, _spec("x"))

  def test_register_same_handler_is_idempotent(self):
    reg = ToolRegistry()
    reg.register("echo", _echo, _spec("echo"))
    reg.register("echo", _echo, _spec("echo"))  # same handler -> allowed
    self.assertEqual(len(reg), 1)

  def test_register_conflicting_handler_raises(self):
    reg = ToolRegistry()
    reg.register("echo", _echo, _spec("echo"))

    def other(_a):
      return {"ok": True}

    with self.assertRaises(ValueError):
      reg.register("echo", other, _spec("echo"))

  def test_schema_only_entry_has_no_handler(self):
    reg = ToolRegistry.from_parts([_spec("remote_tool")])
    self.assertIn("remote_tool", reg)
    self.assertIsNone(reg.get("remote_tool"))
    self.assertNotIn("remote_tool", reg.to_handlers_dict())

  def test_unregister(self):
    reg = ToolRegistry()
    reg.register("echo", _echo, _spec("echo"))
    self.assertTrue(reg.unregister("echo"))
    self.assertFalse(reg.unregister("echo"))
    self.assertNotIn("echo", reg)

  def test_handlers_schemas_all_views(self):
    reg = ToolRegistry()
    reg.register("a", _echo, _spec("a"), {"group": "read"})
    reg.register("b", None, _spec("b"), {"group": "write"})
    self.assertEqual(set(reg.handlers()), {"a"})
    self.assertEqual({s["function"]["name"] for s in reg.schemas()}, {"a", "b"})
    self.assertEqual(set(reg.all()), {"a", "b"})
    self.assertEqual(set(reg.names()), {"a", "b"})
    self.assertIsInstance(reg.all()["a"], dict)
    self.assertEqual(reg.all()["a"]["capability"]["group"], "read")

  def test_all_returns_entry_shape(self):
    reg = ToolRegistry()
    reg.register("a", _echo, _spec("a"))
    entry = reg.entry("a")
    self.assertIsInstance(entry, ToolEntry)
    self.assertEqual(entry.name, "a")
    self.assertEqual(entry.to_dict()["name"], "a")

  def test_to_handlers_dict_matches_legacy_style(self):
    reg = ToolRegistry()
    reg.register("a", _echo, _spec("a"))
    reg.register("b", _echo, _spec("b"))
    self.assertEqual(reg.to_handlers_dict(), reg.handlers())
    self.assertEqual(set(reg.to_handlers_dict()), {"a", "b"})


class ToolRegistryUpdateTests(unittest.TestCase):
  def test_update_with_registry(self):
    base = ToolRegistry()
    base.register("base", _echo, _spec("base"), {"group": "read"})
    extra = ToolRegistry()
    extra.register("extra", _echo, _spec("extra"), {"group": "write"})
    base.update(extra)
    self.assertEqual(set(base.names()), {"base", "extra"})
    self.assertEqual(base.get_capability("extra")["group"], "write")

  def test_update_with_legacy_dict(self):
    reg = ToolRegistry()
    reg.update({"legacy_a": _echo, "legacy_b": _echo})
    self.assertEqual(set(reg.names()), {"legacy_a", "legacy_b"})
    self.assertIs(reg.get("legacy_a"), _echo)

  def test_update_overwrites_last_wins(self):
    reg = ToolRegistry()
    reg.register("x", _echo, _spec("x"))

    def replacement(_a):
      return {"ok": True, "replaced": True}

    reg.update({"x": replacement})
    self.assertIs(reg.get("x"), replacement)


class ToolRegistryFilterTests(unittest.TestCase):
  def _reg(self) -> ToolRegistry:
    reg = ToolRegistry()
    reg.register("read_on", _echo, _spec("read_on"), {"group": "read", "default_enabled": True, "driving": True})
    reg.register("read_off", _echo, _spec("read_off"), {"group": "read", "default_enabled": False, "driving": True})
    reg.register("write_stat", _echo, _spec("write_stat"), {"group": "write", "default_enabled": True, "driving": False})
    reg.register("pc_only_tool", _echo, _spec("pc_only_tool"), {"group": "read", "default_enabled": True, "driving": True, "pc_only": True})
    return reg

  def test_filter_by_group(self):
    reg = self._reg()
    self.assertEqual(set(reg.filter_by_capability(group="read")), {"read_on", "read_off", "pc_only_tool"})
    self.assertEqual(set(reg.filter_by_capability(group="write")), {"write_stat"})

  def test_filter_driving(self):
    reg = self._reg()
    self.assertEqual(set(reg.filter_by_capability(driving=True)), {"read_on", "read_off", "pc_only_tool"})
    self.assertEqual(set(reg.filter_by_capability(driving=False)), {"write_stat"})

  def test_filter_enabled_only(self):
    reg = self._reg()
    enabled = set(reg.filter_by_capability(enabled_only=True))
    self.assertNotIn("read_off", enabled)
    self.assertIn("read_on", enabled)

  def test_filter_pc_only(self):
    reg = self._reg()
    self.assertEqual(reg.filter_by_capability(pc_only=True), ["pc_only_tool"])
    self.assertNotIn("pc_only_tool", reg.filter_by_capability(pc_only=False))

  def test_filter_predicate(self):
    reg = self._reg()
    names = reg.filter_by_capability(predicate=lambda n, c: n.startswith("read"))
    self.assertEqual(set(names), {"read_on", "read_off"})

  def test_filtered_schemas(self):
    reg = self._reg()
    schemas = reg.filtered_schemas(group="write")
    self.assertEqual(len(schemas), 1)
    self.assertEqual(schemas[0]["function"]["name"], "write_stat")


class ToolRegistryBridgeTests(unittest.TestCase):
  def test_from_parts_skips_nameless_schemas(self):
    reg = ToolRegistry.from_parts([{"type": "function", "function": {}}, "not-a-dict"])
    self.assertEqual(len(reg), 0)

  def test_from_parts_aligns_handlers_and_meta(self):
    schemas = [_spec("a"), _spec("b")]
    handlers = {"a": _echo}
    meta = {"a": {"group": "read"}, "b": {"group": "write"}}
    reg = ToolRegistry.from_parts(schemas, handlers=handlers, meta=meta)
    self.assertEqual(set(reg.names()), {"a", "b"})
    self.assertIs(reg.get("a"), _echo)
    self.assertIsNone(reg.get("b"))
    self.assertEqual(reg.get_capability("b")["group"], "write")

  def test_registry_from_agent_tools_with_injected_providers(self):
    """The bridge works with injected providers (no openpilot import)."""
    reg = registry_from_agent_tools(
      build_schemas=lambda: [_spec("alpha"), _spec("beta")],
      meta={"alpha": {"group": "read", "driving": True}},
      handlers={"alpha": _echo},
    )
    self.assertEqual(set(reg.names()), {"alpha", "beta"})
    self.assertIs(reg.get("alpha"), _echo)
    self.assertEqual(reg.filter_by_capability(group="read"), ["alpha"])

  def test_registry_from_agent_tools_real(self):
    """Bridge against the real agent_tools when its imports are available."""
    try:
      from ai.tools.agent_tools import TOOL_META, build_tool_schemas  # noqa: F401
    except Exception as exc:  # pragma: no cover - env dependent
      self.skipTest(f"agent_tools unavailable: {exc}")
    reg = registry_from_agent_tools()
    names = set(reg.names())
    schema_names = {s["function"]["name"] for s in build_tool_schemas() if isinstance(s, dict) and isinstance(s.get("function"), dict)}
    self.assertTrue(schema_names <= names, f"registry missing schemas: {schema_names - names}")
    self.assertIn("goal_create", names)
    self.assertTrue(len(reg.schemas()) > 0)
    # capability meta must flow through for tools that declare it
    if "goal_create" in TOOL_META:
      self.assertEqual(reg.get_capability("goal_create"), TOOL_META["goal_create"])

  def test_known_duplicate_schema_is_deduped(self):
    """Regression: ``list_scheduled_tasks`` is legitimately declared in both
    ``agent_tools`` and ``platform_extensions`` schemas, so
    ``build_tool_schemas()`` emits it twice. The registry must dedupe by name
    (single entry, still queryable with its schema + capability metadata)."""
    try:
      from ai.tools.agent_tools import TOOL_META, build_tool_schemas
    except Exception as exc:  # pragma: no cover - env dependent
      self.skipTest(f"agent_tools unavailable: {exc}")

    raw_names = [
      s["function"]["name"]
      for s in build_tool_schemas()
      if isinstance(s, dict) and isinstance(s.get("function"), dict)
    ]
    # The raw schema list contains the duplicate (documents the known input).
    self.assertGreaterEqual(raw_names.count("list_scheduled_tasks"), 2)

    reg = registry_from_agent_tools()
    # The registry collapses it to exactly one entry.
    self.assertEqual(reg.names().count("list_scheduled_tasks"), 1)
    self.assertIn("list_scheduled_tasks", reg)
    self.assertEqual(reg.get_schema("list_scheduled_tasks")["function"]["name"], "list_scheduled_tasks")
    # And the capability meta is preserved from TOOL_META.
    self.assertEqual(reg.get_capability("list_scheduled_tasks"), TOOL_META["list_scheduled_tasks"])


if __name__ == "__main__":
  unittest.main()
