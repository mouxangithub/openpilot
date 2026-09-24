"""Signature-contract test for VCruiseCarrot's overrides.

Why this exists
---------------
card.py calls the cruise helper polymorphically:

    self.v_cruise_helper.update_v_cruise(CS, self.sm['carControl'].enabled, self.is_metric, self.sm)
    self.v_cruise_helper.initialize_v_cruise(self.CS_prev, self.experimental_mode,
                                             self.dynamic_experimental_control)

`self.v_cruise_helper` is VCruiseHelper at runtime but VCruiseCarrot in cp ports,
so every override MUST keep a signature the base-class call site satisfies. Two
narrower overrides already shipped and both crashed on the device:

  * update_v_cruise(CS, sm, is_metric)          -> TypeError: 'bool' object is not subscriptable
  * initialize_v_cruise(CS, experimental_mode)  -> TypeError: takes 3 positional arguments but 4 were given

Neither is visible to py_compile or to a source review of cruise.py alone - they
only fire when the car enables, which is exactly when nobody is reading logs.
This test parses the AST (no opendbc/numpy/fcntl imports, so it runs on Windows
too) and asserts each override accepts the base call site's argument count.

Run from the repo root:

    PYTHONPATH=. python -m pytest openpilot/selfdrive/car/tests/test_vcruise_carrot_signatures.py -q
"""
from __future__ import annotations

import ast
from pathlib import Path

CRUISE_PATH = Path(__file__).resolve().parents[1] / 'cruise.py'

# (method name, number of positional args card.py passes, excluding self)
CARD_CALL_SITES = {
  'update_v_cruise': 3,        # CS, enabled, is_metric  (+ sm as the 4th for VCruiseCarrot)
  'initialize_v_cruise': 3,    # CS, experimental_mode, dynamic_experimental_control
}


def _methods(class_name: str, src: str) -> dict[str, ast.FunctionDef]:
  tree = ast.parse(src)
  for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name == class_name:
      return {f.name: f for f in node.body if isinstance(f, ast.FunctionDef)}
  raise AssertionError(f'class {class_name} not found in {CRUISE_PATH}')


def _arg_bounds(fn: ast.FunctionDef) -> tuple[int, int]:
  """Return (mandatory, total) positional parameters, excluding self."""
  total = len(fn.args.args) - 1
  return total - len(fn.args.defaults), total


def test_vcruise_carrot_overrides_accept_the_card_call_site():
  src = CRUISE_PATH.read_text(encoding='utf-8')
  base = _methods('VCruiseHelper', src)
  overrides = _methods('VCruiseCarrot', src)

  for name, call_args in CARD_CALL_SITES.items():
    assert name in overrides, f'VCruiseCarrot no longer overrides {name}'

    base_mandatory, base_total = _arg_bounds(base[name])
    assert base_mandatory <= call_args <= base_total, (
      f'VCruiseHelper.{name} cannot accept {call_args} positional args '
      f'(mandatory={base_mandatory}, total={base_total})'
    )

    mandatory, total = _arg_bounds(overrides[name])
    assert mandatory <= call_args <= total, (
      f'VCruiseCarrot.{name} narrows the base signature: cannot accept '
      f'{call_args} positional args (mandatory={mandatory}, total={total}). '
      f'card.py calls it polymorphically, so this raises TypeError on engage.'
    )


def test_update_v_cruise_accepts_the_optional_extra_args():
  """card.py passes sm and CS_SP as the 4th/5th arguments; both must stay optional.

    Making either mandatory would break the base-class call shape used by tests and
    by any brand that drives VCruiseHelper directly:
        update_v_cruise(CS, enabled, is_metric)

    CS_SP is how _prepare_buttons reaches the VW stage-2 stalk latch. It cannot be
    read from SubMaster: card.py is the *publisher* of carStateSP, so
    sm['carStateSP'] raises KeyError (same trap as the earlier longitudinalPlan bug).
    """
  src = CRUISE_PATH.read_text(encoding='utf-8')
  override = _methods('VCruiseCarrot', src)['update_v_cruise']
  mandatory, total = _arg_bounds(override)
  assert total == 5, f'expected 5 positional params (CS, enabled, is_metric, sm, CS_SP), got {total}'
  assert mandatory <= 3, f'sm and CS_SP must be optional; mandatory={mandatory}'


def test_submaster_does_not_supply_carstate_sp():
  """Guard against re-introducing sm['carStateSP'].

    card.py owns carStateSP as a publisher, so it is absent from its SubMaster.
    Reading it from `sm` raises KeyError on the first cruise tick, which is the
    exact class of bug that already took card.py down twice.
    """
  card_src = (CRUISE_PATH.parent / 'card.py').read_text(encoding='utf-8')
  cruise_src = CRUISE_PATH.read_text(encoding='utf-8')
  assert "sm['carStateSP']" not in cruise_src, "carStateSP is not in card.py's SubMaster - read it from the passed CS_SP"
  assert "'carStateSP'" in card_src, 'card.py no longer mentions carStateSP at all?'
