"""Tests for P1/P2 config schema registration and validation."""

from __future__ import annotations

import pytest

from ai.config.registry import ConfigRegistry
from ai.config.validator import validate_payload


@pytest.fixture
def registry() -> ConfigRegistry:
  reg = ConfigRegistry()
  reg.load_defaults()
  return reg


def test_p1p2_namespaces_loaded(registry: ConfigRegistry):
  namespaces = set(registry.namespaces())
  expected = {
    "conversation", "sandbox", "spill", "mcp", "bundle",
    "workflow", "lsp", "subagent", "evolution", "vehicle_safety",
    "data_backup", "scheduler", "dev_diagnostics",
  }
  assert expected <= namespaces


def test_conversation_revision_bumped(registry: ConfigRegistry):
  schema = registry.get_schema("conversation")
  assert schema["revision"] == 2
  fields = schema["fields"]
  assert "ai_use_agent_loop" in fields
  assert "ai_tool_timeout" in fields
  assert "ai_stream_timeout" in fields
  assert fields["ai_use_agent_loop"]["default"] is True


def test_sandbox_schema(registry: ConfigRegistry):
  schema = registry.get_schema("sandbox")
  fields = schema["fields"]
  assert fields["ai_sandbox_shell"]["default"] is True
  assert fields["ai_sandbox_mode"]["enum"] == ["read-only", "confined", "isolated", "disabled"]


def test_spill_schema(registry: ConfigRegistry):
  schema = registry.get_schema("spill")
  fields = schema["fields"]
  assert fields["ai_externalize_results"]["default"] is True
  assert fields["ai_externalize_threshold"]["min"] == 1024
  assert fields["ai_spill_backend"]["enum"] == ["local", "remote"]


def test_mcp_schema(registry: ConfigRegistry):
  schema = registry.get_schema("mcp")
  fields = schema["fields"]
  assert fields["ai_mcp_default_trust"]["enum"] == ["ask", "allow", "deny"]


def test_validator_object_list_enum_min_max(registry: ConfigRegistry):
  schema = registry.get_schema("spill")
  errors = validate_payload(schema, {"ai_externalize_threshold": 512})
  assert any(e["field"] == "ai_externalize_threshold" for e in errors)

  errors = validate_payload(schema, {"ai_spill_backend": "unknown"})
  assert any(e["field"] == "ai_spill_backend" for e in errors)

  errors = validate_payload(schema, {"ai_externalize_threshold": 8192, "ai_spill_backend": "local"})
  assert not errors


def test_validator_secret_restart_not_exposed_in_errors(registry: ConfigRegistry):
  schema = registry.get_schema("dev_diagnostics")
  errors = validate_payload(schema, {"ai_diag_api_key": "x"})
  assert not errors
