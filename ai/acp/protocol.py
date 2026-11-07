"""ACP package metadata, locale, and provider schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AcpProviderKind(StrEnum):
  """Supported ACP provider kinds."""

  MCP = "mcp"
  TOOL = "tool"


@dataclass
class AcpPackageMetadata:
  """Identity and descriptive metadata for an ACP package."""

  id: str
  name: str
  version: str
  description: str = ""
  author: str = ""
  license: str = ""
  homepage: str = ""

  def to_dict(self) -> dict[str, Any]:
    return {
      "id": self.id,
      "name": self.name,
      "version": self.version,
      "description": self.description,
      "author": self.author,
      "license": self.license,
      "homepage": self.homepage,
    }

  @staticmethod
  def from_dict(data: dict[str, Any]) -> AcpPackageMetadata:
    return AcpPackageMetadata(
      id=str(data.get("id", "")),
      name=str(data.get("name", "")),
      version=str(data.get("version", "")),
      description=str(data.get("description", "")),
      author=str(data.get("author", "")),
      license=str(data.get("license", "")),
      homepage=str(data.get("homepage", "")),
    )


@dataclass
class AcpLocale:
  """One language translation table for an ACP package."""

  language: str
  translations: dict[str, str] = field(default_factory=dict)

  def to_dict(self) -> dict[str, Any]:
    return {
      "language": self.language,
      "translations": self.translations,
    }

  @staticmethod
  def from_dict(data: dict[str, Any]) -> AcpLocale:
    return AcpLocale(
      language=str(data.get("language", "")),
      translations={str(k): str(v) for k, v in (data.get("translations") or {}).items()},
    )


@dataclass
class AcpProvider:
  """Base declaration of a capability provider inside an ACP package."""

  id: str
  name: str
  kind: AcpProviderKind
  description: str = ""
  config: dict[str, Any] = field(default_factory=dict)

  def to_dict(self) -> dict[str, Any]:
    return {
      "id": self.id,
      "name": self.name,
      "kind": self.kind.value,
      "description": self.description,
      "config": self.config,
    }

  @staticmethod
  def from_dict(data: dict[str, Any]) -> AcpProvider:
    kind = AcpProviderKind(str(data.get("kind", AcpProviderKind.TOOL.value)))
    return AcpProvider(
      id=str(data.get("id", "")),
      name=str(data.get("name", "")),
      kind=kind,
      description=str(data.get("description", "")),
      config=dict(data.get("config") or {}),
    )


@dataclass
class AcpToolProvider(AcpProvider):
  """A provider that exposes one or more tool definitions."""

  kind: AcpProviderKind = field(default=AcpProviderKind.TOOL)
  tools: list[dict[str, Any]] = field(default_factory=list)

  def to_dict(self) -> dict[str, Any]:
    base = super().to_dict()
    base["tools"] = self.tools
    return base

  @staticmethod
  def from_dict(data: dict[str, Any]) -> AcpToolProvider:
    base = AcpProvider.from_dict(data)
    return AcpToolProvider(
      id=base.id,
      name=base.name,
      kind=AcpProviderKind.TOOL,
      description=base.description,
      config=base.config,
      tools=[dict(t) for t in (data.get("tools") or [])],
    )


@dataclass
class AcpMcpProvider(AcpProvider):
  """A provider that declares an MCP server configuration."""

  kind: AcpProviderKind = field(default=AcpProviderKind.MCP)
  command: str = ""
  args: list[str] = field(default_factory=list)
  env: dict[str, str] = field(default_factory=dict)
  url: str = ""

  def to_dict(self) -> dict[str, Any]:
    base = super().to_dict()
    base.update({
      "command": self.command,
      "args": self.args,
      "env": self.env,
      "url": self.url,
    })
    return base

  @staticmethod
  def from_dict(data: dict[str, Any]) -> AcpMcpProvider:
    base = AcpProvider.from_dict(data)
    return AcpMcpProvider(
      id=base.id,
      name=base.name,
      kind=AcpProviderKind.MCP,
      description=base.description,
      config=base.config,
      command=str(data.get("command", "")),
      args=[str(a) for a in (data.get("args") or [])],
      env={str(k): str(v) for k, v in (data.get("env") or {}).items()},
      url=str(data.get("url", "")),
    )


@dataclass
class AcpPackage:
  """A complete ACP plugin package: metadata plus locales and providers."""

  metadata: AcpPackageMetadata
  locales: dict[str, AcpLocale] = field(default_factory=dict)
  providers: list[AcpProvider] = field(default_factory=list)
  extra: dict[str, Any] = field(default_factory=dict)

  @property
  def id(self) -> str:
    return self.metadata.id

  @property
  def name(self) -> str:
    return self.metadata.name

  @property
  def version(self) -> str:
    return self.metadata.version

  def to_dict(self) -> dict[str, Any]:
    return {
      "metadata": self.metadata.to_dict(),
      "locales": {k: v.to_dict() for k, v in self.locales.items()},
      "providers": [p.to_dict() for p in self.providers],
      "extra": self.extra,
    }

  @staticmethod
  def from_dict(data: dict[str, Any]) -> AcpPackage:
    metadata = AcpPackageMetadata.from_dict(data.get("metadata") or {})

    locales: dict[str, AcpLocale] = {}
    for key, value in (data.get("locales") or {}).items():
      if isinstance(value, dict):
        locales[str(key)] = AcpLocale.from_dict(value)

    providers: list[AcpProvider] = []
    for item in data.get("providers") or []:
      if not isinstance(item, dict):
        continue
      kind = AcpProviderKind(str(item.get("kind", AcpProviderKind.TOOL.value)))
      if kind == AcpProviderKind.MCP:
        providers.append(AcpMcpProvider.from_dict(item))
      else:
        providers.append(AcpToolProvider.from_dict(item))

    return AcpPackage(
      metadata=metadata,
      locales=locales,
      providers=providers,
      extra=dict(data.get("extra") or {}),
    )
