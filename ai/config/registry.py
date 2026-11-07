""":class:`ConfigRegistry` — register, find and merge field schemas by namespace."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from ai.core.errors import ERR_INVALID_INPUT, ERR_NOT_FOUND


@dataclass(frozen=True)
class SchemaField:
  key: str
  type: str  # string|number|boolean|enum|secret|list|object
  default: Any = None
  min: float | None = None
  max: float | None = None
  enum: list[Any] | None = None
  secret: bool = False
  restart: bool = False
  label: str = ""
  description: str = ""


def _field_from_dict(field_id: str, d: dict[str, Any]) -> SchemaField:
  return SchemaField(
    key=str(field_id),
    type=str(d.get("type", "string")),
    default=d.get("default"),
    min=d.get("min"),
    max=d.get("max"),
    enum=list(d["enum"]) if d.get("enum") is not None else None,
    secret=bool(d.get("secret", False)),
    restart=bool(d.get("restart", False)),
    label=str(d.get("label", "")),
    description=str(d.get("description", "")),
  )


def _locate_schema_dir() -> str:
  here = os.path.dirname(__file__)
  return os.path.join(here, "schemas")


class ConfigRegistry:
  """Holds an ordered mapping of namespace -> {revision, fields}.

  ``fields`` is ``{key: SchemaField}``. ``register_schema`` refuses a lower-equal
  revision than the recorded one (stale write protection).
  """

  def __init__(self, schema_dir: str | None = None) -> None:
    self._schemas: dict[str, dict[str, Any]] = {}
    self._schema_dir = schema_dir or _locate_schema_dir()

  def register_schema(self, namespace: str, fields: dict[str, SchemaField], revision: int) -> None:
    if revision <= 0:
      raise ValueError("revision must be a positive integer")
    current = self._schemas.get(namespace)
    if current is not None and revision < current["revision"]:
      return  # refuse to downgrade
    self._schemas[namespace] = {"revision": revision, "fields": dict(fields)}

  def _autoload_index(self) -> None:
    if self._schemas:
      return
    try:
      index_path = os.path.join(self._schema_dir, "index.json")
      if not os.path.isfile(index_path):
        return
      with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)
      for namespace, entry in (index.get("namespaces") or {}).items():
        rev = int(entry.get("revision", 1))
        schema_file = entry.get("file")
        path = schema_file if schema_file else f"{namespace}.json"
        if not path.endswith(".json"):
          path += ".json"
        full = os.path.join(self._schema_dir, path)
        if not os.path.isfile(full):
          self.register_schema(namespace, {}, rev)
          continue
        with open(full, "r", encoding="utf-8") as f2:
          payload = json.load(f2)
        fields = {k: _field_from_dict(k, v) for k, v in (payload.get("fields") or {}).items()}
        self.register_schema(namespace, fields, rev)
    except Exception:
      return

  def get_schema(self, namespace: str) -> dict[str, Any]:
    self._autoload_index()
    entry = self._schemas.get(namespace)
    if entry is None:
      raise KeyError(ERR_NOT_FOUND)
    return {
      "namespace": namespace,
      "revision": entry["revision"],
      "fields": {
        k: {
          "key": f.key, "type": f.type, "default": f.default,
          "min": f.min, "max": f.max, "enum": f.enum, "secret": f.secret,
          "restart": f.restart, "label": f.label, "description": f.description,
        }
        for k, f in entry["fields"].items()
      },
    }

  def all(self) -> dict[str, Any]:
    self._autoload_index()
    return {ns: self.get_schema(ns) for ns in self._schemas}

  def namespaces(self) -> list[str]:
    self._autoload_index()
    return list(self._schemas.keys())

  def load_defaults(self) -> None:
    """Load all schemas from disk into the registry (used by tests/handlers)."""
    self._autoload_index()
    for ns in list(self._schemas.keys()):
      self._schemas[ns] = self._schemas[ns]