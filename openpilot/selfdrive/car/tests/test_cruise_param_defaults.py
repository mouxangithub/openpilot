"""Guard the driving-path settings reads against an unwritten key.

``Params.get()`` returns ``None`` for a key that was never written. VCruiseCarrot
does arithmetic and comparisons on nearly every setting it reads, so one missing
key raised ``TypeError`` inside ``Car()`` and took the card process down before
it could publish carState:

    TypeError: '>' not supported between instances of 'NoneType' and 'int'

reading ``AutoEngage`` from an empty params directory (seen in
``openpilot.selfdrive.controls.tests.test_leads``). Every read now goes through
``_param()``, which passes ``return_default=True`` and therefore yields the
default declared in ``params_keys.h``.

This test parses the AST, so it needs no opendbc/numpy and runs on Windows too.

    PYTHONPATH=. python -m unittest openpilot.selfdrive.car.tests.test_cruise_param_defaults
"""
import ast
import unittest
from pathlib import Path

CRUISE_PATH = Path(__file__).resolve().parents[1] / 'cruise.py'


def class_node(name, src):
  for node in ast.walk(ast.parse(src)):
    if isinstance(node, ast.ClassDef) and node.name == name:
      return node
  raise AssertionError(f'class {name} not found in {CRUISE_PATH}')


def param_get_calls(fn):
  """Every ``self.params.get(...)`` call inside ``fn``."""
  return [node for node in ast.walk(fn)
          if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
          and node.func.attr == 'get' and isinstance(node.func.value, ast.Attribute)
          and node.func.value.attr == 'params']


class TestCruiseParamReads(unittest.TestCase):
  def setUp(self):
    self.src = CRUISE_PATH.read_text(encoding='utf-8')
    self.klass = class_node('VCruiseCarrot', self.src)

  def methods(self):
    return {f.name: f for f in self.klass.body if isinstance(f, ast.FunctionDef)}

  def test_every_setting_read_goes_through_param(self):
    """A direct self.params.get() reintroduces the None arithmetic crash."""
    methods = self.methods()
    offenders = sorted(name for name, fn in methods.items()
                       if name != '_param' and param_get_calls(fn))
    self.assertEqual(offenders, [], f'read these settings through _param() in {CRUISE_PATH.name}: {offenders}')

  def test_param_returns_the_registered_default(self):
    methods = self.methods()
    self.assertIn('_param', methods, 'VCruiseCarrot._param() is the only sanctioned settings read')
    calls = param_get_calls(methods['_param'])
    self.assertEqual(len(calls), 1, '_param() should contain exactly one self.params.get() call')
    keywords = {k.arg: k.value for k in calls[0].keywords}
    self.assertIn('return_default', keywords, '_param() must pass return_default=True')
    self.assertIsInstance(keywords['return_default'], ast.Constant)
    self.assertIs(keywords['return_default'].value, True)


if __name__ == '__main__':
  unittest.main()
