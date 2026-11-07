"""Register ACP providers and locales from loaded packages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ai.acp.protocol import AcpLocale, AcpPackage, AcpProvider


@dataclass
class AcpRegistry:
  """In-memory registry of ACP packages, providers, and locales."""

  packages: dict[str, AcpPackage] = field(default_factory=dict)
  providers: dict[str, AcpProvider] = field(default_factory=dict)
  locales: dict[str, dict[str, AcpLocale]] = field(default_factory=dict)

  def register(self, package: AcpPackage) -> None:
    """Register one package and index its providers and locales."""
    self.packages[package.id] = package
    for provider in package.providers:
      self.providers[provider.id] = provider
    if package.id not in self.locales:
      self.locales[package.id] = {}
    for language, locale in package.locales.items():
      self.locales[package.id][language] = locale

  def unregister(self, package_id: str) -> bool:
    """Remove a package and its indexed providers/locales."""
    package = self.packages.pop(package_id, None)
    if package is None:
      return False
    for provider in package.providers:
      self.providers.pop(provider.id, None)
    self.locales.pop(package_id, None)
    return True

  def get_package(self, package_id: str) -> AcpPackage | None:
    return self.packages.get(package_id)

  def get_provider(self, provider_id: str) -> AcpProvider | None:
    return self.providers.get(provider_id)

  def get_locale(self, package_id: str, language: str) -> AcpLocale | None:
    return self.locales.get(package_id, {}).get(language)

  def list_packages(self) -> list[AcpPackage]:
    return list(self.packages.values())

  def list_providers(self) -> list[AcpProvider]:
    return list(self.providers.values())

  def list_locales(self, package_id: str) -> list[AcpLocale]:
    return list(self.locales.get(package_id, {}).values())

  def merge_translations(self, language: str) -> dict[str, str]:
    """Merge translation tables for one language across all packages."""
    merged: dict[str, str] = {}
    for package_id in sorted(self.locales):
      locale = self.locales[package_id].get(language)
      if locale is not None:
        merged.update(locale.translations)
    return merged

  def to_summary(self) -> dict[str, Any]:
    return {
      "packages": [p.metadata.to_dict() for p in self.list_packages()],
      "providers": [p.to_dict() for p in self.list_providers()],
      "languages": sorted({locale.language for locales in self.locales.values() for locale in locales.values()}),
    }
