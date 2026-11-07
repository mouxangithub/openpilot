"""Command registry and slash-command lifecycle.

Parses ``/command args`` user input, dispatches to registered handlers, and
writes ``command/run`` + ``command/done`` events to the session log so replay
and UI can reconstruct command execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ai.core.session.log import EventType, SessionLog


CommandHandler = Callable[[str, dict[str, Any], SessionLog], Any]
AsyncCommandHandler = Callable[[str, dict[str, Any], SessionLog], Awaitable[Any]]


class CommandError(Exception):
  """Raised when a slash command cannot be parsed or executed."""

  def __init__(self, message: str, code: str = "COMMAND_ERROR") -> None:
    super().__init__(message)
    self.message = message
    self.code = code


@dataclass
class CommandDefinition:
  """Registered slash command metadata."""

  name: str
  description: str
  handler: CommandHandler | AsyncCommandHandler
  requires_args: bool = False
  hidden: bool = False


@dataclass
class CommandRegistry:
  """In-memory registry for slash commands."""

  _commands: dict[str, CommandDefinition] = field(default_factory=dict)

  def register(
    self,
    name: str,
    handler: CommandHandler | AsyncCommandHandler,
    *,
    description: str = "",
    requires_args: bool = False,
    hidden: bool = False,
  ) -> CommandDefinition:
    """Register a command. Overwrites existing registration with a warning."""
    normalized = _normalize_name(name)
    if normalized in self._commands:
      # Intentionally allow override; log is unavailable here.
      pass
    definition = CommandDefinition(
      name=normalized,
      description=description,
      handler=handler,
      requires_args=requires_args,
      hidden=hidden,
    )
    self._commands[normalized] = definition
    return definition

  def unregister(self, name: str) -> CommandDefinition | None:
    """Remove a command from the registry."""
    return self._commands.pop(_normalize_name(name), None)

  def get(self, name: str) -> CommandDefinition | None:
    """Return a command definition by name."""
    return self._commands.get(_normalize_name(name))

  def list_commands(self, include_hidden: bool = False) -> list[dict[str, Any]]:
    """Return public command metadata."""
    out: list[dict[str, Any]] = []
    for cmd in self._commands.values():
      if cmd.hidden and not include_hidden:
        continue
      out.append({
        "name": cmd.name,
        "description": cmd.description,
        "requires_args": cmd.requires_args,
      })
    return out

  def clear(self) -> None:
    """Remove all registered commands."""
    self._commands.clear()


@dataclass
class ParsedCommand:
  """Result of parsing a ``/command args`` line."""

  raw: str
  name: str
  args: str
  is_command: bool


def _normalize_name(name: str) -> str:
  """Strip leading slash and whitespace, lowercase the command name."""
  return name.lstrip("/").strip().lower()


def parse_slash_command(text: str) -> ParsedCommand:
  """Parse a user message line into a slash command.

  Rules:
    - Leading ``/`` followed by a command name makes it a command.
    - Everything after the first whitespace is ``args``.
    - Lines without a leading ``/`` return ``is_command=False``.
  """
  stripped = text.strip()
  if not stripped.startswith("/"):
    return ParsedCommand(raw=stripped, name="", args="", is_command=False)
  body = stripped[1:].strip()
  if not body:
    raise CommandError("Empty command name.", "EMPTY_COMMAND")
  parts = body.split(None, 1)
  name = parts[0].lower()
  args = parts[1] if len(parts) > 1 else ""
  if not name:
    raise CommandError("Empty command name.", "EMPTY_COMMAND")
  return ParsedCommand(raw=stripped, name=name, args=args, is_command=True)


def _write_command_event(
  log: SessionLog | None,
  phase: str,
  name: str,
  args: str,
  result: Any = None,
  error: CommandError | None = None,
) -> dict[str, Any]:
  """Write a command lifecycle event and return the payload."""
  payload: dict[str, Any] = {
    "command": name,
    "args": args,
    "phase": phase,
  }
  if result is not None:
    payload["result"] = result
  if error is not None:
    payload["error"] = error.message
    payload["error_code"] = error.code
  if log is not None:
    event_type = EventType.COMMAND_RUN if phase == "run" else EventType.COMMAND_DONE
    log.append(event_type, payload)
  return payload


def dispatch_command(
  registry: CommandRegistry,
  text: str,
  log: SessionLog | None = None,
  context: dict[str, Any] | None = None,
) -> dict[str, Any]:
  """Parse and execute a slash command synchronously.

  Writes ``command/run`` before invocation and ``command/done`` after.
  """
  parsed = parse_slash_command(text)
  if not parsed.is_command:
    return {"handled": False, "parsed": parsed}

  definition = registry.get(parsed.name)
  if definition is None:
    error = CommandError(f"Unknown command: /{parsed.name}", "UNKNOWN_COMMAND")
    _write_command_event(log, "run", parsed.name, parsed.args)
    _write_command_event(log, "done", parsed.name, parsed.args, error=error)
    return {"handled": True, "ok": False, "error": error.message, "code": error.code}

  if definition.requires_args and not parsed.args.strip():
    error = CommandError(f"Command /{parsed.name} requires arguments.", "MISSING_ARGS")
    _write_command_event(log, "run", parsed.name, parsed.args)
    _write_command_event(log, "done", parsed.name, parsed.args, error=error)
    return {"handled": True, "ok": False, "error": error.message, "code": error.code}

  _write_command_event(log, "run", parsed.name, parsed.args)

  try:
    result = definition.handler(parsed.args, context or {}, log)
    payload = _write_command_event(log, "done", parsed.name, parsed.args, result=_coerce_result(result))
    return {"handled": True, "ok": True, "command": parsed.name, "result": payload.get("result")}
  except CommandError as exc:
    _write_command_event(log, "done", parsed.name, parsed.args, error=exc)
    return {"handled": True, "ok": False, "error": exc.message, "code": exc.code}
  except Exception as exc:  # noqa: BLE001
    error = CommandError(str(exc), "HANDLER_ERROR")
    _write_command_event(log, "done", parsed.name, parsed.args, error=error)
    return {"handled": True, "ok": False, "error": error.message, "code": error.code}


async def dispatch_command_async(
  registry: CommandRegistry,
  text: str,
  log: SessionLog | None = None,
  context: dict[str, Any] | None = None,
) -> dict[str, Any]:
  """Parse and execute a slash command, awaiting async handlers.

  Writes ``command/run`` before invocation and ``command/done`` after.
  """
  parsed = parse_slash_command(text)
  if not parsed.is_command:
    return {"handled": False, "parsed": parsed}

  definition = registry.get(parsed.name)
  if definition is None:
    error = CommandError(f"Unknown command: /{parsed.name}", "UNKNOWN_COMMAND")
    _write_command_event(log, "run", parsed.name, parsed.args)
    _write_command_event(log, "done", parsed.name, parsed.args, error=error)
    return {"handled": True, "ok": False, "error": error.message, "code": error.code}

  if definition.requires_args and not parsed.args.strip():
    error = CommandError(f"Command /{parsed.name} requires arguments.", "MISSING_ARGS")
    _write_command_event(log, "run", parsed.name, parsed.args)
    _write_command_event(log, "done", parsed.name, parsed.args, error=error)
    return {"handled": True, "ok": False, "error": error.message, "code": error.code}

  _write_command_event(log, "run", parsed.name, parsed.args)

  try:
    if hasattr(definition.handler, "__await__") or _is_coroutine(definition.handler):
      result = await definition.handler(parsed.args, context or {}, log)
    else:
      result = definition.handler(parsed.args, context or {}, log)
    payload = _write_command_event(log, "done", parsed.name, parsed.args, result=_coerce_result(result))
    return {"handled": True, "ok": True, "command": parsed.name, "result": payload.get("result")}
  except CommandError as exc:
    _write_command_event(log, "done", parsed.name, parsed.args, error=exc)
    return {"handled": True, "ok": False, "error": exc.message, "code": exc.code}
  except Exception as exc:  # noqa: BLE001
    error = CommandError(str(exc), "HANDLER_ERROR")
    _write_command_event(log, "done", parsed.name, parsed.args, error=error)
    return {"handled": True, "ok": False, "error": error.message, "code": error.code}


def _is_coroutine(fn: CommandHandler | AsyncCommandHandler) -> bool:
  import asyncio
  return asyncio.iscoroutinefunction(fn)


def _coerce_result(result: Any) -> Any:
  """Best-effort serialize command handler results."""
  if isinstance(result, (str, int, float, bool, type(None), list, dict)):
    return result
  return str(result)


# Global registry for process-wide command registration.
_global_registry: CommandRegistry | None = None


def get_global_registry() -> CommandRegistry:
  """Return the process-wide command registry, creating it if needed."""
  global _global_registry
  if _global_registry is None:
    _global_registry = CommandRegistry()
  return _global_registry


def register_command(
  name: str,
  handler: CommandHandler | AsyncCommandHandler,
  *,
  description: str = "",
  requires_args: bool = False,
  hidden: bool = False,
) -> CommandDefinition:
  """Register a command on the global registry."""
  return get_global_registry().register(
    name,
    handler,
    description=description,
    requires_args=requires_args,
    hidden=hidden,
  )
