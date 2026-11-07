"""Offline tests for ai.lsp.index and ai.lsp.search."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from ai.lsp.index import Symbol, SymbolIndex, SymbolKind
from ai.lsp.search import search_documents, search_symbols


class TestSymbolIndex(unittest.TestCase):
  def test_add_document_symbols(self):
    index = SymbolIndex()
    count = index.add_document_symbols("file:///a.py", [
      {"name": "foo", "kind": SymbolKind.FUNCTION, "range": {"start": {"line": 0, "character": 0}, "end": {"line": 1, "character": 1}}},
      {"name": "Bar", "kind": SymbolKind.CLASS, "range": {"start": {"line": 2, "character": 0}, "end": {"line": 5, "character": 1}},
       "children": [
         {"name": "baz", "kind": SymbolKind.METHOD, "range": {"start": {"line": 3, "character": 2}, "end": {"line": 3, "character": 10}}},
       ]},
    ])
    self.assertEqual(count, 3)
    self.assertEqual(len(index.lookup_by_file("file:///a.py")), 3)
    self.assertEqual(len(index.lookup("baz")), 1)
    self.assertEqual(index.lookup("baz")[0].container_name, "Bar")

  def test_add_workspace_symbols(self):
    index = SymbolIndex()
    index.add_workspace_symbols([
      {"name": "helper", "kind": SymbolKind.FUNCTION, "location": {"uri": "file:///b.py", "range": {"start": {"line": 10, "character": 0}, "end": {"line": 10, "character": 10}}}, "containerName": "module"},
    ])
    self.assertEqual(len(index.lookup("helper")), 1)
    self.assertEqual(index.lookup("helper")[0].uri, "file:///b.py")

  def test_lookup_by_kind(self):
    index = SymbolIndex()
    index.add_document_symbols("file:///c.py", [
      {"name": "cls", "kind": SymbolKind.CLASS, "range": {"start": {"line": 0, "character": 0}, "end": {"line": 1, "character": 1}}},
      {"name": "fn", "kind": SymbolKind.FUNCTION, "range": {"start": {"line": 2, "character": 0}, "end": {"line": 3, "character": 1}}},
    ])
    self.assertEqual(len(index.lookup_by_kind(SymbolKind.CLASS)), 1)
    self.assertEqual(len(index.lookup_by_kind(SymbolKind.FUNCTION)), 1)

  def test_clear_file(self):
    index = SymbolIndex()
    index.add_document_symbols("file:///d.py", [
      {"name": "x", "kind": SymbolKind.VARIABLE, "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}}},
    ])
    index.clear_file("file:///d.py")
    self.assertEqual(len(index.lookup("x")), 0)
    self.assertEqual(len(index.lookup_by_file("file:///d.py")), 0)


class TestSymbolSearch(unittest.TestCase):
  def test_search_symbols_by_name(self):
    index = SymbolIndex()
    index.add_document_symbols("file:///a.py", [
      {"name": "fetchData", "kind": SymbolKind.FUNCTION, "range": {"start": {"line": 0, "character": 0}, "end": {"line": 1, "character": 1}}},
      {"name": "process", "kind": SymbolKind.FUNCTION, "range": {"start": {"line": 2, "character": 0}, "end": {"line": 3, "character": 1}}},
    ])
    results = search_symbols(index, "fetch")
    self.assertEqual(len(results), 1)
    self.assertEqual(results[0].name, "fetchData")

  def test_search_symbols_kind_filter(self):
    index = SymbolIndex()
    index.add_document_symbols("file:///a.py", [
      {"name": "MyClass", "kind": SymbolKind.CLASS, "range": {"start": {"line": 0, "character": 0}, "end": {"line": 1, "character": 1}}},
      {"name": "my_fn", "kind": SymbolKind.FUNCTION, "range": {"start": {"line": 2, "character": 0}, "end": {"line": 3, "character": 1}}},
    ])
    results = search_symbols(index, "my", kind=SymbolKind.CLASS)
    self.assertEqual(len(results), 1)
    self.assertEqual(results[0].kind, SymbolKind.CLASS)

  def test_search_documents(self):
    files = ["/src/main.py", "/src/utils.py", "/tests/test.py"]
    self.assertEqual(search_documents(files, "utils"), ["/src/utils.py"])
    self.assertEqual(len(search_documents(files, ".py", limit=2)), 2)


if __name__ == "__main__":
  unittest.main()
