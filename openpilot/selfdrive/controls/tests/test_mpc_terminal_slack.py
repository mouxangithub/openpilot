"""The longitudinal MPC terminal stage carries the same soft constraint.

Why this exists
---------------
`gen_long_ocp` defined the slack constraint only for stages 0..N-1: no
`con_h_expr_e`, no `zl_e/Zl_e/Zu_e/zu_e`, no `lh_e/uh_e/idxsh_e`, and the
runtime `Zl` loop stopped at N. A solver stopped early could therefore
overrun the terminal constraint (StarPilot saw a -15.95 m/s terminal speed
recovering a reverse plan). Ported from StarPilot e75470f2e; the solver is
rebuilt by SCons, so this pins the python source, the build script and a
real solve.

unittest so it runs on the device. The solver import fails on the PC (no
compiled acados pyx) - that part is skipped with an explicit reason there,
and the AST half still runs.
"""
import unittest
from pathlib import Path
import os

REPO_ROOT = Path(__file__).resolve().parents[4]
MPC_PATH = REPO_ROOT / 'openpilot' / 'selfdrive' / 'controls' / 'lib' / 'longitudinal_mpc_lib' / 'long_mpc.py'
SCONS_PATH = REPO_ROOT / 'openpilot' / 'selfdrive' / 'controls' / 'lib' / 'longitudinal_mpc_lib' / 'SConscript'

ON_DEVICE = os.path.isfile('/AGNOS')


class TheGeneratedOpcCarriesTheTerminalConstraint(unittest.TestCase):
  """Pure AST: pins the python source and the build script on any machine."""

  def test_gen_long_ocp_defines_the_terminal_constraint(self):
    src = MPC_PATH.read_text(encoding='utf-8')
    for needle in ('con_h_expr_e', 'zl_e', 'Zl_e', 'Zu_e', 'zu_e', 'lh_e', 'uh_e', 'idxsh_e'):
      self.assertIn(needle, src, f'gen_long_ocp is missing the terminal piece {needle!r}')

  def test_the_runtime_zl_loop_covers_the_terminal_stage(self):
    src = MPC_PATH.read_text(encoding='utf-8')
    self.assertIn("for i in range(N+1):\n      self.solver.cost_set(i, 'Zl', Zl)", src,
                  'the Zl loop must include the terminal stage')

  def test_scons_builds_the_terminal_constraint_sources(self):
    src = SCONS_PATH.read_text(encoding='utf-8')
    self.assertIn('long_constr_h_e_fun.c', src)
    self.assertIn('long_constr_h_e_fun_jac_uxt_zt.c', src)


@unittest.skipUnless(ON_DEVICE, 'the compiled acados pyx only exists on device')
class TheRebuiltSolverSolves(unittest.TestCase):
  def test_an_open_road_solve_succeeds_without_a_negative_speed_plan(self):
    import numpy as np
    import openpilot.cereal.messaging as messaging
    from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import LongitudinalMpc

    mpc = LongitudinalMpc()
    rs = messaging.new_message('radarState')
    rs.radarState.leadOne.present = False
    rs.radarState.leadTwo.present = False

    for _ in range(5):
      mpc.set_cur_state(20.0, 0.0)
      mpc.update(rs.radarState)
      self.assertEqual(mpc.solution_status, 0)
      self.assertGreaterEqual(float(np.min(mpc.v_solution)), -0.01,
                              'an open road must not plan a reversing terminal speed')
      self.assertGreaterEqual(mpc.v_solution[1], 19.0)


if __name__ == '__main__':
  unittest.main()
