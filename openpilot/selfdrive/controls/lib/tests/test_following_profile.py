import json
import unittest

from openpilot.selfdrive.controls.lib.following_profile import (
  DEFAULT_T_FOLLOW,
  FOLLOWING_CURVE_MAX,
  FOLLOWING_CURVE_MIN,
  FOLLOWING_PRESET_CURVES,
  FOLLOWING_SPEEDS_MPH,
  load_profile_document,
  personality_key,
  serialize_profile_document,
  t_follow_for_personality,
  validate_category,
  validate_profile_document,
)


class TestValidateCategory(unittest.TestCase):
  def test_named_preset_is_accepted(self):
    entry = validate_category({"preset": "close"})
    self.assertEqual(entry["preset"], "close")
    self.assertEqual(entry["curve"], list(FOLLOWING_PRESET_CURVES["close"]))

  def test_named_preset_ignores_a_stale_curve(self):
    # A curve left over from an earlier custom edit must not override the
    # named preset.
    entry = validate_category({"preset": "close", "curve": [3.0] * 10})
    self.assertEqual(entry["curve"], list(FOLLOWING_PRESET_CURVES["close"]))

  def test_unknown_preset_is_rejected(self):
    self.assertIsNone(validate_category({"preset": "traffic"}))
    self.assertIsNone(validate_category({"preset": "nope"}))
    self.assertIsNone(validate_category({}))

  def test_custom_curve_needs_the_full_grid(self):
    self.assertIsNone(validate_category({"preset": "custom", "curve": [1.0, 1.1]}))
    entry = validate_category({"preset": "custom", "curve": [1.0] * len(FOLLOWING_SPEEDS_MPH)})
    self.assertIsNotNone(entry)

  def test_custom_curve_respects_the_bounds(self):
    too_low = [FOLLOWING_CURVE_MIN - 0.1] * len(FOLLOWING_SPEEDS_MPH)
    too_high = [FOLLOWING_CURVE_MAX + 0.1] * len(FOLLOWING_SPEEDS_MPH)
    self.assertIsNone(validate_category({"preset": "custom", "curve": too_low}))
    self.assertIsNone(validate_category({"preset": "custom", "curve": too_high}))

  def test_bool_is_not_a_number(self):
    # bool is a subclass of int in Python; a bool in a curve is always a bug.
    curve = [True] * len(FOLLOWING_SPEEDS_MPH)
    self.assertIsNone(validate_category({"preset": "custom", "curve": curve}))

  def test_nan_is_rejected(self):
    curve = [float("nan")] * len(FOLLOWING_SPEEDS_MPH)
    self.assertIsNone(validate_category({"preset": "custom", "curve": curve}))

  def test_non_dict_is_rejected(self):
    self.assertIsNone(validate_category("close"))
    self.assertIsNone(validate_category(None))


class TestValidateProfileDocument(unittest.TestCase):
  def test_empty_document_is_valid(self):
    self.assertEqual(validate_profile_document({}), {})

  def test_one_bad_entry_rejects_the_whole_document(self):
    document = {
      "aggressive": {"preset": "close"},
      "standard": {"preset": "bogus"},
    }
    self.assertIsNone(validate_profile_document(document))

  def test_unknown_keys_are_ignored(self):
    document = {"standard": {"preset": "medium"}, "traffic": {"preset": "close"}}
    validated = validate_profile_document(document)
    self.assertIsNotNone(validated)
    self.assertIn("standard", validated)
    self.assertNotIn("traffic", validated)


class TestLoadProfileDocument(unittest.TestCase):
  def test_empty_string_means_not_configured(self):
    self.assertEqual(load_profile_document(""), {})
    self.assertEqual(load_profile_document("   "), {})
    self.assertEqual(load_profile_document(None), None)

  def test_invalid_json_is_rejected(self):
    self.assertIsNone(load_profile_document("{not json"))
    self.assertIsNone(load_profile_document(b"\xff\xfe"))

  def test_json_round_trip(self):
    document = {"standard": {"preset": "medium"}}
    raw = serialize_profile_document(document)
    loaded = load_profile_document(raw)
    self.assertIsNotNone(loaded)
    self.assertEqual(loaded["standard"]["preset"], "medium")

  def test_bytes_input_is_accepted(self):
    raw = json.dumps({"standard": {"preset": "far"}}).encode("utf-8")
    loaded = load_profile_document(raw)
    self.assertIsNotNone(loaded)
    self.assertEqual(loaded["standard"]["preset"], "far")

  def test_dict_input_is_accepted(self):
    loaded = load_profile_document({"standard": {"preset": "far"}})
    self.assertIsNotNone(loaded)


class TestTFollowForPersonality(unittest.TestCase):
  def test_missing_personality_returns_none(self):
    profile = validate_profile_document({"standard": {"preset": "medium"}})
    self.assertIsNone(t_follow_for_personality(profile, "relaxed", 20.0))

  def test_named_preset_interpolates_over_speed(self):
    profile = validate_profile_document({"standard": {"preset": "medium"}})
    # The medium preset is 1.45 s at 45 mph and 1.2 s at 70 mph.
    mph = 0.44704
    at_45 = t_follow_for_personality(profile, "standard", 45.0 * mph)
    at_70 = t_follow_for_personality(profile, "standard", 70.0 * mph)
    self.assertAlmostEqual(at_45, 1.45)
    self.assertAlmostEqual(at_70, 1.2)
    # Between the breakpoints it interpolates linearly. The breakpoints are
    # 45 and 70 mph, so the midpoint is 57.5 mph.
    at_mid = t_follow_for_personality(profile, "standard", 57.5 * mph)
    self.assertAlmostEqual(at_mid, (1.45 + 1.2) / 2)

  def test_named_preset_clamps_outside_the_breakpoints(self):
    profile = validate_profile_document({"standard": {"preset": "medium"}})
    mph = 0.44704
    self.assertAlmostEqual(t_follow_for_personality(profile, "standard", 0.0), 1.45)
    self.assertAlmostEqual(t_follow_for_personality(profile, "standard", 200.0 * mph), 1.2)

  def test_custom_curve_uses_the_mph_grid(self):
    curve = [1.0 + 0.1 * i for i in range(len(FOLLOWING_SPEEDS_MPH))]
    profile = validate_profile_document({"aggressive": {"preset": "custom", "curve": curve}})
    mph = 0.44704
    self.assertAlmostEqual(t_follow_for_personality(profile, "aggressive", 0.0), 1.0)
    self.assertAlmostEqual(t_follow_for_personality(profile, "aggressive", 50.0 * mph), 1.5)
    self.assertAlmostEqual(t_follow_for_personality(profile, "aggressive", 90.0 * mph), 1.9)

  def test_non_finite_speed_returns_none(self):
    profile = validate_profile_document({"standard": {"preset": "medium"}})
    self.assertIsNone(t_follow_for_personality(profile, "standard", float("nan")))
    self.assertIsNone(t_follow_for_personality(profile, "standard", float("inf")))

  def test_bool_speed_returns_none(self):
    profile = validate_profile_document({"standard": {"preset": "medium"}})
    self.assertIsNone(t_follow_for_personality(profile, "standard", True))

  def test_no_profile_returns_none(self):
    self.assertIsNone(t_follow_for_personality(None, "standard", 20.0))


class TestPersonalityKey(unittest.TestCase):
  def test_named_personalities(self):
    self.assertEqual(personality_key("aggressive"), "aggressive")
    self.assertEqual(personality_key("standard"), "standard")
    self.assertEqual(personality_key("relaxed"), "relaxed")

  def test_unknown_is_none(self):
    self.assertIsNone(personality_key("traffic"))
    self.assertIsNone(personality_key(None))


class TestDefaults(unittest.TestCase):
  def test_defaults_match_the_stock_scalars(self):
    self.assertAlmostEqual(DEFAULT_T_FOLLOW["aggressive"], 1.25)
    self.assertAlmostEqual(DEFAULT_T_FOLLOW["standard"], 1.45)
    self.assertAlmostEqual(DEFAULT_T_FOLLOW["relaxed"], 1.75)


if __name__ == "__main__":
  unittest.main()
