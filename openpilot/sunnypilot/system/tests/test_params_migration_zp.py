"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of zoompilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from openpilot.common.params import Params, UnknownKeyName
from openpilot.common.test import OpenpilotTestCase
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.common import Policy
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.source_auto import AUTO
from openpilot.sunnypilot.system.params_migration_zp import E2E_ASSISTS, E2E_ASSISTS_MIGRATED, LANE_CENTER_MIGRATED, run_migration_zp


class TestE2EAssistsMigration(OpenpilotTestCase):
  """Existing installs hold the old declared default (off) on disk; the migration turns the
  assists on once, then leaves the driver's choice alone."""

  def test_turns_on_the_materialized_old_default(self):
    params = Params()
    for key in E2E_ASSISTS:
      params.put_bool(key, False, block=True)  # what manager_init wrote under the old default
    run_migration_zp(params)
    assert all(params.get_bool(key) for key in E2E_ASSISTS)
    assert params.get_bool(E2E_ASSISTS_MIGRATED)

  def test_runs_once(self):
    params = Params()
    run_migration_zp(params)
    params.put_bool("ExperimentalModeSetSpeed", False, block=True)  # the driver turns it off
    run_migration_zp(params)
    assert not params.get_bool("ExperimentalModeSetSpeed")

  def test_unknown_key_on_stale_native_lib_does_not_take_down_boot(self):
    # Regression: a pull that registers new keys while libparams_c.so is still stale makes
    # check_key raise UnknownKeyName. The marker read used to run outside the try block,
    # escaping into manager_init and crashing manager before any daemon spawned.
    params = Params()
    real_get_bool = params.get_bool

    def raising_get_bool(key, block=False):
      if key == E2E_ASSISTS_MIGRATED:
        raise UnknownKeyName(key.encode())
      return real_get_bool(key, block)

    params.get_bool = raising_get_bool
    run_migration_zp(params)  # must not raise

  def test_one_bad_hook_does_not_block_the_other(self):
    params = Params()

    def boom(_params):
      raise RuntimeError("unexpected migration failure")

    from openpilot.sunnypilot.system import params_migration_zp as mod
    original = (mod._migrate_e2e_assists_on, mod.seed_car_defaults_offroad)
    mod.seed_car_defaults_offroad = boom
    try:
      run_migration_zp(params)  # boom is swallowed; e2e marker still applied
    finally:
      mod._migrate_e2e_assists_on, mod.seed_car_defaults_offroad = original
    assert params.get_bool(E2E_ASSISTS_MIGRATED)

class TestLaneCenterMigration(OpenpilotTestCase):
  """Blendful's declared default (off) is already on disk; the migration turns it on once."""

  def test_turns_on_the_materialized_default(self):
    params = Params()
    params.put_bool("Blendful", False, block=True)  # what manager_init wrote
    run_migration_zp(params)
    assert params.get_bool("Blendful")
    assert params.get_bool(LANE_CENTER_MIGRATED)
    assert not params.get_bool("BlendfulReadout")

  def test_runs_once(self):
    params = Params()
    run_migration_zp(params)
    params.put_bool("Blendful", False, block=True)  # the driver turns it off
    run_migration_zp(params)
    assert not params.get_bool("Blendful")


class TestSpeedLimitSourceFold(OpenpilotTestCase):
  """Map-first (the old default, already on disk) and combined become Auto; car and map stand."""

  def test_folds_map_first_and_combined(self):
    params = Params()
    for old in (Policy.map_data_priority, Policy.combined):
      params.put("SpeedLimitPolicy", int(old), block=True)
      run_migration_zp(params)
      assert params.get("SpeedLimitPolicy") == AUTO

  def test_keeps_car_and_map_only(self):
    params = Params()
    for kept in (Policy.car_state_only, Policy.map_data_only, AUTO):
      params.put("SpeedLimitPolicy", int(kept), block=True)
      run_migration_zp(params)
      assert params.get("SpeedLimitPolicy") == kept
