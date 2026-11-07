"""Tests for param_changes_service."""
import unittest
import tempfile
import os

# Set temp state dir before importing the module
_temp_dir = tempfile.mkdtemp()
os.environ["CARROT_SETTINGS_STATE_DIR"] = _temp_dir

from webui.server.bridge.param_changes_service import (
  append_param_change,
  count_changes_since,
  get_settings_fingerprint,
  note_known_value,
  param_fingerprint,
  read_fingerprint_baseline,
  read_param_changes,
  verify_param_changes,
  write_fingerprint_baseline,
  PARAM_CHANGES_PATH,
  FINGERPRINT_BASELINE_PATH,
)
import webui.server.bridge.param_changes_service as svc


class TestParamFingerprint(unittest.TestCase):
  def test_fingerprint_deterministic(self):
    values1 = {"A": "1", "B": "2"}
    values2 = {"B": "2", "A": "1"}  # same content, different order
    fp1 = param_fingerprint(values1)
    fp2 = param_fingerprint(values2)
    self.assertEqual(fp1["fingerprint"], fp2["fingerprint"])
    self.assertEqual(fp1["count"], 2)
    self.assertNotEqual(fp1["fingerprint"], "")

  def test_different_values_different_fingerprint(self):
    fp1 = param_fingerprint({"Key": "value1"})
    fp2 = param_fingerprint({"Key": "value2"})
    self.assertNotEqual(fp1["fingerprint"], fp2["fingerprint"])

  def test_fingerprint_baseline_roundtrip(self):
    original = write_fingerprint_baseline("abcd1234")
    self.assertEqual(original["fingerprint"], "abcd1234")
    loaded = read_fingerprint_baseline()
    self.assertIsNotNone(loaded)
    self.assertEqual(loaded["fingerprint"], "abcd1234")
    self.assertIn("ts", loaded)


class TestParamChanges(unittest.TestCase):
  def setUp(self):
    # Reset known_values for clean test isolation
    svc._known_values.clear()

  def test_append_and_read(self):
    rec = append_param_change("TestKey", "old_val", "new_val", source="profile")
    self.assertIsNotNone(rec)
    self.assertEqual(rec["name"], "TestKey")
    self.assertEqual(rec["prev"], "old_val")
    self.assertEqual(rec["next"], "new_val")
    self.assertEqual(rec["source"], "profile")
    self.assertIn("hash", rec)
    self.assertIn("ts", rec)

    changes = read_param_changes()
    self.assertGreaterEqual(len(changes), 1)

  def test_verify_clean_chain(self):
    append_param_change("K1", "a", "b", source="profile")
    append_param_change("K2", "c", "d", source="profile")
    result = verify_param_changes()
    self.assertTrue(result["valid"])
    self.assertTrue(result["ok"])
    self.assertGreater(result["checked"], 0)
    self.assertIsNone(result["broken_at"])

  def test_filter_by_name(self):
    append_param_change("TargetKey", "1", "2", source="profile")
    append_param_change("OtherKey", "3", "4", source="profile")
    changes = read_param_changes(name="TargetKey")
    for c in changes:
      self.assertEqual(c["name"], "TargetKey")

  def test_filter_by_source(self):
    append_param_change("K", "a", "b", source="profile")
    append_param_change("K", "b", "c", source="web_ui")
    changes = read_param_changes(source="profile")
    for c in changes:
      self.assertEqual(c["source"], "profile")

  def test_observe_drift_detects_change(self):
    svc._known_values.clear()
    note_known_value("DriftKey", "initial")
    count = svc.observe_param_values({"DriftKey": "changed_by_device"}, allowed={"DriftKey"})
    self.assertEqual(count, 1)

  def test_observe_no_drift(self):
    svc._known_values.clear()
    note_known_value("StableKey", "value")
    count = svc.observe_param_values({"StableKey": "value"}, allowed={"StableKey"})
    self.assertEqual(count, 0)

  def test_empty_read(self):
    changes = read_param_changes(limit=10)
    self.assertIsInstance(changes, list)


if __name__ == "__main__":
  unittest.main(verbosity=2)
