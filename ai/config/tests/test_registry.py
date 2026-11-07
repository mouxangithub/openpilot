"""Tests for G12 ConfigRegistry."""
from __future__ import annotations
import unittest

from ai.config import ConfigRegistry, SchemaField


class ConfigRegistryTest(unittest.TestCase):
  def test_register_and_get(self) -> None:
    reg = ConfigRegistry()
    reg.register_schema("demo", {
      "max_speed": SchemaField("max_speed", "number", default=100, min=0, max=300),
      "enabled": SchemaField("enabled", "boolean", default=True),
    }, revision=1)
    schema = reg.get_schema("demo")
    self.assertEqual(schema["revision"], 1)
    self.assertIn("max_speed", schema["fields"])
    self.assertEqual(schema["fields"]["max_speed"]["max"], 300)

  def test_downgrade_refused(self) -> None:
    reg = ConfigRegistry()
    reg.register_schema("demo", {"a": SchemaField("a", "string")}, revision=2)
    reg.register_schema("demo", {"a": SchemaField("a", "string")}, revision=1)
    self.assertEqual(reg.get_schema("demo")["revision"], 2)

  def test_autoload_from_disk_index(self) -> None:
    reg = ConfigRegistry()
    all_schemas = reg.all()
    self.assertIn("conversation", all_schemas)
    self.assertIn("dev_diagnostics", all_schemas)
    self.assertIn("scheduler", all_schemas)
    # dev_diagnostics secret field marked secret.
    diag = all_schemas["dev_diagnostics"]["fields"]
    self.assertTrue(diag["ai_diag_api_key"]["secret"])

  def test_missing_namespace_raises(self) -> None:
    reg = ConfigRegistry()
    with self.assertRaises(KeyError):
      reg.get_schema("nope")


if __name__ == "__main__":
  unittest.main()