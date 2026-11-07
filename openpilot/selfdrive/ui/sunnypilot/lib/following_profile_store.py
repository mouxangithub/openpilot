"""
Copyright (c) 2026-, sunnypilot contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

Pure helpers that map the Following Profile settings UI's per-personality
preset selection to the LongitudinalFollowingProfile param document and back.

Kept free of any UI imports (no pyray) so the preset -> JSON round trip stays
unit testable on a plain PC host, exactly like the engine module it wraps
(selfdrive/controls/lib/following_profile.py).
"""
from openpilot.selfdrive.controls.lib.following_profile import (
  DEFAULT_PRESETS,
  FOLLOWING_PRESET_CURVES,
  PERSONALITY_KEYS,
  load_profile_document,
  serialize_profile_document,
)

# The presets the settings UI offers, in button order. These are exactly the
# named presets the engine already knows - no new curves are invented here.
PRESET_ORDER = ("close", "medium", "far")

# The param key this store owns (params_keys.h: PERSISTENT | BACKUP, STRING).
PROFILE_PARAM_KEY = "LongitudinalFollowingProfile"


def default_selection() -> dict[str, str]:
  """The selection the UI shows when nothing is configured yet."""
  return dict(DEFAULT_PRESETS)


def selection_from_document(document: dict | None) -> dict[str, str]:
  """Read a validated profile document into a per-personality preset selection.

  Personalities the document says nothing about (or with an unknown preset)
  keep their default preset, so the UI always shows a complete, valid state.
  """
  selection = default_selection()
  if not document:
    return selection
  for personality in PERSONALITY_KEYS:
    entry = document.get(personality)
    if isinstance(entry, dict) and entry.get("preset") in PRESET_ORDER:
      selection[personality] = entry["preset"]
  return selection


def selection_from_raw(raw) -> dict[str, str]:
  """Parse the stored param value (str / bytes / dict / None) into a selection.

  A malformed or unset value falls back to the defaults instead of raising:
  the engine fails closed the same way.
  """
  return selection_from_document(load_profile_document(raw))


def build_document(selection: dict[str, str]) -> dict:
  """Build the profile document for a selection.

  Each personality gets its chosen named preset with that preset's default
  curve, which is what the engine expects for a named preset.
  """
  document = {}
  for personality in PERSONALITY_KEYS:
    preset = selection.get(personality)
    if preset in PRESET_ORDER:
      document[personality] = {"preset": preset, "curve": list(FOLLOWING_PRESET_CURVES[preset])}
  return document


def serialize_selection(selection: dict[str, str]) -> str:
  """Serialize a selection into the JSON string stored in the param.

  Delegates to the engine's serializer, so the exact document the UI writes is
  the exact document the engine validates - one canonical shape, no drift.
  """
  return serialize_profile_document(build_document(selection))
