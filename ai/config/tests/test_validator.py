"""Tests for G12 validate_payload."""
from __future__ import annotations
import unittest

from ai.config import validate_payload
from ai.config.registry import ConfigRegistry
from ai.core.errors import ERR_CONFIG_INVALID

SCHEMA = {
  "namespace": "demo",
  "revision": 1,
  "fields": {
    "n": {"key": "n", "type": "number", "default": 1, "min": 0, "max": 100},
    "b": {"key": "b", "type": "boolean", "default": True},
    "mode": {"key": "mode", "type": "enum", "enum": ["a", "b", "c"], "default": "a"},
    "name": {"key": "name", "type": "string", "default": ""},
  },
}


class ValidatorTest(unittest.TestCase):
  def test_valid(self) -> None:
    self.assertEqual(validate_payload(SCHEMA, {"n": 5, "b": False, "mode": "b", "name": "x"}), [])

  def test_unknown_key(self) -> None:
    errors = validate_payload(SCHEMA, {"bogus": 1})
    self.assertEqual(len(errors), 1)
    self.assertEqual(errors[0]["field"], "bogus")
    self.assertEqual(errors[0]["code"], ERR_CONFIG_INVALID)

  def test_type_mismatch(self) -> None:
    errors = validate_payload(SCHEMA, {"n": "not-a-number"})
    self.assertTrue(any(e["field"] == "n" for e in errors))

  def test_out_of_range(self) -> None:
    errors = validate_payload(SCHEMA, {"n": 999})
    self.assertTrue(any(e["field"] == "n" for e in errors))

  def test_enum(self) -> None:
    errors = validate_payload(SCHEMA, {"mode": "zzz"})
    self.assertTrue(any(e["field"] == "mode" for e in errors))

  def test_integration_with_registry_fields(self) -> None:
    reg = ConfigRegistry()
    reg.register_schema("demo", {
      "max_speed": __import__("ai.config", fromlist=["SchemaField"]).SchemaField("max_speed", "number", default=100, min=0, max=300),
    }, revision=1)
    errors = validate_payload(reg.get_schema("demo"), {"max_speed": 301})
    self.assertEqual(len(errors), 1)


if __name__ == "__main__":
  unittest.main()