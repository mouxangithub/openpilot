"""
Copyright (c) 2026-, sunnypilot contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

Preset -> JSON round trip for the Following Profile settings: the exact document
the UI writes into LongitudinalFollowingProfile must be the exact document the
engine's validator accepts. Pure logic, no pyray - runs on a bare PC host.
"""
import json

from openpilot.selfdrive.controls.lib.following_profile import (
  FOLLOWING_PRESET_CURVES,
  FOLLOWING_PRESET_SPEEDS_MPH,
  PERSONALITY_KEYS,
  load_profile_document,
  t_follow_for_personality,
)
from openpilot.selfdrive.ui.sunnypilot.lib.following_profile_store import (
  PRESET_ORDER,
  build_document,
  default_selection,
  serialize_selection,
  selection_from_document,
  selection_from_raw,
)

MPH_TO_MS = 0.44704  # mirrors the engine's constant, for speed checks


def test_default_selection_matches_engine_defaults():
  selection = default_selection()
  assert selection == {"aggressive": "close", "standard": "medium", "relaxed": "far"}
  assert set(selection) == set(PERSONALITY_KEYS)


def test_preset_to_json_round_trip():
  # every legal combination of presets must survive serialize -> parse unchanged
  for aggressive in PRESET_ORDER:
    for standard in PRESET_ORDER:
      for relaxed in PRESET_ORDER:
        selection = {"aggressive": aggressive, "standard": standard, "relaxed": relaxed}
        raw = serialize_selection(selection)
        assert isinstance(raw, str)

        parsed = json.loads(raw)
        assert selection_from_document(parsed) == selection

        # and through the engine's own reader, as long_mpc consumes it
        document = load_profile_document(raw)
        assert document is not None
        for personality, preset in selection.items():
          assert document[personality]["preset"] == preset
          assert document[personality]["curve"] == list(FOLLOWING_PRESET_CURVES[preset])


def test_named_preset_curve_interpolates():
  # the written document must drive the engine: mid-point between the two
  # breakpoints is the mean of the two curve values
  document = load_profile_document(serialize_selection({"aggressive": "close", "standard": "medium", "relaxed": "far"}))
  for personality, entry in document.items():
    preset = entry["preset"]
    low, high = FOLLOWING_PRESET_SPEEDS_MPH[preset]
    t_low = t_follow_for_personality(document, personality, low * MPH_TO_MS)
    t_high = t_follow_for_personality(document, personality, high * MPH_TO_MS)
    t_mid = t_follow_for_personality(document, personality, (low + high) / 2 * MPH_TO_MS)
    assert t_low == FOLLOWING_PRESET_CURVES[preset][0]
    assert t_high == FOLLOWING_PRESET_CURVES[preset][1]
    assert abs(t_mid - (t_low + t_high) / 2) < 1e-9


def test_partial_document_keeps_defaults_for_missing_personalities():
  # a document with only one personality configured: the UI fills the rest
  # from the defaults, mirroring the engine's optional-per-personality read
  document = {"aggressive": {"preset": "far", "curve": [1.6, 1.4]}}
  selection = selection_from_document(document)
  assert selection["aggressive"] == "far"
  assert selection["standard"] == "medium"
  assert selection["relaxed"] == "far"


def test_malformed_raw_falls_back_to_defaults():
  for raw in (None, b"", "not json", '{"aggressive": {"preset": "bogus"}}', '["not", "a", "dict"]'):
    assert selection_from_raw(raw) == default_selection()


def test_unset_param_serializes_to_valid_empty_document():
  # before the user touches anything the store yields the defaults; writing
  # that selection produces a document the engine validates and uses
  selection = selection_from_raw(None)
  raw = serialize_selection(selection)
  document = load_profile_document(raw)
  assert document is not None and set(document) == set(PERSONALITY_KEYS)
