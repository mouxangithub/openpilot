"""
Copyright (c) 2026-, sunnypilot contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

The "Following Profile" section of the Cruise panel: the master switch plus a
per-personality preset picker for the speed-dependent following profiles
(selfdrive/controls/lib/following_profile.py + long_mpc.py consume them).

Not a panel: CruiseLayout lists `items` in its own scroller and drives the
update_state / refresh hooks, the same pattern AlphaLongitudinalToggles uses.
"""
from openpilot.common.params import Params
from openpilot.selfdrive.controls.lib.following_profile import PERSONALITY_KEYS
from openpilot.selfdrive.ui.sunnypilot.lib.following_profile_store import (
  PRESET_ORDER,
  PROFILE_PARAM_KEY,
  serialize_selection,
  selection_from_raw,
)
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.multilang import tr, tr_noop
from openpilot.system.ui.sunnypilot.widgets.list_view import multiple_button_item_sp, section_heading_sp, toggle_item_sp

MASTER_SWITCH_DESCRIPTION = tr_noop(
  "Replace the single following distance per personality with a speed-dependent profile. " +
  "The follow time is interpolated over speed, so the gap can be shorter in town and longer on the highway."
)

PROFILE_SECTION_TITLE = tr_noop("Following Profile")

# Personality -> display label; preset -> display label. Both translated lazily
# through callables so a language switch re-renders without rebuilding items.
PERSONALITY_LABELS = {
  "aggressive": tr_noop("Aggressive Personality"),
  "standard": tr_noop("Standard Personality"),
  "relaxed": tr_noop("Relaxed Personality"),
}

PERSONALITY_DESCRIPTIONS = {
  "aggressive": tr_noop("Preset used for the aggressive driving personality: close (1.25 s -> 1.0 s), medium (1.45 s -> 1.2 s) or far (1.6 s -> 1.4 s), low speed -> highway speed."),
  "standard": tr_noop("Preset used for the standard driving personality: close (1.25 s -> 1.0 s), medium (1.45 s -> 1.2 s) or far (1.6 s -> 1.4 s), low speed -> highway speed."),
  "relaxed": tr_noop("Preset used for the relaxed driving personality: close (1.25 s -> 1.0 s), medium (1.45 s -> 1.2 s) or far (1.6 s -> 1.4 s), low speed -> highway speed."),
}

PRESET_LABELS = {
  "close": tr_noop("Close"),
  "medium": tr_noop("Medium"),
  "far": tr_noop("Far"),
}


class FollowingProfileToggles:
  """Master switch + one preset picker per personality, bound to params."""

  def __init__(self):
    self._params = Params()
    # The per-personality preset selection mirrored from the param; refresh()
    # rebuilds it, callbacks only mutate it on a real user change.
    self._selection: dict[str, str] = selection_from_raw(self._params.get(PROFILE_PARAM_KEY))

    self._enabled_toggle = toggle_item_sp(
      title=lambda: tr("Custom Following Profiles"),
      description=lambda: tr(MASTER_SWITCH_DESCRIPTION),
      param="LongitudinalFollowingProfileEnabled")

    self._preset_items: dict[str, object] = {}
    for personality in PERSONALITY_KEYS:
      self._preset_items[personality] = multiple_button_item_sp(
        title=lambda p=personality: tr(PERSONALITY_LABELS[p]),
        description=lambda p=personality: tr(PERSONALITY_DESCRIPTIONS[p]),
        buttons=[lambda p=preset: tr(PRESET_LABELS[p]) for preset in PRESET_ORDER],
        button_width=300,
        callback=self._on_preset_changed(personality),
        selected_index=PRESET_ORDER.index(self._selection[personality]))

    self.items = [
      section_heading_sp(lambda: tr(PROFILE_SECTION_TITLE)),
      self._enabled_toggle,
      *self._preset_items.values(),
    ]

  def update_state(self):
    """Per-frame visibility/enable, driven by CruiseLayout._update_state."""
    has_long = ui_state.CP is not None and ui_state.has_longitudinal_control
    self._enabled_toggle.action_item.set_enabled(has_long)

    enabled = self._enabled_toggle.action_item.get_state()
    for item in self._preset_items.values():
      item.set_visible(enabled)
      item.action_item.set_enabled(has_long)

  def refresh(self):
    """Re-read both params from disk: called when the panel opens."""
    self._enabled_toggle.action_item.set_state(self._params.get_bool("LongitudinalFollowingProfileEnabled"))
    self._selection = selection_from_raw(self._params.get(PROFILE_PARAM_KEY))
    for personality, item in self._preset_items.items():
      item.action_item.selected_button = PRESET_ORDER.index(self._selection[personality])

  def _on_preset_changed(self, personality: str):
    """One callback per picker: writes the JSON param only when the user picks
    a preset that differs from the stored one."""
    def callback(index: int):
      preset = PRESET_ORDER[index]
      if self._selection.get(personality) == preset:
        return
      self._selection[personality] = preset
      self._params.put(PROFILE_PARAM_KEY, serialize_selection(self._selection))
    return callback
