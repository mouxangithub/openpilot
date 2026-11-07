"""Every in-tree relative import must name something the target module defines.

Why a test and not just lint: `from .settings import carrot_defaults` is syntactically
perfect, so ruff says nothing, and because the import sits inside a function body it is
not evaluated until the handler runs. The result is a feature that looks shipped and
returns 500 the first time somebody touches it - which is exactly what happened to
`POST /api/setting_profiles`: the name lives in `settings_sp`, not `settings`.

The check is static on purpose: the carrot server imports `fcntl` through
`openpilot.common.params`, so it cannot be imported on a PC at all. Parsing the ASTs of
both sides answers the question without running either.
"""
import ast
import os
import unittest

CARROT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _module_names(path: str) -> set[str] | None:
  """Every name a module binds at its own top level, or None if it will not parse."""
  try:
    with open(path, encoding="utf-8") as f:
      tree = ast.parse(f.read())
  except (OSError, SyntaxError):
    return None
  names: set[str] = set()
  for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
      names.add(node.name)
    elif isinstance(node, ast.Assign):
      names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
      names.add(node.target.id)
    elif isinstance(node, (ast.Import, ast.ImportFrom)):
      names.update(a.asname or a.name.split(".")[0] for a in node.names)
  return names


def _resolve(package_dir: str, node: ast.ImportFrom) -> str | None:
  """The file a relative `ImportFrom` points at, or None when it is outside the tree."""
  base = package_dir
  for _ in range(node.level - 1):
    base = os.path.dirname(base)
  if node.module:
    base = os.path.join(base, *node.module.split("."))
  for candidate in (base + ".py", os.path.join(base, "__init__.py")):
    if os.path.isfile(candidate):
      return candidate
  return None


def _is_submodule(target: str, name: str) -> bool:
  """`from . import foo` names a module, which `__init__.py` need not re-export."""
  package_dir = os.path.dirname(target)
  return (os.path.isfile(os.path.join(package_dir, name + ".py"))
          or os.path.isfile(os.path.join(package_dir, name, "__init__.py")))


def missing_imports(root: str) -> list[str]:
  """`path:line -> module.name` for every relative import that cannot resolve."""
  problems: list[str] = []
  for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if d != "__pycache__"]
    for filename in filenames:
      if not filename.endswith(".py"):
        continue
      path = os.path.join(dirpath, filename)
      try:
        with open(path, encoding="utf-8") as f:
          tree = ast.parse(f.read())
      except (OSError, SyntaxError):
        continue
      for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.level:
          continue
        target = _resolve(dirpath, node)
        if target is None:
          continue
        defined = _module_names(target)
        if defined is None:
          continue
        for alias in node.names:
          if alias.name == "*" or alias.name in defined:
            continue
          if _is_submodule(target, alias.name):
            continue
          where = f"{os.path.relpath(path, root)}:{node.lineno}"
          problems.append(f"{where} -> {os.path.relpath(target, root)}.{alias.name}")
  return problems


class RelativeImportResolutionTests(unittest.TestCase):

  def test_every_relative_import_resolves(self):
    problems = missing_imports(CARROT_ROOT)
    self.assertFalse(problems, "relative imports naming nothing:\n  " + "\n  ".join(problems))

  def test_the_check_can_actually_fail(self):
    """Guard the guard: a vacuous pass would hide the very bug this file exists for."""
    self.assertTrue(_module_names(os.path.abspath(__file__)))
    sample = ast.parse("from .settings import carrot_defaults\n")
    node = sample.body[0]
    assert isinstance(node, ast.ImportFrom)
    servicess = os.path.join(CARROT_ROOT, "server", "services")
    target = _resolve(servicess, node)
    self.assertIsNotNone(target)
    self.assertNotIn("carrot_defaults", _module_names(target) or set())


if __name__ == "__main__":
  unittest.main()
