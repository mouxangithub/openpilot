"""Tests for the mode state skeleton."""
import unittest

from openpilot.sunnypilot.common.mode_state import (
  MODE_CONFIRMED_PARAM,
  MODE_ON_PARAM,
  STATUS_CURVATURE,
  STATUS_LEAD,
  STATUS_OFF,
  STATUS_USER_DISABLED,
  STATUS_USER_ENABLED,
  is_manual_status,
  lock_reason,
  normalize_persisted_status,
  plan_matches_store,
  requested_mode_active,
  road_state_known,
  selected_mode,
  write_plan,
)
from openpilot.sunnypilot.common.mode_state_runtime import (
  ModeStateError,
  experimental_mode_requested,
  set_experimental_mode,
  snapshot,
)


class FakeParams:
  """A Params stand-in with the real signatures."""

  def __init__(self, values: dict | None = None, *, fail_put: tuple = ()):
    self.values = dict(values or {})
    self.fail_put = set(fail_put)

  def get_bool(self, key: str, block: bool = False) -> bool:
    return self.values.get(key) == "1"

  def get(self, key: str, block: bool = False, return_default: bool = False):
    return self.values.get(key)

  def put(self, key: str, value, block: bool = False) -> None:
    if key in self.fail_put:
      raise OSError("store refused")
    self.values[key] = "1" if value else "0"


def onroad_params(values: dict | None = None, *, fail_put: tuple = ()) -> FakeParams:
  return FakeParams({"IsOnroad": "0", "IsOffroad": "1", **(values or {})}, fail_put=fail_put)


class TestStatuses(unittest.TestCase):
  def test_only_manual_statuses_persist(self):
    # A scenario status ("there was a lead") must never survive a restart.
    self.assertEqual(normalize_persisted_status(STATUS_LEAD), STATUS_OFF)
    self.assertEqual(normalize_persisted_status(STATUS_CURVATURE), STATUS_OFF)

  def test_manual_statuses_pass_through(self):
    for status in (STATUS_OFF, STATUS_USER_DISABLED, STATUS_USER_ENABLED):
      self.assertEqual(normalize_persisted_status(status), status)

  def test_manual_membership(self):
    self.assertTrue(is_manual_status(STATUS_USER_ENABLED))
    self.assertFalse(is_manual_status(STATUS_LEAD))


class TestLockReason(unittest.TestCase):
  def test_an_unknown_road_state_locks(self):
    self.assertTrue(lock_reason(is_onroad=None, is_offroad=None, safe_mode=False, capable=True))
    self.assertTrue(lock_reason(is_onroad=True, is_offroad=True, safe_mode=False, capable=True))

  def test_safe_mode_locks(self):
    self.assertTrue(lock_reason(is_onroad=False, is_offroad=True, safe_mode=True, capable=True))

  def test_no_openpilot_long_locks(self):
    self.assertTrue(lock_reason(is_onroad=False, is_offroad=True, safe_mode=False, capable=False))

  def test_an_unknown_capability_does_not_lock(self):
    # A companion app that cannot read CarParams must still be able to toggle.
    self.assertEqual(lock_reason(is_onroad=False, is_offroad=True, safe_mode=False, capable=None), "")

  def test_offroad_and_capable_unlocks(self):
    self.assertEqual(lock_reason(is_onroad=False, is_offroad=True, safe_mode=False, capable=True), "")


class TestWritePlan(unittest.TestCase):
  def test_enabling_without_confirmation_is_refused(self):
    self.assertIsNone(write_plan(True, confirmed=False, acknowledged=False))

  def test_enabling_with_an_existing_confirmation_is_one_write(self):
    self.assertEqual(write_plan(True, confirmed=True, acknowledged=False),
                     ((MODE_ON_PARAM, True),))

  def test_enabling_with_acknowledgement_confirms_first(self):
    self.assertEqual(write_plan(True, confirmed=False, acknowledged=True),
                     ((MODE_CONFIRMED_PARAM, True), (MODE_ON_PARAM, True)))

  def test_disabling_never_touches_the_confirmation(self):
    self.assertEqual(write_plan(False, confirmed=True, acknowledged=False),
                     ((MODE_ON_PARAM, False),))


class TestSnapshotAndSet(unittest.TestCase):
  def test_snapshot_reports_the_stored_mode(self):
    self.assertEqual(snapshot(onroad_params())["mode"], "chill")
    self.assertEqual(snapshot(onroad_params({MODE_ON_PARAM: "1"}))["mode"], "experimental")
    self.assertEqual(selected_mode(True), "experimental")

  def test_snapshot_locks_on_safe_mode(self):
    snap = snapshot(onroad_params({"SafeMode": "1"}))
    self.assertTrue(snap["locked"])
    self.assertIn("Safe Mode", snap["reason"])

  def test_set_refused_while_locked(self):
    params = onroad_params({"SafeMode": "1"})
    with self.assertRaises(ModeStateError) as ctx:
      set_experimental_mode(params, True, acknowledged=True)
    self.assertEqual(ctx.exception.status, 403)

  def test_set_requires_acknowledgement(self):
    params = onroad_params()
    with self.assertRaises(ModeStateError) as ctx:
      set_experimental_mode(params, True)
    self.assertEqual(ctx.exception.status, 403)
    # The store is untouched.
    self.assertNotIn(MODE_ON_PARAM, params.values)

  def test_set_with_acknowledgement_confirms_and_enables(self):
    params = onroad_params()
    snap = set_experimental_mode(params, True, acknowledged=True)
    self.assertEqual(snap["mode"], "experimental")
    self.assertEqual(params.values[MODE_CONFIRMED_PARAM], "1")
    self.assertEqual(params.values[MODE_ON_PARAM], "1")

  def test_set_with_a_stale_expected_is_refused(self):
    params = onroad_params({MODE_ON_PARAM: "0", MODE_CONFIRMED_PARAM: "1"})
    stale = {MODE_ON_PARAM: False, MODE_CONFIRMED_PARAM: True}
    # Someone else flips the mode between the caller's snapshot and now.
    params.values[MODE_ON_PARAM] = "1"
    with self.assertRaises(ModeStateError) as ctx:
      set_experimental_mode(params, False, expected=stale)
    self.assertEqual(ctx.exception.status, 409)

  def test_set_with_a_matching_expected_succeeds(self):
    params = onroad_params({MODE_ON_PARAM: "1", MODE_CONFIRMED_PARAM: "1"})
    expected = {MODE_ON_PARAM: True, MODE_CONFIRMED_PARAM: True}
    snap = set_experimental_mode(params, False, expected=expected)
    self.assertEqual(snap["mode"], "chill")

  def test_a_failed_write_is_an_error_not_success(self):
    params = onroad_params(fail_put=(MODE_ON_PARAM,))
    with self.assertRaises(ModeStateError) as ctx:
      set_experimental_mode(params, True, acknowledged=True)
    self.assertEqual(ctx.exception.status, 500)
    # The confirmation was written, the mode was not: the caller must see
    # the failure, not a snapshot that lies about half a plan.
    self.assertEqual(ctx.exception.args[0], "Longitudinal mode update failed on ExperimentalMode.")

  def test_disabling_keeps_the_confirmation_bit(self):
    params = onroad_params({MODE_ON_PARAM: "1", MODE_CONFIRMED_PARAM: "1"})
    set_experimental_mode(params, False)
    self.assertEqual(params.values[MODE_CONFIRMED_PARAM], "1")
    self.assertEqual(params.values[MODE_ON_PARAM], "0")


class TestVerify(unittest.TestCase):
  def test_verification_reads_the_store_back(self):
    params = onroad_params()
    self.assertFalse(plan_matches_store(((MODE_ON_PARAM, True),), params.get_bool))
    params.values[MODE_ON_PARAM] = "1"
    self.assertTrue(plan_matches_store(((MODE_ON_PARAM, True),), params.get_bool))

  def test_verification_survives_a_raising_reader(self):
    def broken(_key):
      raise OSError("gone")
    self.assertFalse(plan_matches_store(((MODE_ON_PARAM, True),), broken))


class TestRoadState(unittest.TestCase):
  def test_known_states(self):
    self.assertTrue(road_state_known(True, False))
    self.assertTrue(road_state_known(False, True))

  def test_unknown_states(self):
    self.assertFalse(road_state_known(None, None))
    self.assertFalse(road_state_known(True, True))


class TestRequestedMode(unittest.TestCase):
  """The switch and its confirmation bit, read as one thing."""

  def test_the_switch_alone_is_not_a_request_when_the_bit_says_no(self):
    self.assertFalse(requested_mode_active(True, False))

  def test_an_acknowledged_switch_is_a_request(self):
    self.assertTrue(requested_mode_active(True, True))

  def test_an_off_switch_is_never_a_request(self):
    self.assertFalse(requested_mode_active(False, True))
    self.assertFalse(requested_mode_active(False, None))

  def test_a_car_without_the_bit_is_grandfathered(self):
    # The bit exists to stop a new enable from skipping the dialog; it must
    # not switch off a car that has been driving the mode since before it.
    self.assertTrue(requested_mode_active(True, None))

  def test_a_runtime_read_of_the_switch_uses_the_bit(self):
    self.assertFalse(experimental_mode_requested(FakeParams({"ExperimentalMode": "1",
                                                            "ExperimentalModeConfirmed": "0"})))
    self.assertTrue(experimental_mode_requested(FakeParams({"ExperimentalMode": "1",
                                                            "ExperimentalModeConfirmed": "1"})))
    self.assertFalse(experimental_mode_requested(FakeParams({"ExperimentalMode": "0",
                                                             "ExperimentalModeConfirmed": "1"})))

  def test_a_runtime_read_grandfathers_a_missing_bit(self):
    self.assertTrue(experimental_mode_requested(FakeParams({"ExperimentalMode": "1"})))

  def test_a_runtime_read_survives_a_store_that_raises(self):
    class Broken:
      def get_bool(self, key, block=False):
        return True

      def get(self, key, block=False, return_default=False):
        raise OSError("gone")

    # The switch says on and the bit cannot be read: the honest answer is the
    # grandfathered one, which is also what the store said before the bit.
    self.assertTrue(experimental_mode_requested(Broken()))


if __name__ == "__main__":
  unittest.main()
