"""The angle controller's saturation flag must respect the car's own limiter.

Why this exists
---------------
`_check_saturation` decides when "steering saturated" degrades openpilot. Its
third argument says the car's torque/angle rate limiter is clipping the output
right now - and a large angle error under an active limiter is the limiter doing
its job, not the controller failing. `LatControlAngle` used to pass a hardcoded
`False`, so ordinary large requests on threshold cars (Nissan/Toyota/Ford)
accumulated saturation time and could fire the alert.

`False` is still correct for tesla/hyundai, whose `angle_control_saturated` is
derived FROM the limiter signal itself - passing the real value there would make
the flag permanently False and silently disable their saturation detection.

Adapted from upstream c61d998 via cp commit 8e7eec04. unittest so it runs on a
PC (only capnp is needed, not msgq) and on the device.
"""

import unittest
from types import SimpleNamespace

from openpilot.selfdrive.controls.lib.latcontrol_angle import LatControlAngle

DT = 0.01
SAT_LIMIT = 0.4
FRAMES = int(SAT_LIMIT / DT) + 10  # enough active frames to cross any sat_limit


def make_controller(brand="toyota"):
  return LatControlAngle(SimpleNamespace(steerLimitTimer=SAT_LIMIT, brand=brand), None, None, DT)


def make_state():
  return SimpleNamespace(vEgo=15.0, steeringAngleDeg=0.0, steeringPressed=False)


VM = SimpleNamespace(get_steer_from_curvature=lambda *_args: 0.2)  # radians; update() turns it into ~11.5 deg
PARAMS = SimpleNamespace(roll=0.0, angleOffsetDeg=0.0)


class TestAngleSaturationRespectsTheLimiter(unittest.TestCase):
  def _run_active(self, controller, steer_limited_by_safety, curvature_limited):
    status = None
    for _ in range(FRAMES):
      _, _, status = controller.update(True, make_state(), VM, PARAMS,
                                       steer_limited_by_safety, 0.01, None, curvature_limited, 0.0)
    return status

  def _test_matrix(self, brand):
    for limited in (False, True):
      for curvature_limited in (False, True):
        with self.subTest(brand=brand, limited=limited, curvature_limited=curvature_limited):
          status = self._run_active(make_controller(brand), limited, curvature_limited)
          if brand == "toyota":
            expected = not limited
          else:
            # hyundai: the limiter signal is the saturation signal, and curvature
            # limiting counts through the base class regardless of the third arg
            expected = limited or curvature_limited
          self.assertEqual(bool(status.saturated), expected)

  def test_threshold_car_limiter_explains_the_error(self):
    """Toyota path: the flag accumulates only when the limiter is NOT clipping."""
    self._test_matrix("toyota")

  def test_caroutput_car_keeps_its_signal(self):
    """Hyundai path: the limiter signal IS the saturation signal, unchanged."""
    self._test_matrix("hyundai")

  def test_recovery_after_the_fault_clears(self):
    controller = make_controller()
    self._run_active(controller, False, False)
    self.assertTrue(bool(self._run_active(controller, False, False).saturated))
    for _ in range(FRAMES):
      _, _, status = controller.update(False, make_state(), VM, PARAMS, False, 0.01, None, False, 0.0)
    self.assertFalse(bool(status.saturated))
    self.assertEqual(controller.sat_time, 0.0)


if __name__ == "__main__":
  unittest.main()
