"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of zoompilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

Chill mode, which upstream retired and no longer runs its maneuvers in: the e2e candidate never
drives, and lead following and a set-speed drop still work on the MPC and cruise candidates.
"""
import pytest

from openpilot.selfdrive.controls.lib.longitudinal_planner import A_CRUISE_MIN, LongitudinalPlanSource
from openpilot.selfdrive.test.longitudinal_maneuvers.maneuver import Maneuver
from openpilot.selfdrive.test.longitudinal_maneuvers.plant import Plant
from openpilot.selfdrive.test.longitudinal_maneuvers.test_longitudinal import create_maneuvers


@pytest.mark.parametrize("force_decel", [False, True])
def test_upstream_maneuvers_in_chill(subtests, force_decel):
  for maneuver in create_maneuvers({"force_decel": force_decel, "experimental": False}):
    with subtests.test(title=maneuver.title):
      valid, _ = maneuver.evaluate()
      assert valid


def test_set_speed_drop_in_chill():
  # 25 m/s down to 15: reached, at no harder than upstream's cruise floor
  valid, logs = Maneuver("set speed drop", duration=40., initial_speed=25., cruise_values=[25., 15.],
                         breakpoints=[0., 2.], experimental=False).evaluate()
  assert valid
  speed, accel = logs[:, 3], logs[:, 5]
  assert speed[-1] == pytest.approx(15., abs=0.3)
  assert accel.min() >= A_CRUISE_MIN - 0.05


def test_e2e_never_drives_in_chill():
  # the model asks for more than cruise and MPC here, and less on a stopped lead: neither wins
  for v_lead in (30., 0.):
    plant = Plant(lead_relevancy=True, speed=20., distance_lead=60., experimental=False)
    sources = set()
    for _ in range(200):
      plant.step(v_lead, 1., 20.)
      sources.add(plant.planner.mpc.source)
    assert LongitudinalPlanSource.e2e not in sources, v_lead
