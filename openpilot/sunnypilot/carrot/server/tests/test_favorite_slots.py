"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Executable favorite slots: storage shape, kind resolution and apply semantics.

Pure-logic tests: the service's dependencies (catalog, current-value reader,
writer) are injected, so no Params store, settings cache or manager is needed.
"""

import unittest

from openpilot.sunnypilot.carrot.server.services import favorite_slots as fs
from openpilot.sunnypilot.carrot.server.services.setting_favorites import (
  MAX_FAVORITE_SLOTS,
  sanitize_setting_favorites,
)


class Recorder:
  """Captures writer calls; optionally raises like set_param_value does."""

  def __init__(self, fail_with=None):
    self.calls = []
    self.fail_with = fail_with

  def __call__(self, key, value):
    self.calls.append((key, value))
    if self.fail_with is not None:
      raise ValueError(self.fail_with)


CATALOG = {
  "EnableSomething": {"name": "EnableSomething", "min": 0, "max": 1, "default": 0},
  "DMMode": {"name": "DMMode", "min": 0, "max": 1, "default": 0,
             "options": {"zh": ["基本", "实验"], "en": ["default", "experimental"]}},
  "PathOffset": {"name": "PathOffset", "min": -150, "max": 150, "default": 0, "unit": 1},
  "Gone": None,
}


class FavoriteSlotsTestBase(unittest.TestCase):
  def setUp(self):
    self._patches = {}
    self._patch(fs, "_catalog_by_name", lambda: CATALOG)
    self._patch(fs, "_read_current", lambda key, entry: self.values.get(key, entry.get("default")))
    self._assigned = ["EnableSomething", "DMMode", "PathOffset"]
    self._patch(fs, "_assigned_keys", lambda: self._assigned)
    self.values = {}

  def tearDown(self):
    for target, name, original in self._patches.values():
      setattr(target, name, original)

  def _patch(self, target, name, replacement):
    self._patches[name] = (target, name, getattr(target, name))
    setattr(target, name, replacement)


class TestStorageShape(unittest.TestCase):
  def test_slots_truncated_and_normalized(self):
    raw = {"slots": [{"key": "A"}, "garbage", None, {"key": "DroppedBeyondThree"}]}
    clean = sanitize_setting_favorites(raw)
    assert len(clean["slots"]) == MAX_FAVORITE_SLOTS  # positional: first three raw entries win
    assert clean["slots"][0] == {"key": "A"}
    assert clean["slots"][1] == {"key": ""}  # non-dict becomes an explicit empty slot
    assert clean["slots"][2] == {"key": ""}  # null stays an empty slot

  def test_legacy_favorites_file_still_sanitizes(self):
    clean = sanitize_setting_favorites({"favorites": ["A", "A", "B", ""]})
    assert clean["favorites"] == ["A", "B"]
    assert clean["slots"] == []


class TestDescribe(FavoriteSlotsTestBase):
  def test_kinds_and_live_values(self):
    self.values = {"EnableSomething": 1, "DMMode": 0}
    slots = fs.describe_favorite_slots()
    assert slots[0]["kind"] == "toggle" and slots[0]["value"] is True
    assert slots[1]["kind"] == "cycle" and slots[1]["options"] == ["基本", "实验"]
    assert slots[2]["kind"] == "value" and slots[2]["min"] == -150

  def test_stale_key_is_reported_not_dropped(self):
    self._assigned = ["Gone"]
    slots = fs.describe_favorite_slots()
    assert slots[0]["kind"] == "stale" and slots[0]["key"] == "Gone"


class TestApply(FavoriteSlotsTestBase):
  def test_toggle_flips_current(self):
    self.values = {"EnableSomething": 0}
    rec = Recorder()
    result = fs.apply_favorite_slot(slot=0, writer=rec)
    assert rec.calls == [("EnableSomething", True)]
    assert result["previous"] == 0 and result["value"] is True

  def test_toggle_explicit_value_sets_target(self):
    self.values = {"EnableSomething": 1}
    rec = Recorder()
    fs.apply_favorite_slot(slot=0, value=0, writer=rec)
    assert rec.calls == [("EnableSomething", False)]

  def test_cycle_advances_and_wraps(self):
    self.values = {"DMMode": 0}
    rec = Recorder()
    fs.apply_favorite_slot(key="DMMode", writer=rec)
    assert rec.calls == [("DMMode", 1)]
    self.values = {"DMMode": 1}
    fs.apply_favorite_slot(key="DMMode", writer=rec)
    assert rec.calls[-1] == ("DMMode", 0)

  def test_cycle_rejects_out_of_range_explicit_index(self):
    with self.assertRaises(fs.FavoriteSlotError) as ctx:
      fs.apply_favorite_slot(key="DMMode", value=5, writer=Recorder())
    assert ctx.exception.code == "out_of_range"

  def test_numeric_requires_explicit_value_and_clamps(self):
    with self.assertRaises(fs.FavoriteSlotError) as ctx:
      fs.apply_favorite_slot(slot=2, writer=Recorder())
    assert ctx.exception.code == "value_required"
    rec = Recorder()
    fs.apply_favorite_slot(slot=2, value=9999, writer=rec)
    key, value = rec.calls[0]
    assert key == "PathOffset" and value <= 150

  def test_writer_valueerror_becomes_rejected(self):
    rec = Recorder(fail_with="blocked while onroad")
    with self.assertRaises(fs.FavoriteSlotError) as ctx:
      fs.apply_favorite_slot(slot=0, writer=rec)
    assert ctx.exception.code == "rejected" and "onroad" in ctx.exception.message

  def test_key_not_assigned_is_refused(self):
    with self.assertRaises(fs.FavoriteSlotError) as ctx:
      fs.apply_favorite_slot(key="NotAssigned", writer=Recorder())
    assert ctx.exception.code == "not_a_slot"

  def test_bad_slot_index_is_refused(self):
    for bad, expected in ((3, "bad_slot"), (-1, "bad_slot"), (True, "bad_slot")):
      with self.assertRaises(fs.FavoriteSlotError) as ctx:
        fs.apply_favorite_slot(slot=bad, writer=Recorder())
      assert ctx.exception.code == expected
    with self.assertRaises(fs.FavoriteSlotError) as ctx:
      fs.apply_favorite_slot(slot=None, key=None, writer=Recorder())
    assert ctx.exception.code == "bad_request"


if __name__ == "__main__":
  unittest.main()
