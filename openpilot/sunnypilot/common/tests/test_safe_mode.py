import json
import unittest

from openpilot.sunnypilot.common.safe_mode import (
  SAFE_MODE_MANAGED_KEYS,
  SAFE_MODE_REMOVE_KEYS,
  UNKNOWN_STOCK,
  backup_entry,
  can_enter,
  can_restore,
  load_backup,
  missing_backup_keys,
  restore_plan,
  safe_value,
  serialize_backup,
  transition_block_reason,
)
from openpilot.sunnypilot.common.safe_mode_runtime import (
  SafeModeError,
  apply_safe_mode,
  backup_document,
  enforce_safe_mode,
  is_safe_mode,
  restore_safe_mode,
  safe_mode_status,
  set_safe_mode,
)


class UnknownKeyName(Exception):
  """Mirrors openpilot.common.params.UnknownKeyName without importing it."""


class _Kind:
  """Stands in for ParamKeyType, which carries its own name."""

  def __init__(self, name: str):
    self.name = name


# The registered types of the keys these tests touch, copied from params_keys.h.
# Spelled out for the same reason the real store has them: put() refuses a
# value whose type does not match, and a fake that accepts anything hides
# exactly the bug this table prevents. It did: a backup written as a str into
# a JSON key failed silently on the device and the fake never noticed.
KEY_TYPES = {
  "ExperimentalMode": "BOOL",
  "ExperimentalModeConfirmed": "BOOL",
  "LongitudinalPersonality": "INT",
  "ForceAutoTune": "BOOL",
  "ForceAutoTuneOff": "BOOL",
  "SteerRatio": "FLOAT",
  "SteerDelay": "FLOAT",
  "SteerFriction": "FLOAT",
  "SteerKP": "FLOAT",
  "SteerLatAccel": "FLOAT",
  "UseAutoSteerDelay": "BOOL",
  "CustomSR": "INT",
  "LaneCenteringEnabled": "BOOL",
  "LaneCenterOffset": "FLOAT",
  "LaneCenteringE2EAuthority": "BOOL",
  "NNFFMode": "INT",
  "FlmRuntimeOverridesEnabled": "BOOL",
  "LongitudinalFollowingProfileEnabled": "BOOL",
  "WeatherOffsetsEnabled": "BOOL",
  "VisionSpeedLimitEnabled": "BOOL",
  "VisionSpeedLimitLowLimitFilter": "BOOL",
  "LeadDuplicateGuardEnabled": "BOOL",
  "ModelLeadTrajectoryEnabled": "BOOL",
  "CscCurvatureLearningEnabled": "BOOL",
  "SafeMode": "BOOL",
  "SafeModeBackup": "JSON",
  "IsOnroad": "BOOL",
  "IsOffroad": "BOOL",
}


def _matches(kind: str, value) -> bool:
  if kind == "BOOL":
    return isinstance(value, bool)
  if kind == "INT":
    return isinstance(value, int) and not isinstance(value, bool)
  if kind == "FLOAT":
    return isinstance(value, float)
  if kind == "JSON":
    return isinstance(value, dict)
  if kind == "STRING":
    return isinstance(value, str)
  return False


class FakeParams:
  """A Params stand-in with the real signatures and the real type checks.

  ``drop_writes`` models a store that accepts a write and does not keep it,
  which is the failure the read-back in ``set_safe_mode`` exists to catch.
  ``fail_remove`` models a store that refuses a delete.
  """

  def __init__(self, values: dict | None = None, *, stock: dict | None = None,
               unknown: tuple = (), onroad: bool = False, offroad: bool = True,
               drop_writes: tuple = (), fail_remove: tuple = ()):
    self.values = dict(values or {})
    self.stock = dict(stock or {})
    self.unknown = set(unknown)
    self.drop_writes = set(drop_writes)
    self.fail_remove = set(fail_remove)
    self.values["IsOnroad"] = "1" if onroad else "0"
    self.values["IsOffroad"] = "1" if offroad else "0"

  def _check(self, key: str) -> None:
    if key in self.unknown:
      raise UnknownKeyName(key)

  def get(self, key: str, block: bool = False, return_default: bool = False):
    self._check(key)
    raw = self.values.get(key)
    if raw is None:
      return None
    # The real store decodes to Python values; a fake that hands back the raw
    # text hides every caller that forgets to convert. That is how a JSON
    # backup read back as str(dict) and quietly counted as absent.
    kind = KEY_TYPES.get(key)
    if kind == "BOOL":
      return raw == "1"
    if kind == "INT":
      return int(raw)
    if kind == "FLOAT":
      return float(raw)
    if kind == "JSON":
      return json.loads(raw)
    return raw

  def get_bool(self, key: str, block: bool = False) -> bool:
    self._check(key)
    return self.values.get(key) == "1"

  def get_stock_value(self, key: str):
    self._check(key)
    return self.stock.get(key)

  def get_type(self, key: str) -> _Kind:
    self._check(key)
    kind = KEY_TYPES.get(key)
    if kind is None:
      raise UnknownKeyName(key)
    return _Kind(kind)

  def put(self, key: str, value, block: bool = False) -> None:
    self._check(key)
    if key in self.drop_writes:
      return
    kind = self.get_type(key).name
    if not _matches(kind, value):
      raise TypeError(f"Type mismatch while writing param {key}: {type(value)} for {kind}")
    if kind == "JSON":
      self.values[key] = json.dumps(value, separators=(",", ":"), sort_keys=True)
    elif kind == "BOOL":
      self.values[key] = "1" if value else "0"
    else:
      self.values[key] = str(value)

  def put_bool(self, key: str, dat: bool, block: bool = False) -> None:
    self._check(key)
    if key in self.drop_writes:
      return
    self.values[key] = "1" if dat else "0"

  def remove(self, key: str) -> None:
    self._check(key)
    if key in self.fail_remove:
      raise OSError(f"cannot remove {key}")
    self.values.pop(key, None)



class TestSafeValue(unittest.TestCase):
  def test_a_fixed_value_wins(self):
    self.assertEqual(safe_value("ExperimentalMode", current="1", stock="9", default="0"), "0")

  def test_the_stock_value_is_used_when_there_is_no_fixed_one(self):
    self.assertEqual(safe_value("SteerRatio", current="16.8", stock="15.5", default="0.0"), "15.5")

  def test_an_unknown_stock_value_is_not_written(self):
    # 0.0 means "not known"; writing it would set the ratio to zero.
    self.assertIsNone(safe_value("SteerRatio", current="16.8", stock=UNKNOWN_STOCK, default=None))

  def test_the_default_is_the_last_resort(self):
    self.assertEqual(safe_value("SteerRatio", current="16.8", stock=None, default="14.0"), "14.0")

  def test_nothing_known_means_leave_it_alone(self):
    self.assertIsNone(safe_value("SteerRatio", current="16.8", stock=None, default=None))

  def test_the_managed_keys_are_all_registered_elsewhere(self):
    # Safe Mode must not name a key this fork does not ship: a read of an
    # unregistered key raises, and the whitelist is read every cycle.
    for key in SAFE_MODE_MANAGED_KEYS:
      self.assertIsInstance(key, str)
      self.assertTrue(key)
    # A whitelist covering everything would defeat the purpose.
    self.assertLess(len(SAFE_MODE_MANAGED_KEYS), 40)

  def test_every_removed_key_is_managed(self):
    # The runtime only backs up managed keys; a removal outside the managed
    # set would restore from nothing.
    for key in SAFE_MODE_REMOVE_KEYS:
      self.assertIn(key, SAFE_MODE_MANAGED_KEYS)


class TestCanRestore(unittest.TestCase):
  def test_only_when_parked(self):
    self.assertTrue(can_restore(is_onroad=False, is_offroad=True))

  def test_refused_while_moving(self):
    self.assertFalse(can_restore(is_onroad=True, is_offroad=False))

  def test_refused_when_the_flags_contradict(self):
    self.assertFalse(can_restore(is_onroad=True, is_offroad=True))

  def test_refused_when_the_state_is_unknown(self):
    self.assertFalse(can_restore(is_onroad=False, is_offroad=False))


class TestBackupDocument(unittest.TestCase):
  def test_round_trip(self):
    backup = {"SteerRatio": backup_entry(True, "16.8"), "SteerFriction": backup_entry(False, None)}
    self.assertEqual(load_backup(serialize_backup(backup)), backup)

  def test_garbage_loads_as_empty(self):
    self.assertEqual(load_backup(None), {})
    self.assertEqual(load_backup(""), {})
    self.assertEqual(load_backup("not json"), {})
    self.assertEqual(load_backup("[1,2]"), {})

  def test_a_malformed_entry_is_skipped(self):
    self.assertEqual(load_backup('{"A": "not a dict"}'), {})

  def test_missing_keys_are_reported(self):
    backup = {"SteerRatio": backup_entry(True, "16.8")}
    missing = missing_backup_keys(backup, ("SteerRatio", "SteerFriction"))
    self.assertEqual(missing, ["SteerFriction"])

  def test_the_restore_plan_covers_managed_keys_then_extras(self):
    backup = {"Extra": backup_entry(True, "x"), "SteerRatio": backup_entry(True, "16.8")}
    plan = dict(restore_plan(backup, ("SteerRatio",)))
    self.assertEqual(plan["SteerRatio"], "16.8")
    self.assertEqual(plan["Extra"], "x")

  def test_a_key_that_was_absent_is_removed(self):
    backup = {"SteerRatio": backup_entry(False, None)}
    plan = dict(restore_plan(backup, ("SteerRatio",)))
    self.assertIsNone(plan["SteerRatio"])


class TestApplyAndRestore(unittest.TestCase):
  def test_applying_forces_the_fixed_values(self):
    params = FakeParams({"ExperimentalMode": "1", "NNFFMode": "2", "LaneCenteringEnabled": "1"})
    self.assertTrue(apply_safe_mode(params))
    self.assertEqual(params.values["ExperimentalMode"], "0")
    self.assertEqual(params.values["NNFFMode"], "0")
    self.assertEqual(params.values["LaneCenteringEnabled"], "0")

  def test_applying_records_the_original_values(self):
    params = FakeParams({"ExperimentalMode": "1", "NNFFMode": "2"})
    apply_safe_mode(params)
    backup = backup_document(params)
    self.assertEqual(backup["ExperimentalMode"], {"present": True, "value": "1"})
    self.assertEqual(backup["NNFFMode"], {"present": True, "value": "2"})

  def test_a_second_apply_does_not_overwrite_the_backup(self):
    params = FakeParams({"ExperimentalMode": "1"})
    apply_safe_mode(params)
    apply_safe_mode(params, ensure_backup=False)
    backup = backup_document(params)
    # The backup still holds the user's value, not the forced one.
    self.assertEqual(backup["ExperimentalMode"]["value"], "1")

  def test_an_unset_key_is_recorded_as_absent(self):
    params = FakeParams({"ExperimentalMode": "1"})
    apply_safe_mode(params)
    backup = backup_document(params)
    self.assertFalse(backup["SteerFriction"]["present"])

  def test_a_key_the_store_does_not_know_is_left_alone(self):
    # A device whose parameter library predates the key must not crash.
    params = FakeParams({"ExperimentalMode": "1"}, unknown=("NNFFMode",))
    self.assertTrue(apply_safe_mode(params))
    self.assertEqual(params.values["ExperimentalMode"], "0")

  def test_the_steer_knobs_are_removed_not_written(self):
    # These knobs are "0.0 means not set" parameters; writing 0.0 would be
    # read back as a present-but-invalid value, so they are removed.
    params = FakeParams({"SteerRatio": "16.8", "SteerFriction": "0.3"})
    self.assertTrue(apply_safe_mode(params))
    self.assertNotIn("SteerRatio", params.values)
    self.assertNotIn("SteerFriction", params.values)
    # And the originals are in the backup.
    backup = backup_document(params)
    self.assertEqual(backup["SteerRatio"], {"present": True, "value": "16.8"})
    self.assertEqual(backup["SteerFriction"], {"present": True, "value": "0.3"})

  def test_a_removed_knob_restores_to_its_original_value(self):
    params = FakeParams({"SteerRatio": "16.8"})
    apply_safe_mode(params)
    self.assertTrue(restore_safe_mode(params))
    self.assertEqual(params.values["SteerRatio"], "16.8")

  def test_the_enforcer_reapplies_the_removal(self):
    params = FakeParams({"SafeMode": "1", "SteerRatio": "16.8"})
    apply_safe_mode(params)
    # Someone (a learner process) writes the ratio back mid-drive.
    params.values["SteerRatio"] = "17.2"
    self.assertTrue(enforce_safe_mode(params, 20))
    self.assertNotIn("SteerRatio", params.values)

  def test_restore_puts_the_values_back(self):
    params = FakeParams({"ExperimentalMode": "1", "NNFFMode": "2"})
    apply_safe_mode(params)
    self.assertTrue(restore_safe_mode(params))
    self.assertEqual(params.values["ExperimentalMode"], "1")
    self.assertEqual(params.values["NNFFMode"], "2")

  def test_restore_removes_a_key_that_was_absent(self):
    params = FakeParams({"ExperimentalMode": "1"})
    apply_safe_mode(params)
    # SteerFriction was absent, so restoring removes whatever Safe Mode wrote
    params.values["SteerFriction"] = "0.3"
    restore_safe_mode(params)
    self.assertNotIn("SteerFriction", params.values)

  def test_restore_is_refused_while_moving(self):
    params = FakeParams({"ExperimentalMode": "1"}, onroad=True, offroad=False)
    apply_safe_mode(params)
    self.assertFalse(restore_safe_mode(params))
    # The forced value is still in place.
    self.assertEqual(params.values["ExperimentalMode"], "0")

  def test_restore_clears_the_backup(self):
    params = FakeParams({"ExperimentalMode": "1"})
    apply_safe_mode(params)
    restore_safe_mode(params)
    self.assertEqual(backup_document(params), {})

  def test_restore_without_a_backup_is_harmless(self):
    params = FakeParams({"ExperimentalMode": "1"})
    self.assertFalse(restore_safe_mode(params))

  def test_the_enforcer_only_runs_when_safe_mode_is_on(self):
    params = FakeParams({"SafeMode": "0", "ExperimentalMode": "1"})
    self.assertFalse(enforce_safe_mode(params, 0))
    self.assertEqual(params.values["ExperimentalMode"], "1")

  def test_the_enforcer_reapplies_on_its_cadence(self):
    params = FakeParams({"SafeMode": "1", "ExperimentalMode": "1"})
    apply_safe_mode(params)
    # Someone writes the user value back while Safe Mode is on.
    params.values["ExperimentalMode"] = "1"
    self.assertFalse(enforce_safe_mode(params, 1))
    self.assertEqual(params.values["ExperimentalMode"], "1")
    # On the cadence it is forced back.
    self.assertTrue(enforce_safe_mode(params, 20))
    self.assertEqual(params.values["ExperimentalMode"], "0")

  def test_is_safe_mode_reads_the_switch(self):
    self.assertTrue(is_safe_mode(FakeParams({"SafeMode": "1"})))
    self.assertFalse(is_safe_mode(FakeParams({"SafeMode": "0"})))
    self.assertFalse(is_safe_mode(FakeParams({})))

  def test_is_safe_mode_survives_an_unknown_key(self):
    self.assertFalse(is_safe_mode(FakeParams({}, unknown=("SafeMode",))))


class TestEnterGate(unittest.TestCase):
  """The parked prerequisite, tested separately from the store plumbing."""

  def test_entering_is_allowed_when_the_car_is_known_to_be_parked(self):
    self.assertTrue(can_enter(False))

  def test_entering_is_refused_while_moving(self):
    self.assertFalse(can_enter(True))

  def test_an_unknown_road_state_does_not_authorise_entering(self):
    self.assertFalse(can_enter(None))

  def test_the_reason_names_the_parked_rule(self):
    self.assertIn("park", transition_block_reason(False, True, False))
    self.assertIsNone(transition_block_reason(False, False, True))

  def test_an_unknown_road_state_blocks_both_directions(self):
    self.assertIn("unknown", transition_block_reason(False, None, None))
    self.assertIn("unknown", transition_block_reason(True, None, None))


class TestSetSafeMode(unittest.TestCase):
  """The transition itself: backup, force, flag, read-back."""

  def test_entering_forces_the_knobs_and_sets_the_flag(self):
    params = FakeParams({"ExperimentalMode": "1", "NNFFMode": "2", "SteerRatio": "16.8"})
    status = set_safe_mode(params, True)

    self.assertTrue(status["active"])
    self.assertTrue(is_safe_mode(params))
    self.assertEqual(params.values["ExperimentalMode"], "0")
    self.assertEqual(params.values["NNFFMode"], "0")
    # A "0.0 means not set" knob is removed, never written.
    self.assertNotIn("SteerRatio", params.values)
    self.assertGreater(status["backupKeys"], 0)

  def test_entering_while_moving_is_refused_and_changes_nothing(self):
    params = FakeParams({"ExperimentalMode": "1"}, onroad=True, offroad=False)
    with self.assertRaises(SafeModeError) as caught:
      set_safe_mode(params, True)

    self.assertEqual(caught.exception.status, 403)
    self.assertFalse(is_safe_mode(params))
    self.assertEqual(params.values["ExperimentalMode"], "1")

  def test_entering_twice_is_a_no_op(self):
    params = FakeParams({"NNFFMode": "2"})
    set_safe_mode(params, True)
    backup = params.values["SafeModeBackup"]
    status = set_safe_mode(params, True)

    self.assertTrue(status["active"])
    # The second call must not overwrite the record with the forced values.
    self.assertEqual(params.values["SafeModeBackup"], backup)

  def test_leaving_puts_the_original_values_back(self):
    params = FakeParams({"ExperimentalMode": "1", "NNFFMode": "2", "SteerRatio": "16.8"})
    set_safe_mode(params, True)
    status = set_safe_mode(params, False)

    self.assertFalse(status["active"])
    self.assertFalse(is_safe_mode(params))
    self.assertEqual(params.values["ExperimentalMode"], "1")
    self.assertEqual(params.values["NNFFMode"], "2")
    self.assertEqual(params.values["SteerRatio"], "16.8")
    self.assertNotIn("SafeModeBackup", params.values)

  def test_leaving_is_refused_while_moving(self):
    params = FakeParams({"NNFFMode": "2"})
    set_safe_mode(params, True)
    params.values["IsOnroad"] = "1"
    params.values["IsOffroad"] = "0"

    with self.assertRaises(SafeModeError) as caught:
      set_safe_mode(params, False)

    self.assertEqual(caught.exception.status, 403)
    self.assertTrue(is_safe_mode(params))
    self.assertEqual(params.values["NNFFMode"], "0")

  def test_a_flag_that_does_not_stick_is_reported(self):
    params = FakeParams({"NNFFMode": "2"}, drop_writes=("SafeMode",))
    with self.assertRaises(SafeModeError) as caught:
      set_safe_mode(params, True)

    self.assertEqual(caught.exception.status, 500)
    self.assertIn("read back", str(caught.exception))

  def test_a_backup_that_cannot_be_cleared_keeps_safe_mode_on(self):
    # Clearing the flag here would strand the forced values with no record
    # of what they used to be, so the refusal has to keep the flag.
    params = FakeParams({"NNFFMode": "2"})
    set_safe_mode(params, True)
    params.fail_remove.add("SafeModeBackup")

    with self.assertRaises(SafeModeError) as caught:
      set_safe_mode(params, False)

    self.assertEqual(caught.exception.status, 500)
    self.assertTrue(is_safe_mode(params))

  def test_a_store_that_refuses_the_backup_forces_nothing(self):
    """The device bug this regression is named after.

    The backup document was written as a str into a JSON key. The store
    refused it, the refusal was swallowed, and the only write that survived
    was the steer-knob removal - a destructive change with nothing left to
    restore from. Nothing may be forced before the record exists.
    """

    class NoJson(FakeParams):
      def put(self, key: str, value, block: bool = False) -> None:
        if self.get_type(key).name == "JSON":
          raise TypeError("this store refuses json")
        super().put(key, value, block)

    params = NoJson({"NNFFMode": "2", "SteerRatio": "16.8"})
    with self.assertRaises(SafeModeError) as caught:
      set_safe_mode(params, True)

    self.assertEqual(caught.exception.status, 500)
    self.assertFalse(is_safe_mode(params))
    self.assertEqual(params.values["NNFFMode"], "2")
    self.assertEqual(params.values["SteerRatio"], "16.8")

  def test_status_explains_a_refusal_without_raising(self):
    parked = safe_mode_status(FakeParams({}), is_onroad=False, is_offroad=True)
    moving = safe_mode_status(FakeParams({}), is_onroad=True, is_offroad=False)

    self.assertTrue(parked["canEnter"])
    self.assertIsNone(parked["reason"])
    self.assertFalse(moving["canEnter"])
    self.assertIn("park", moving["reason"])

  def test_status_of_an_active_mode_offers_the_restore(self):
    params = FakeParams({"NNFFMode": "2"})
    set_safe_mode(params, True)
    status = safe_mode_status(params, is_onroad=False, is_offroad=True)

    self.assertTrue(status["active"])
    self.assertFalse(status["canEnter"])
    self.assertTrue(status["canRestore"])
    self.assertIsNone(status["reason"])


if __name__ == "__main__":
  unittest.main()
