"""
Copyright (c) 2026-, mouxan.

Checks the mici models panel after the zoompilot develop merge: the panel
builds, the model options (lane center, lane turn, steer delay, camera
offset) are in the list, and the panel's rows are the ones the merged
layout expects.

Deliberately NOT named test_*.py: it installs sys.modules stubs (fake
pyray / application / params) and pytest must not collect it into the
normal run. Run it directly:

  PYTHONPATH=.;opendbc_repo python openpilot/selfdrive/ui/tests/mici_models_panel_smoke.py
"""
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

os.environ.setdefault("SCALE", "1")

# The device-only GPIO layer imports fcntl, which a PC has not; the panel
# never touches it, so a stub is enough to import the widgets here.
if "fcntl" not in sys.modules:
  fcntl = types.ModuleType("fcntl")
  fcntl.flock = lambda *a, **k: None
  fcntl.ioctl = lambda *a, **k: 0
  fcntl.LOCK_EX = fcntl.LOCK_SH = fcntl.LOCK_NB = fcntl.LOCK_UN = 1
  sys.modules["fcntl"] = fcntl

from carrot_tuning_render_smoke import (  # noqa: E402
  build_fake_application, build_fake_multilang, build_fake_params, build_fake_pyray, install_stubs,
)


def main() -> int:
  # The settings panels' smoke test already installs the whole stub set
  # (fake pyray / application / params / ui_state with its device), which the
  # mici widgets need as much as the settings ones do.
  sys.path.insert(0, str(Path(__file__).resolve().parent))
  from settings_panels_render_smoke import install

  install()

  failures = []
  checks = 0

  def check(name, fn):
    nonlocal checks
    checks += 1
    try:
      fn()
      print(f"  ok  {name}")
    except Exception as exc:
      failures.append(f"{name}: {exc}")
      print(f"  FAIL  {name}: {exc}")

  from openpilot.selfdrive.ui.sunnypilot.mici.layouts.models import ModelsLayoutMici

  def panel_builds():
    layout = ModelsLayoutMici()
    assert layout is not None
    assert layout.main_items, "the panel has no rows"

  check("mici models panel builds", panel_builds)

  def options_present():
    layout = ModelsLayoutMici()
    opts = layout._options
    for name in ("lane_center", "lane_turn", "lane_turn_speed", "live_delay", "steer_delay", "camera_offset"):
      assert hasattr(opts, name), f"ModelOptions has no {name}"
    assert len(opts.items) == 5, f"expected five option rows, got {len(opts.items)}"

  check("ModelOptions carries every option", options_present)

  def blendful_is_the_option():
    layout = ModelsLayoutMici()
    assert layout.blendful_toggle is layout._options.lane_center, "the panel's blendful row is not the lane center option"

  check("the panel's blendful row is the lane center option", blendful_is_the_option)

  def every_row_in_the_scroller():
    layout = ModelsLayoutMici()
    assert len(layout.main_items) >= 8, f"too few rows: {len(layout.main_items)}"
    # the options rows are in the list, in the order the options declare them
    idx = [layout.main_items.index(i) for i in layout._options.items]
    assert idx == sorted(idx), f"option rows out of order: {idx}"

  check("the option rows are in the panel, in order", every_row_in_the_scroller)

  print()
  if failures:
    print(f"FAILED {len(failures)}/{checks} checks:")
    for f in failures:
      print(f"  - {f}")
    return 1
  print(f"PASSED {checks}/{checks} checks")
  return 0


if __name__ == "__main__":
  sys.exit(main())
