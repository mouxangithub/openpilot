"""Unified tool registry (M1 / A-P0.1, landing point ``tool_registry.py``).

This module hosts the ``ToolRegistry`` class — the single registration
contract that extension / platform / sp / harness / skill / mcp tool sets plug
into. It is intentionally **pure standard library** (no ``openpilot`` import)
so it can be imported from any layer without pulling heavy transitive
dependencies or creating import cycles.

Design notes
------------
``ai/tools/registry.py`` is kept as a *compatibility facade* that re-exports a
handful of symbols from ``ai.tools.agent_tools``; existing callers import it as
``from ai.tools.registry import build_tool_schemas``. The real registry class
therefore lives here, under the more accurate ``tool_registry`` name.

A tool module is expected to expose::

    def register_tools(registry: ToolRegistry, *, params=None, ...) -> None:
        registry.register(name, handler, spec, capability=meta)

and ``agent_tools`` orchestrates them into one registry, exporting
``handlers()`` / ``schemas()`` / ``to_handlers_dict()`` for the rest of the
system (Agent / ToolPipeline / HTTP / Web UI).

The bridge helper :func:`registry_from_agent_tools` lazily imports
``ai.tools.agent_tools`` (which pulls openpilot) so importing this module stays
dependency-free; callers that run in a lean environment can pass their own
schema/meta/handler providers to :meth:`ToolRegistry.from_parts` instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

Handler = Callable[[dict[str, Any]], Any]


@dataclass
class ToolEntry:
  """A single registered tool: handler + schema + capability metadata."""

  name: str
  handler: Handler | None
  spec: dict[str, Any]
  capability: dict[str, Any] = field(default_factory=dict)

  def to_dict(self) -> dict[str, Any]:
    return {
      "name": self.name,
      "handler": self.handler,
      "spec": self.spec,
      "capability": dict(self.capability),
    }


class ToolRegistry:
  """Thread-agnostic registry of tool handlers, schemas and capability meta.

  The registry keeps handler, schema and UI/behaviour metadata co-located so
  there is a single source of truth per tool. It supports:

  * ``register`` — add one tool (handler may be ``None`` for schema-only
    entries, e.g. tools discovered remotely before a handler is bound).
  * ``update`` — merge another registry or a legacy ``{name: handler}`` dict.
  * ``handlers`` / ``schemas`` / ``all`` / ``to_handlers_dict`` — views.
  * ``filter_by_capability`` — select tools by group / driving / enabled /
    custom predicate.
  * ``from_parts`` / :func:`registry_from_agent_tools` — bridge to the
    existing ``agent_tools`` schema + meta providers.
  """

  def __init__(self) -> None:
    self._entries: dict[str, ToolEntry] = {}

  # -- registration --------------------------------------------------------

  def register(
    self,
    name: str,
    handler: Handler | None,
    spec: dict[str, Any],
    capability: dict[str, Any] | None = None,
  ) -> None:
    """Register a single tool.

    Args:
      name: Fully-qualified tool name (the schema ``function.name``).
      handler: Callable accepting an ``args`` dict, or ``None`` for a
        schema-only entry.
      spec: OpenAI-style tool definition
        (``{"type": "function", "function": {...}}``). When ``spec`` lacks a
        ``function.name`` it is filled in from ``name``.
      capability: UI/behaviour metadata previously held in ``TOOL_META``
        (label / group / default_enabled / driving / pc_only).

    Raises:
      ValueError: If ``name`` is empty, or already registered with a different
        handler.
    """
    if not name:
      raise ValueError("tool name is required")
    resolved_spec = _normalize_spec(name, spec)
    existing = self._entries.get(name)
    if existing is not None and existing.handler is not None and handler is not None and existing.handler is not handler:
      raise ValueError(f"tool {name!r} already registered with a different handler")
    self._entries[name] = ToolEntry(
      name=name,
      handler=handler,
      spec=resolved_spec,
      capability=dict(capability or {}),
    )

  def register_many(
    self,
    items: Iterable[tuple[str, Handler | None, dict[str, Any], dict[str, Any] | None]],
  ) -> None:
    """Register several ``(name, handler, spec, capability)`` tuples at once."""
    for name, handler, spec, capability in items:
      self.register(name, handler, spec, capability)

  def update(self, other: "ToolRegistry | Mapping[str, Handler]") -> None:
    """Merge ``other`` into this registry (last write wins).

    ``other`` may be another :class:`ToolRegistry` (handler + schema +
    capability are all merged) or a legacy ``{name: handler}`` mapping (handlers
    are registered with an empty schema/capability). Unlike :meth:`register`,
    ``update`` overwrites existing entries silently to match the legacy
    ``handlers.update(...)`` merge semantics used by ``agent_tools``.
    """
    if isinstance(other, ToolRegistry):
      for name, entry in other._entries.items():
        self._entries[name] = ToolEntry(
          name=name,
          handler=entry.handler,
          spec=entry.spec,
          capability=dict(entry.capability),
        )
      return
    for name, handler in other.items():
      self._entries[name] = ToolEntry(
        name=name,
        handler=handler,
        spec=_normalize_spec(name, {}),
        capability={},
      )

  def unregister(self, name: str) -> bool:
    """Remove a tool; returns ``True`` if it existed."""
    return self._entries.pop(name, None) is not None

  # -- lookup --------------------------------------------------------------

  def get(self, name: str) -> Handler | None:
    """Return the handler for ``name`` (``None`` if missing or unbound)."""
    entry = self._entries.get(name)
    return entry.handler if entry is not None else None

  def get_handler(self, name: str) -> Handler | None:
    """Alias for :meth:`get` (design-doc naming)."""
    return self.get(name)

  def get_schema(self, name: str) -> dict[str, Any] | None:
    """Return the OpenAI-style schema for ``name`` (``None`` if missing)."""
    entry = self._entries.get(name)
    return entry.spec if entry is not None else None

  def get_capability(self, name: str) -> dict[str, Any]:
    """Return capability metadata for ``name`` (empty dict if missing)."""
    entry = self._entries.get(name)
    return dict(entry.capability) if entry is not None else {}

  def entry(self, name: str) -> ToolEntry | None:
    """Return the full :class:`ToolEntry` for ``name`` (``None`` if missing)."""
    return self._entries.get(name)

  # -- enumeration ---------------------------------------------------------

  def names(self) -> list[str]:
    """Return all registered tool names in registration order."""
    return list(self._entries.keys())

  def handlers(self) -> dict[str, Handler]:
    """Return ``{name: handler}`` for every tool with a bound handler."""
    return {name: e.handler for name, e in self._entries.items() if e.handler is not None}

  def schemas(self) -> list[dict[str, Any]]:
    """Return OpenAI-style schemas for all registered tools."""
    return [e.spec for e in self._entries.values()]

  def all(self) -> dict[str, dict[str, Any]]:
    """Return ``{name: {"handler", "spec", "capability"}}`` metadata."""
    return {name: e.to_dict() for name, e in self._entries.items()}

  def to_handlers_dict(self) -> dict[str, Handler]:
    """Return the legacy ``{name: handler}`` dict (alias for :meth:`handlers`)."""
    return self.handlers()

  def list_tools(self) -> list[dict[str, Any]]:
    """Return schema list (design-doc naming alias for :meth:`schemas`)."""
    return self.schemas()

  # -- capability filtering ------------------------------------------------

  def filter_by_capability(
    self,
    *,
    group: str | None = None,
    driving: bool | None = None,
    enabled_only: bool = False,
    pc_only: bool | None = None,
    predicate: Callable[[str, dict[str, Any]], bool] | None = None,
  ) -> list[str]:
    """Return tool names matching the requested capability constraints.

    Args:
      group: Match ``capability["group"]`` exactly when provided.
      driving: Match ``capability["driving"]`` exactly when provided.
      enabled_only: Drop tools whose ``capability["default_enabled"]`` is
        explicitly ``False``.
      pc_only: When ``False`` drop tools marked ``px_only``; when ``True`` keep
        only tools marked ``pc_only``.
      predicate: Optional extra filter ``(name, capability) -> bool``.
    """
    out: list[str] = []
    for name, entry in self._entries.items():
      cap = entry.capability
      if group is not None and cap.get("group") != group:
        continue
      if driving is not None and bool(cap.get("driving")) != driving:
        continue
      if enabled_only and cap.get("default_enabled") is False:
        continue
      if pc_only is True and not cap.get("pc_only"):
        continue
      if pc_only is False and cap.get("pc_only"):
        continue
      if predicate is not None and not predicate(name, cap):
        continue
      out.append(name)
    return out

  def filtered_schemas(self, **kwargs: Any) -> list[dict[str, Any]]:
    """Return schemas for tools matching :meth:`filter_by_capability`."""
    names = set(self.filter_by_capability(**kwargs))
    return [e.spec for name, e in self._entries.items() if name in names]

  # -- bridges -------------------------------------------------------------

  @classmethod
  def from_parts(
    cls,
    schemas: Iterable[dict[str, Any]],
    *,
    handlers: Mapping[str, Handler] | None = None,
    meta: Mapping[str, dict[str, Any]] | None = None,
  ) -> "ToolRegistry":
    """Build a registry from schema / handler / meta collections.

    This is the dependency-free bridge: callers supply the pieces (typically
    read from ``agent_tools``) and get a unified registry back. Schemas whose
    ``function.name`` is absent are skipped.
    """
    registry = cls()
    handler_map = dict(handlers or {})
    meta_map = dict(meta or {})
    for spec in schemas:
      name = _spec_name(spec)
      if not name:
        continue
      registry.register(
        name,
        handler_map.get(name),
        spec,
        capability=meta_map.get(name),
      )
    return registry

  def __contains__(self, name: str) -> bool:
    return name in self._entries

  def __len__(self) -> int:
    return len(self._entries)

  def __iter__(self):
    return iter(self._entries)

  def __repr__(self) -> str:  # pragma: no cover - debug helper
    return f"ToolRegistry({len(self._entries)} tools)"


def _spec_name(spec: Any) -> str:
  """Extract ``function.name`` from an OpenAI-style tool spec."""
  if not isinstance(spec, dict):
    return ""
  fn = spec.get("function")
  if isinstance(fn, dict):
    return str(fn.get("name") or "")
  return ""


def _normalize_spec(name: str, spec: dict[str, Any]) -> dict[str, Any]:
  """Ensure ``spec`` has a ``function.name`` equal to ``name``."""
  out: dict[str, Any] = dict(spec) if isinstance(spec, dict) else {}
  fn = out.get("function")
  if not isinstance(fn, dict):
    fn = {}
  if not fn.get("name"):
    fn["name"] = name
  if "parameters" not in fn:
    fn["parameters"] = {"type": "object", "properties": {}, "required": []}
  out["type"] = out.get("type", "function")
  out["function"] = fn
  return out


def registry_from_agent_tools(
  *,
  params: Any = None,
  get_state_reader: Any = None,
  build_schemas: Callable[[], list[dict[str, Any]]] | None = None,
  meta: Mapping[str, dict[str, Any]] | None = None,
  handlers: Mapping[str, Handler] | None = None,
) -> ToolRegistry:
  """Bridge the legacy ``agent_tools`` providers into a :class:`ToolRegistry`.

  By default it lazily imports ``ai.tools.agent_tools`` to read
  ``build_tool_schemas()``, ``TOOL_META`` and (when ``get_state_reader`` is
  given) ``make_handlers()``. All three can be injected instead
  (``build_schemas`` / ``meta`` / ``handlers``) so the bridge is usable in
  environments where the openpilot transitive dependencies are unavailable.

  Returns:
    A populated :class:`ToolRegistry`.
  """
  need_import = build_schemas is None or meta is None or (get_state_reader is not None and handlers is None)
  if need_import:
    from ai.tools.agent_tools import TOOL_META, build_tool_schemas, make_handlers  # lazy import

    if build_schemas is None:
      build_schemas = build_tool_schemas
    if meta is None:
      meta = TOOL_META
    if handlers is None and get_state_reader is not None:
      handlers = make_handlers(get_state_reader=get_state_reader, params=params)

  if build_schemas is None:  # pragma: no cover - defensive
    raise RuntimeError("registry_from_agent_tools: no schema provider available")
  schemas = list(build_schemas())
  return ToolRegistry.from_parts(
    schemas,
    handlers=handlers,
    meta=meta,
  )
