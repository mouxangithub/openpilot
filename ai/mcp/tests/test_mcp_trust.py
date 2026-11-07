"""Tests for ai.mcp.trust."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai.core.session.log import SessionLog
from ai.mcp.trust import (
  MCPTrustError,
  MCPTrustStore,
  ask_trust_before_tool,
  decide_trust_for_tool,
  fingerprint_server_config,
)


@pytest.fixture
def store(tmp_path: Path):
  return MCPTrustStore(tmp_path)


@pytest.fixture
def log(tmp_path: Path):
  return SessionLog("mcp-test", persist_path=tmp_path / "mcp.jsonl")


def test_fingerprint_stable():
  fp1 = fingerprint_server_config("srv1", command="node", args=["a.js"], env={"K": "V"})
  fp2 = fingerprint_server_config("srv1", command="node", args=["a.js"], env={"K": "V"})
  assert fp1.digest == fp2.digest


def test_fingerprint_env_order_independent():
  fp1 = fingerprint_server_config("srv1", command="node", args=["a.js"], env={"A": "1", "B": "2"})
  fp2 = fingerprint_server_config("srv1", command="node", args=["a.js"], env={"B": "2", "A": "1"})
  assert fp1.digest == fp2.digest


def test_fingerprint_args_order_matters():
  fp1 = fingerprint_server_config("srv1", command="node", args=["a", "b"])
  fp2 = fingerprint_server_config("srv1", command="node", args=["b", "a"])
  assert fp1.digest != fp2.digest


def test_trust_store_allow(store: MCPTrustStore):
  fp = fingerprint_server_config("srv1", command="node")
  assert store.is_trusted(fp) is False
  store.decide(fp, "allow")
  assert store.is_trusted(fp) is True


def test_trust_store_digest_mismatch(store: MCPTrustStore):
  fp1 = fingerprint_server_config("srv1", command="node", args=["a.js"])
  store.decide(fp1, "allow")
  fp2 = fingerprint_server_config("srv1", command="node", args=["b.js"])
  assert store.is_trusted(fp2) is False


def test_trust_store_invalid_decision(store: MCPTrustStore):
  fp = fingerprint_server_config("srv1")
  with pytest.raises(MCPTrustError) as exc:
    store.decide(fp, "maybe")
  assert exc.value.code == "INVALID_DECISION"


def test_ask_and_decide_events(log: SessionLog):
  fp = fingerprint_server_config("srv1", command="node")
  request = ask_trust_before_tool(log, "req-1", "srv1", fp, "tool_a", {"x": 1})
  assert request.server_id == "srv1"
  decide_trust_for_tool(log, request, "allow", reason="user confirmed")
  events = log.events
  assert any(ev.type.value == "mcp/trust_asked" for ev in events)
  assert any(ev.type.value == "mcp/trust_decided" for ev in events)


def test_remove_decision(store: MCPTrustStore):
  fp = fingerprint_server_config("srv1")
  store.decide(fp, "allow")
  assert store.remove("srv1") is True
  assert store.is_trusted(fp) is False
