"""Convention gate: every `class CanBus` in the tree must derive from CanBusBase.

CanBusBase.offset = 4 * (len(CP.safetyConfigs) - 1) is what makes dual-panda CAN
mode (internal dos + external USB panda, pandad bus-block routing) work without
per-car edits. A CanBus class that does not derive from CanBusBase silently
addresses buses 0-2 only, i.e. the car loses multi-panda support.

Brands that hardcode bus literals without a CanBus class are allowed (same as
upstream: they are single-panda only) - the gate only fires when someone adds a
CanBus class and forgets the base.
"""
import ast
import unittest
from pathlib import Path


class TestCanBusConvention(unittest.TestCase):
  def test_canbus_classes_derive_from_canbus_base(self):
    root = Path(__file__).resolve().parents[1]
    offenders: list[str] = []

    for path in sorted(root.rglob("*.py")):
      if "__pycache__" in path.parts or "/tests/" in path.as_posix() or path.name.startswith("test_"):
        continue
      try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
      except SyntaxError:
        continue
      for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "CanBus":
          bases = {getattr(b, "id", getattr(b, "attr", None)) for b in node.bases}
          if "CanBusBase" not in bases:
            offenders.append(f"{path}: CanBus must derive from CanBusBase (dual-panda offset support)")

    self.assertEqual(offenders, [], "\n".join(offenders))


if __name__ == "__main__":
  unittest.main()
