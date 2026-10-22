import unittest

from openpilot.sunnypilot.common.safety_guards import (
  BLOCKED_ONROAD_KEYS,
  CommIssueGrace,
  blocked_onroad_reason,
  capability_fingerprint_is_usable,
  clear_longitudinal_excessive_actuation,
  is_mock_fingerprint,
  is_param_action_safe_onroad,
)


class TestOnroadParamGuard(unittest.TestCase):
  def test_blocked_key_is_refused_onroad(self):
    self.assertFalse(is_param_action_safe_onroad("SteerRatio", True))
    self.assertFalse(is_param_action_safe_onroad("ForceFingerprint", True))
    self.assertFalse(is_param_action_safe_onroad("ExperimentalMode", True))

  def test_blocked_key_is_allowed_offroad(self):
    self.assertTrue(is_param_action_safe_onroad("SteerRatio", False))

  def test_unlisted_key_is_always_allowed(self):
    self.assertTrue(is_param_action_safe_onroad("IsMetric", True))
    self.assertTrue(is_param_action_safe_onroad("CarrotTurnAccelEnabled", True))

  def test_the_blocklist_covers_the_dangerous_ones(self):
    for key in ("SteerRatio", "SteerFriction", "SteerLatAccel", "ForceFingerprint",
                "DisableOpenpilotLongitudinal", "SecOCKey"):
      self.assertIn(key, BLOCKED_ONROAD_KEYS)

  def test_the_blocklist_does_not_swallow_the_whole_surface(self):
    # A blocklist that covered everything would break the product.
    self.assertLess(len(BLOCKED_ONROAD_KEYS), 60)

  def test_reason_is_only_given_when_refused(self):
    self.assertIsNone(blocked_onroad_reason("IsMetric", True))
    reason = blocked_onroad_reason("SteerRatio", True)
    self.assertIsNotNone(reason)
    self.assertIn("SteerRatio", reason)

  def test_a_custom_blocklist_is_honoured(self):
    self.assertFalse(is_param_action_safe_onroad("Foo", True, blocked_keys=["Foo"]))
    self.assertTrue(is_param_action_safe_onroad("SteerRatio", True, blocked_keys=["Foo"]))


class TestCommIssueGrace(unittest.TestCase):
  def test_a_healthy_stream_never_raises(self):
    grace = CommIssueGrace()
    for _ in range(10):
      self.assertFalse(grace.update(all_checks=True, all_alive=True, all_freq_ok=True))

  def test_a_dead_publisher_is_reported_immediately(self):
    grace = CommIssueGrace()
    self.assertTrue(grace.update(all_checks=False, all_alive=False, all_freq_ok=False))

  def test_a_stale_publisher_is_reported_immediately(self):
    grace = CommIssueGrace()
    self.assertTrue(grace.update(all_checks=False, all_alive=True, all_freq_ok=False))

  def test_stale_but_present_data_gets_a_grace_period(self):
    grace = CommIssueGrace(grace_frames=3)
    self.assertFalse(grace.update(all_checks=False, all_alive=True, all_freq_ok=True))
    self.assertFalse(grace.update(all_checks=False, all_alive=True, all_freq_ok=True))
    self.assertTrue(grace.update(all_checks=False, all_alive=True, all_freq_ok=True))

  def test_a_recovery_resets_the_counter(self):
    grace = CommIssueGrace(grace_frames=3)
    grace.update(all_checks=False, all_alive=True, all_freq_ok=True)
    grace.update(all_checks=False, all_alive=True, all_freq_ok=True)
    self.assertFalse(grace.update(all_checks=True, all_alive=True, all_freq_ok=True))
    # The counter was reset, so it takes the full grace period again.
    self.assertFalse(grace.update(all_checks=False, all_alive=True, all_freq_ok=True))
    self.assertFalse(grace.update(all_checks=False, all_alive=True, all_freq_ok=True))
    self.assertTrue(grace.update(all_checks=False, all_alive=True, all_freq_ok=True))

  def test_a_dead_publisher_resets_the_counter(self):
    grace = CommIssueGrace(grace_frames=3)
    grace.update(all_checks=False, all_alive=True, all_freq_ok=True)
    self.assertTrue(grace.update(all_checks=False, all_alive=False, all_freq_ok=True))
    self.assertFalse(grace.update(all_checks=False, all_alive=True, all_freq_ok=True))


class TestExcessiveActuationCleanup(unittest.TestCase):
  def test_longitudinal_is_cleared(self):
    self.assertTrue(clear_longitudinal_excessive_actuation({"extra": "longitudinal"}))
    self.assertTrue(clear_longitudinal_excessive_actuation('{"extra": "longitudinal"}'))

  def test_lateral_is_left_alone(self):
    self.assertFalse(clear_longitudinal_excessive_actuation({"extra": "lateral"}))

  def test_an_empty_payload_is_left_alone(self):
    self.assertFalse(clear_longitudinal_excessive_actuation(None))
    self.assertFalse(clear_longitudinal_excessive_actuation(""))
    self.assertFalse(clear_longitudinal_excessive_actuation("not json"))
    self.assertFalse(clear_longitudinal_excessive_actuation(42))

  def test_bytes_are_accepted(self):
    self.assertTrue(clear_longitudinal_excessive_actuation(b'{"extra": "longitudinal"}'))


class TestCapabilityFingerprint(unittest.TestCase):
  def test_a_mock_fingerprint_is_never_usable(self):
    self.assertTrue(is_mock_fingerprint("MOCK_TOYOTA"))
    self.assertFalse(capability_fingerprint_is_usable("MOCK_TOYOTA"))

  def test_a_real_fingerprint_is_usable(self):
    self.assertFalse(is_mock_fingerprint("TOYOTA_WILDLANDER_PHEV"))
    self.assertTrue(capability_fingerprint_is_usable("TOYOTA_WILDLANDER_PHEV"))

  def test_an_empty_fingerprint_is_not_a_mock(self):
    self.assertFalse(is_mock_fingerprint(""))
    self.assertFalse(is_mock_fingerprint(None))

  def test_a_forced_fingerprint_still_rejects_a_mock(self):
    # Forcing a fingerprint does not make a mocked one real.
    self.assertFalse(capability_fingerprint_is_usable("MOCK_TOYOTA", forced=True))


if __name__ == "__main__":
  unittest.main()
