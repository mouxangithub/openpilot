"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of zoompilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

The torque bar and the lane lines reach full scale at the EPS rail, where a
torque tune saturates: on a tuned car the carcontroller's full scale is past
what the rack can deliver, so a bar drawn against it tops out late.
"""
import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("SCALE", "1")

from openpilot.common.prefix import OpenpilotPrefix
from openpilot.common.test import OpenpilotTestCase

# the window's own params, for whatever it reads while it comes up
_window_prefix = OpenpilotPrefix()


def setUpModule():
  import pyray as rl
  from openpilot.system.ui.lib.application import gui_app
  _window_prefix.__enter__()
  rl.set_config_flags(rl.FLAG_WINDOW_HIDDEN)
  gui_app.init_window("test_torque_utilization", fps=30)


def tearDownModule():
  from openpilot.system.ui.lib.application import gui_app
  gui_app.close()
  _window_prefix.__exit__(None, None, None)


def _utilization(CP, torque, v_ego):
  from openpilot.selfdrive.ui.ui_state import ui_state
  from opendbc.sunnypilot.car.interfaces import get_steer_rail_schedule
  with mock.patch.object(ui_state, '_steer_rail_schedule', get_steer_rail_schedule(CP)), \
       mock.patch.object(ui_state, 'sm', {
         'carOutput': SimpleNamespace(actuatorsOutput=SimpleNamespace(torque=torque)),
         'carState': SimpleNamespace(vEgo=v_ego),
       }):
    ui_state._update_torque_utilization()
    return ui_state.torque_utilization


def _mazda():
  from opendbc.car import structs
  from opendbc.car.mazda.values import CAR, MazdaFlags
  return structs.CarParams(brand='mazda', carFingerprint=CAR.MAZDA_CX5_2022,
                           flags=int(MazdaFlags.GEN1 | MazdaFlags.STEER_TO_ZERO_EPS))


class TestTorqueUtilization(OpenpilotTestCase):
  # route 21d103861daeed11/000003db--f4124f0aa8/8, t=10.39: 620 counts at 19.7 m/s, pinned there
  # 0.7 s before steerSaturated; the old bar read 0.775 of that build's 800 scale
  def test_rail_is_full_scale(self):
    CP = _mazda()
    for v_ego, torque in ((19.69, 620 / 1200), (13.9, 676 / 1200), (10.3, 1048 / 1200)):
      self.assertAlmostEqual(_utilization(CP, torque, v_ego), 1.0, places=3)

  def test_below_rail_is_proportional(self):
    self.assertAlmostEqual(_utilization(_mazda(), -310 / 1200, 20.0), -0.5, places=3)

  def test_no_ceiling_is_applied_torque(self):
    # a car with no rail schedule: the raw applied torque, unchanged
    from opendbc.car import structs
    self.assertAlmostEqual(_utilization(structs.CarParams(brand='toyota'), 0.6, 20.0), 0.6, places=3)

  def test_torque_bar_reads_it(self):
    from openpilot.selfdrive.ui.mici.onroad.torque_bar import TorqueBar
    _utilization(_mazda(), 620 / 1200, 19.69)
    bar = TorqueBar()
    for _ in range(200):
      bar._update_state()
    self.assertAlmostEqual(bar._torque_filter.x, -1.0, places=3)


if __name__ == '__main__':
  unittest.main()
