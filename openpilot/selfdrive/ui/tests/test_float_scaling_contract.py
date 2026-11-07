"""`use_float_scaling` stores value/100, so it only works on a FLOAT parameter.

The control writes `params.put(key, value / 100.0)` and reads
`int(float(value) * 100)`. On an INT key both halves are wrong in different
ways: the read multiplies an already-scaled number by 100 again (110 becomes
11000, thirty times past the row's own maximum), and the write raises
TypeMismatch because `Params` only casts float into a FLOAT key. Neither shows
up until somebody presses the + button, so five rows sat like that - the four
TFollowGap knobs and DynamicTFollowLC.

It is a one-line mistake with no compile step to catch it and no import to
break, which is exactly the kind of thing a static check earns its keep on.

Plain `unittest.TestCase` and nothing but files and `ast` on purpose: the UI
package cannot be imported on a PC (it pulls PIL through the text measurer and
`fcntl` through Params), so anything that imports the widgets to inspect them
would be a device-only test - and a test that only runs on the device is a test
that does not run while the mistake is being made.
"""
import ast
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
PARAMS_KEYS = REPO_ROOT / "openpilot" / "common" / "params_keys.h"
UI_ROOT = REPO_ROOT / "openpilot" / "selfdrive" / "ui"
WIDGET_HELPERS = {"option_item_sp", "option_control_sp"}

# {"Key", {PERSISTENT | BACKUP, FLOAT, "0.1", std::nullopt, 2, SETTINGS_ADVANCED}},  // ...
_KEY_ENTRY = re.compile(r'^\s*\{[ ]*"([A-Za-z0-9_]+)"[ ]*,[ ]*\{[ ]*[A-Z_ |]+,[ ]*(BOOL|INT|FLOAT|STRING|JSON|BYTES)')


def declared_types() -> dict[str, str]:
  """Every key in params_keys.h with its declared type."""
  types: dict[str, str] = {}
  for line in PARAMS_KEYS.read_text(encoding="utf-8").splitlines():
    match = _KEY_ENTRY.match(line)
    if match:
      types[match.group(1)] = match.group(2)
  return types


def float_scaled_rows() -> list[tuple[str, str, int]]:
  """(path, param, lineno) for every row that asks the control to scale.

  A row whose `param` is a variable - the MPC tuning page builds its rows
  through a helper that takes the key as an argument - cannot be resolved
  statically, so it is skipped rather than reported. Its four call sites pass
  FLOAT keys; `test_the_scan_finds_rows_to_check` keeps that from silencing the
  whole scan if the helper is ever renamed.
  """
  rows = []
  for path in sorted(UI_ROOT.rglob("*.py")):
    try:
      tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
      continue
    for node in ast.walk(tree):
      if not isinstance(node, ast.Call):
        continue
      name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
      if name not in WIDGET_HELPERS:
        continue
      kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
      scaling = kwargs.get("use_float_scaling")
      if not (isinstance(scaling, ast.Constant) and scaling.value is True):
        continue
      param = kwargs.get("param")
      if isinstance(param, ast.Constant) and isinstance(param.value, str):
        rows.append((str(path.relative_to(REPO_ROOT)), param.value, node.lineno))
  return rows


def option_rows() -> list[tuple[str, str, int, bool]]:
  """(path, param, lineno, scaled) for every option row with a literal key."""
  rows = []
  for path in sorted(UI_ROOT.rglob("*.py")):
    try:
      tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
      continue
    for node in ast.walk(tree):
      if not isinstance(node, ast.Call):
        continue
      if getattr(node.func, "id", None) != "option_item_sp":
        continue
      kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
      param = kwargs.get("param")
      if not (isinstance(param, ast.Constant) and isinstance(param.value, str)):
        continue
      scaling = kwargs.get("use_float_scaling")
      scaled = isinstance(scaling, ast.Constant) and scaling.value is True
      rows.append((str(path.relative_to(REPO_ROOT)), param.value, node.lineno, scaled))
  return rows


class TestFloatScalingMatchesTheParameter(unittest.TestCase):
  def test_the_scan_finds_rows_to_check(self):
    """A silent scan would make the assertion below vacuous."""
    self.assertGreater(len(float_scaled_rows()), 0, "no use_float_scaling rows found - did the helper get renamed?")
    self.assertGreater(len(option_rows()), 0, "no option rows found - did the helper get renamed?")

  def test_every_scaled_row_targets_a_float_parameter(self):
    types = declared_types()
    offenders = []
    for path, param, lineno in float_scaled_rows():
      if param not in types:
        offenders.append(f"{path}:{lineno} {param} is not a registered parameter")
      elif types[param] != "FLOAT":
        offenders.append(f"{path}:{lineno} {param} is declared {types[param]}, but the control scales it by 100")
    self.assertFalse(offenders, "use_float_scaling on a non-FLOAT key:\n  " + "\n  ".join(offenders))

  def test_an_unscaled_row_targets_an_int_parameter(self):
    """The other half: without scaling the control writes a plain int.

    `params.put(key, int)` raises TypeMismatch on a FLOAT key, so a row that
    dropped `use_float_scaling` to fix the read side becomes a row that cannot
    save. DynamicTFollowLC was declared FLOAT with a percent-and-divide-by-100
    consumer, which is how it managed to be wrong in both directions at once.
    """
    types = declared_types()
    offenders = []
    for path, param, lineno, scaled in option_rows():
      if scaled:
        continue
      if param not in types:
        offenders.append(f"{path}:{lineno} {param} is not a registered parameter")
      elif types[param] not in ("INT", "BOOL"):
        offenders.append(f"{path}:{lineno} {param} is declared {types[param]}, but the control writes an int")
    self.assertFalse(offenders, "an int-only control on a non-INT key:\n  " + "\n  ".join(offenders))


if __name__ == "__main__":
  unittest.main()
