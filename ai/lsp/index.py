"""Symbol index backed by LSP document/workspace symbol results.

Stores symbols per file and supports lookup by name, file, or kind.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# LSP SymbolKind constants (subset most commonly returned by servers).
class SymbolKind:
  FILE = 1
  MODULE = 2
  NAMESPACE = 3
  PACKAGE = 4
  CLASS = 5
  METHOD = 6
  PROPERTY = 7
  FIELD = 8
  CONSTRUCTOR = 9
  ENUM = 10
  INTERFACE = 11
  FUNCTION = 12
  VARIABLE = 13
  CONSTANT = 14
  STRING = 15
  NUMBER = 16
  BOOLEAN = 17
  ARRAY = 18
  OBJECT = 19
  KEY = 20
  NULL = 21
  ENUM_MEMBER = 22
  STRUCT = 23
  EVENT = 24
  OPERATOR = 25
  TYPE_PARAMETER = 26


_SYMBOL_KIND_NAMES: dict[int, str] = {
  SymbolKind.FILE: "file",
  SymbolKind.MODULE: "module",
  SymbolKind.NAMESPACE: "namespace",
  SymbolKind.PACKAGE: "package",
  SymbolKind.CLASS: "class",
  SymbolKind.METHOD: "method",
  SymbolKind.PROPERTY: "property",
  SymbolKind.FIELD: "field",
  SymbolKind.CONSTRUCTOR: "constructor",
  SymbolKind.ENUM: "enum",
  SymbolKind.INTERFACE: "interface",
  SymbolKind.FUNCTION: "function",
  SymbolKind.VARIABLE: "variable",
  SymbolKind.CONSTANT: "constant",
  SymbolKind.STRING: "string",
  SymbolKind.NUMBER: "number",
  SymbolKind.BOOLEAN: "boolean",
  SymbolKind.ARRAY: "array",
  SymbolKind.OBJECT: "object",
  SymbolKind.KEY: "key",
  SymbolKind.NULL: "null",
  SymbolKind.ENUM_MEMBER: "enumMember",
  SymbolKind.STRUCT: "struct",
  SymbolKind.EVENT: "event",
  SymbolKind.OPERATOR: "operator",
  SymbolKind.TYPE_PARAMETER: "typeParameter",
}


def symbol_kind_name(kind: int) -> str:
  return _SYMBOL_KIND_NAMES.get(kind, "unknown")


@dataclass
class Symbol:
  name: str
  kind: int
  uri: str
  range: dict[str, Any]
  selection_range: dict[str, Any] | None = None
  container_name: str = ""
  detail: str = ""

  def kind_name(self) -> str:
    return symbol_kind_name(self.kind)

  def to_dict(self) -> dict[str, Any]:
    return {
      "name": self.name,
      "kind": self.kind,
      "kindName": self.kind_name(),
      "uri": self.uri,
      "range": self.range,
      "selectionRange": self.selection_range,
      "containerName": self.container_name,
      "detail": self.detail,
    }


@dataclass
class SymbolIndex:
  """In-memory symbol index."""

  _by_file: dict[str, list[Symbol]] = field(default_factory=dict)
  _by_name: dict[str, list[Symbol]] = field(default_factory=dict)
  _by_kind: dict[int, list[Symbol]] = field(default_factory=dict)

  def clear(self) -> None:
    self._by_file.clear()
    self._by_name.clear()
    self._by_kind.clear()

  def clear_file(self, uri: str) -> None:
    removed = self._by_file.pop(uri, [])
    self._remove_from_index(removed)

  def _remove_from_index(self, symbols: list[Symbol]) -> None:
    for sym in symbols:
      self._by_name.setdefault(sym.name, [])
      if sym in self._by_name[sym.name]:
        self._by_name[sym.name].remove(sym)
      self._by_kind.setdefault(sym.kind, [])
      if sym in self._by_kind[sym.kind]:
        self._by_kind[sym.kind].remove(sym)

  def add(self, symbol: Symbol) -> None:
    self._by_file.setdefault(symbol.uri, []).append(symbol)
    self._by_name.setdefault(symbol.name, []).append(symbol)
    self._by_kind.setdefault(symbol.kind, []).append(symbol)

  def add_document_symbols(self, uri: str, symbols: list[dict[str, Any]]) -> int:
    """Flatten and index hierarchical document symbols."""
    count = 0
    for raw in symbols:
      count += self._add_document_symbol(uri, raw, "")
    return count

  def _add_document_symbol(
    self,
    uri: str,
    raw: dict[str, Any],
    container_name: str,
  ) -> int:
    symbol = Symbol(
      name=raw.get("name", ""),
      kind=raw.get("kind", 0),
      uri=uri,
      range=raw.get("range", {}),
      selection_range=raw.get("selectionRange"),
      container_name=container_name,
      detail=raw.get("detail", ""),
    )
    self.add(symbol)
    count = 1
    for child in raw.get("children") or []:
      count += self._add_document_symbol(uri, child, symbol.name)
    return count

  def add_workspace_symbols(self, symbols: list[dict[str, Any]]) -> int:
    """Index workspace symbol results."""
    count = 0
    for raw in symbols:
      location = raw.get("location") or {}
      symbol = Symbol(
        name=raw.get("name", ""),
        kind=raw.get("kind", 0),
        uri=location.get("uri", ""),
        range=location.get("range", {}),
        container_name=raw.get("containerName", ""),
        detail=raw.get("detail", ""),
      )
      self.add(symbol)
      count += 1
    return count

  def lookup(self, name: str) -> list[Symbol]:
    """Exact lookup by symbol name."""
    return list(self._by_name.get(name, []))

  def lookup_by_file(self, uri: str) -> list[Symbol]:
    return list(self._by_file.get(uri, []))

  def lookup_by_kind(self, kind: int) -> list[Symbol]:
    return list(self._by_kind.get(kind, []))

  def all_symbols(self) -> list[Symbol]:
    results: list[Symbol] = []
    for symbols in self._by_file.values():
      results.extend(symbols)
    return results
