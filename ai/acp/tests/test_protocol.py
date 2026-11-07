"""Unit tests for ACP protocol dataclasses and registry."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ai.acp.loader import AcpLoader, AcpLoadError
from ai.acp.protocol import (
  AcpLocale,
  AcpMcpProvider,
  AcpPackage,
  AcpPackageMetadata,
  AcpToolProvider,
)
from ai.acp.registry import AcpRegistry


class TestAcpPackageMetadata(unittest.TestCase):
  def test_round_trip(self) -> None:
    meta = AcpPackageMetadata(
      id="test.pkg",
      name="Test Package",
      version="1.2.3",
      description="A test package",
      author="tester",
      license="MIT",
      homepage="https://example.com",
    )
    data = meta.to_dict()
    restored = AcpPackageMetadata.from_dict(data)
    self.assertEqual(restored, meta)

  def test_defaults(self) -> None:
    meta = AcpPackageMetadata.from_dict({"id": "x", "name": "X"})
    self.assertEqual(meta.version, "")
    self.assertEqual(meta.description, "")


class TestAcpLocale(unittest.TestCase):
  def test_round_trip(self) -> None:
    locale = AcpLocale(language="zh", translations={"hello": "你好"})
    restored = AcpLocale.from_dict(locale.to_dict())
    self.assertEqual(restored, locale)


class TestAcpProviders(unittest.TestCase):
  def test_tool_provider(self) -> None:
    provider = AcpToolProvider(
      id="tool-1",
      name="Tool One",
      description="Does one thing",
      tools=[{"name": "foo", "description": "bar"}],
    )
    data = provider.to_dict()
    self.assertEqual(data["kind"], "tool")
    restored = AcpToolProvider.from_dict(data)
    self.assertEqual(restored, provider)

  def test_mcp_provider(self) -> None:
    provider = AcpMcpProvider(
      id="mcp-1",
      name="MCP One",
      command="/usr/bin/node",
      args=["server.js"],
      env={"KEY": "value"},
    )
    data = provider.to_dict()
    self.assertEqual(data["kind"], "mcp")
    restored = AcpMcpProvider.from_dict(data)
    self.assertEqual(restored, provider)


class TestAcpPackage(unittest.TestCase):
  def test_round_trip(self) -> None:
    package = AcpPackage(
      metadata=AcpPackageMetadata(id="pkg.a", name="Pkg A", version="0.0.1"),
      locales={
        "en": AcpLocale(language="en", translations={"hello": "Hello"}),
        "zh": AcpLocale(language="zh", translations={"hello": "你好"}),
      },
      providers=[
        AcpToolProvider(id="t1", name="T1"),
        AcpMcpProvider(id="m1", name="M1", command="/bin/sh"),
      ],
      extra={"foo": "bar"},
    )
    data = package.to_dict()
    restored = AcpPackage.from_dict(data)
    self.assertEqual(restored, package)
    self.assertEqual(restored.id, "pkg.a")
    self.assertEqual(restored.name, "Pkg A")


class TestAcpLoader(unittest.TestCase):
  def test_load_file(self) -> None:
    with TemporaryDirectory() as tmp:
      path = Path(tmp) / "acp.json"
      package = AcpPackage(
        metadata=AcpPackageMetadata(id="loaded", name="Loaded", version="1.0.0"),
      )
      path.write_text(json.dumps(package.to_dict()), encoding="utf-8")
      loader = AcpLoader()
      loaded = loader.load_file(path)
      self.assertEqual(loaded.id, "loaded")

  def test_load_directory(self) -> None:
    with TemporaryDirectory() as tmp:
      path = Path(tmp) / "acp.json"
      package = AcpPackage(
        metadata=AcpPackageMetadata(id="dir", name="Dir", version="1.0.0"),
      )
      path.write_text(json.dumps(package.to_dict()), encoding="utf-8")
      loader = AcpLoader()
      loaded = loader.load_directory(tmp)
      self.assertEqual(loaded.id, "dir")

  def test_load_missing(self) -> None:
    with TemporaryDirectory() as tmp:
      loader = AcpLoader()
      with self.assertRaises(AcpLoadError):
        loader.load_file(Path(tmp) / "missing.json")


class TestAcpRegistry(unittest.TestCase):
  def test_register_and_lookup(self) -> None:
    registry = AcpRegistry()
    package = AcpPackage(
      metadata=AcpPackageMetadata(id="r1", name="R1", version="1.0.0"),
      locales={"en": AcpLocale(language="en", translations={"k": "v"})},
      providers=[AcpToolProvider(id="p1", name="P1")],
    )
    registry.register(package)
    self.assertEqual(registry.get_package("r1"), package)
    self.assertIsNotNone(registry.get_provider("p1"))
    self.assertIsNotNone(registry.get_locale("r1", "en"))
    self.assertEqual(registry.merge_translations("en"), {"k": "v"})

  def test_unregister(self) -> None:
    registry = AcpRegistry()
    package = AcpPackage(
      metadata=AcpPackageMetadata(id="r2", name="R2", version="1.0.0"),
      providers=[AcpToolProvider(id="p2", name="P2")],
    )
    registry.register(package)
    self.assertTrue(registry.unregister("r2"))
    self.assertIsNone(registry.get_package("r2"))
    self.assertIsNone(registry.get_provider("p2"))


if __name__ == "__main__":
  unittest.main()
