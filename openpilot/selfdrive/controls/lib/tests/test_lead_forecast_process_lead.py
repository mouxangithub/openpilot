"""The lead-forecast wrapper must accept what the MPC actually passes it.

Why this exists
---------------
`LeadForecast.install()` replaces `mpc.process_lead` with its own method, and
`LongitudinalPlanner.__init__` installs it unconditionally. The port came from
zoompilot, whose `LongitudinalMpc.process_lead(self, lead)` took one argument;
this fork's takes `lead_index`, `model_lead` and `smooth_duplicate_vision` as
well, and its `update()` passes all three by keyword. The wrapper kept the
zoompilot signature, so the first planning frame of every drive died with

    TypeError: LeadForecast.process_lead() got an unexpected keyword argument 'lead_index'

and plannerd was not running at all. Nothing caught it: the module's own tests
import msgq (unavailable on a PC) and require pytest (unavailable on the
device), so they had never executed anywhere.

This file reads both sides with `ast` and never imports either, so it runs
wherever plain Python does. It is deliberately about the *contract* - the
argument names `update()` sends - not about whether an individual call works.

Run from the repo root:

    python -m unittest openpilot.selfdrive.controls.lib.tests.test_lead_forecast_process_lead
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
MPC = REPO_ROOT / "openpilot" / "selfdrive" / "controls" / "lib" / "longitudinal_mpc_lib" / "long_mpc.py"
FORECAST = REPO_ROOT / "openpilot" / "sunnypilot" / "selfdrive" / "controls" / "lib" / "lead_forecast" / "forecast.py"


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
  for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name == name:
      return node
  raise AssertionError(f"class {name} not found")


def _method(cls: ast.ClassDef, name: str) -> ast.FunctionDef:
  for node in cls.body:
    if isinstance(node, ast.FunctionDef) and node.name == name:
      return node
  raise AssertionError(f"{cls.name}.{name}() not found")


def _parse(path: Path) -> ast.Module:
  return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def mpc_process_lead_calls() -> list[ast.Call]:
  """Every `self.process_lead(...)` call in the MPC class."""
  cls = _class(_parse(MPC), "LongitudinalMpc")
  return [node for node in ast.walk(cls)
          if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "process_lead"]


def wrapper_signature() -> ast.FunctionDef:
  return _method(_class(_parse(FORECAST), "LeadForecast"), "process_lead")


def accepts(func: ast.FunctionDef, keyword: str) -> bool:
  """Whether `func` takes `keyword` - named, or through **kwargs."""
  for arg in func.args.kwonlyargs:
    if arg.arg == keyword:
      return True
  if any(a.arg == keyword for a in func.args.args):
    return True
  return func.args.kwarg is not None


def installs_itself() -> tuple[bool, bool]:
  """(patches mpc.process_lead, forwards to the captured original)."""
  install = _method(_class(_parse(FORECAST), "LeadForecast"), "install")
  patches = any(isinstance(n, ast.Assign) and any(
    isinstance(t, ast.Attribute) and t.attr == "process_lead" and isinstance(t.value, ast.Name) and t.value.id == "mpc"
    for t in n.targets) for n in ast.walk(install))
  wrapper = wrapper_signature()
  forwards = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "_upstream_process_lead" and
                 any(isinstance(a, ast.Starred) for a in n.args) and n.keywords and
                 any(k.arg is None for k in n.keywords) for n in ast.walk(wrapper))
  return patches, forwards


class TestTheWrapperTakesWhatTheMpcSends(unittest.TestCase):
  def test_the_scan_finds_both_call_sites(self):
    """A guard that scans nothing passes everything."""
    calls = mpc_process_lead_calls()
    self.assertEqual(2, len(calls), "the MPC is expected to extrapolate leadOne and leadTwo")

  def test_every_keyword_the_mpc_passes_is_accepted(self):
    keywords = sorted({k.arg for call in mpc_process_lead_calls() for k in call.keywords if k.arg})
    self.assertTrue(keywords, "the MPC passes no keywords, so this test would prove nothing")
    wrapper = wrapper_signature()
    missing = [k for k in keywords if not accepts(wrapper, k)]
    self.assertEqual([], missing,
                     "LeadForecast.process_lead cannot take these; installing it makes every planning frame raise TypeError")

  def test_the_wrapper_is_actually_installed_and_forwards(self):
    patches, forwards = installs_itself()
    self.assertTrue(patches, "install() no longer replaces mpc.process_lead, so this contract is moot")
    self.assertTrue(forwards, "the wrapper must forward *args/**kwargs to the original process_lead")

  def test_the_cover_story_is_that_a_one_argument_wrapper_fails(self):
    """The shape that broke: a wrapper taking only `lead`."""
    one_arg = ast.parse("def process_lead(self, lead):\n  pass\n").body[0]
    keywords = sorted({k.arg for call in mpc_process_lead_calls() for k in call.keywords if k.arg})
    missing = [k for k in keywords if not accepts(one_arg, k)]
    self.assertIn("lead_index", missing)


if __name__ == "__main__":
  unittest.main()
