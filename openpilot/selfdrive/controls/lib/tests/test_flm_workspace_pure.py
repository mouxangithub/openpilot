"""Pure-logic unit tests for the ported FLM analyzer helpers.

These only cover functions that are importable on dev machines; anything that
needs the built capnp modules or Params-backed device state is out of scope
(the analyzer itself only runs on device).
"""
import tempfile
import unittest
from pathlib import Path

from openpilot.selfdrive.controls.lib.flm_workspace import (
  _car_params_control_path,

  _get_segments_in_route,
  _stock_kp,
  _require_car,
)
from openpilot.sunnypilot.common.lateral_delay import LATERAL_CONTROL_SOFTWARE_DELAY, full_lateral_delay


class TestGetSegmentsInRoute(unittest.TestCase):
  def test_returns_empty_for_missing_root(self):
    self.assertEqual(_get_segments_in_route("some-route", str(Path(tempfile.gettempdir()) / "flm-nope-xyz")), [])

  def test_collects_segment_dirs_sorted_by_number(self):
    with tempfile.TemporaryDirectory() as root:
      for name in ("routeA--10", "routeA--2", "routeA--0", "other--3", "routeA--notes"):
        Path(root, name).mkdir()
      Path(root, "routeA--0", "f.log").touch()
      self.assertEqual(
        _get_segments_in_route("routeA", root),
        ["routeA--0", "routeA--2", "routeA--10"],
      )


class TestCarParamsControlPath(unittest.TestCase):
  def test_raises_without_built_cereal_modules(self):
    try:
      from openpilot.cereal import car  # noqa: F401
      has_car = True
    except ImportError:
      has_car = False
    if has_car:
      self.skipTest("built capnp modules present; device-style assertion applies")

    with self.assertRaises(RuntimeError):
      _car_params_control_path(object())

  def test_classifies_torque_stub(self):
    try:
      _require_car()
    except RuntimeError:
      self.skipTest("built capnp modules unavailable on this machine")
    stub = type("Stub", (), {"steerControlType": _require_car().CarParams.SteerControlType.angle})()
    self.assertEqual(_car_params_control_path(stub), "angle")


class TestMiscHelpers(unittest.TestCase):
  def test_stock_kp_matches_latcontrol_torque(self):
    try:
      from openpilot.selfdrive.controls.lib.latcontrol_torque import KP
    except (ImportError, ModuleNotFoundError):
      self.skipTest("latcontrol_torque import chain needs fcntl (device/Linux only)")
    self.assertEqual(_stock_kp(), float(KP))

  def test_full_lateral_delay_adds_software_delay(self):
    self.assertEqual(full_lateral_delay(0.15), 0.15 + LATERAL_CONTROL_SOFTWARE_DELAY)


if __name__ == "__main__":
  unittest.main()
