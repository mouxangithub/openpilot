"""Tests for ai.core.chat.commands."""

from __future__ import annotations

import pytest

from ai.core.chat.commands import (
  CommandError,
  CommandRegistry,
  ParsedCommand,
  dispatch_command,
  dispatch_command_async,
  parse_slash_command,
)
from ai.core.session.log import SessionLog


@pytest.fixture
def registry():
  return CommandRegistry()


@pytest.fixture
def log(tmp_path):
  return SessionLog("test-session", persist_path=tmp_path / "test.jsonl")


def test_parse_slash_command():
  parsed = parse_slash_command("/foo arg1 arg2")
  assert parsed.is_command is True
  assert parsed.name == "foo"
  assert parsed.args == "arg1 arg2"


def test_parse_no_command():
  parsed = parse_slash_command("hello world")
  assert parsed.is_command is False


def test_parse_empty_command():
  with pytest.raises(CommandError) as exc:
    parse_slash_command("/")
  assert exc.value.code == "EMPTY_COMMAND"


def test_register_and_dispatch(registry: CommandRegistry, log: SessionLog):
  called = {}

  def handler(args: str, ctx: dict, sess_log: SessionLog):
    called["args"] = args
    called["ctx"] = ctx
    return {"echo": args}

  registry.register("echo", handler, description="Echo args")
  result = dispatch_command(registry, "/echo hello", log=log, context={"sessionId": "s1"})
  assert result["handled"] is True
  assert result["ok"] is True
  assert called["args"] == "hello"
  events = log.events
  assert any(ev.type.value == "command/run" for ev in events)
  assert any(ev.type.value == "command/done" for ev in events)


def test_dispatch_unknown(registry: CommandRegistry, log: SessionLog):
  result = dispatch_command(registry, "/unknown", log=log)
  assert result["handled"] is True
  assert result["ok"] is False
  assert result["code"] == "UNKNOWN_COMMAND"


def test_requires_args(registry: CommandRegistry, log: SessionLog):
  registry.register("rename", lambda args, ctx, log: "ok", requires_args=True)
  result = dispatch_command(registry, "/rename", log=log)
  assert result["ok"] is False
  assert result["code"] == "MISSING_ARGS"


def test_dispatch_non_command(registry: CommandRegistry, log: SessionLog):
  result = dispatch_command(registry, "regular message", log=log)
  assert result["handled"] is False


@pytest.mark.asyncio
async def test_async_dispatch(registry: CommandRegistry, log: SessionLog):
  async def handler(args: str, ctx: dict, sess_log: SessionLog):
    return f"async-{args}"

  registry.register("async", handler)
  result = await dispatch_command_async(registry, "/async x", log=log)
  assert result["ok"] is True
  assert result["result"] == "async-x"


def test_handler_exception(registry: CommandRegistry, log: SessionLog):
  registry.register("boom", lambda args, ctx, log: (_ for _ in ()).throw(RuntimeError("fail")))
  result = dispatch_command(registry, "/boom x", log=log)
  assert result["ok"] is False
  assert result["code"] == "HANDLER_ERROR"
