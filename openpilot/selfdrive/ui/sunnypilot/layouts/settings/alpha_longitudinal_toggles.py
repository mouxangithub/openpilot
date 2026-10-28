"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of zoompilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

The alpha switch and the modes that run on openpilot longitudinal control, at the top of the tizi
Cruise panel. Developer drops its copy of the alpha switch (DeveloperLayoutSP) so it appears once.
"""
from openpilot.selfdrive.ui.layouts.settings.developer import DESCRIPTIONS as DEVELOPER_DESCRIPTIONS
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr, tr_noop
from openpilot.system.ui.sunnypilot.widgets.list_view import toggle_item_sp
from openpilot.system.ui.widgets import DialogResult
from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog

# upstream's Toggles text from before it retired chill mode, with our name and default
EXPERIMENTAL_MODE_DESCRIPTION = tr_noop(
  "zoompilot defaults to driving in experimental mode; turn it off for chill mode. " +
  "Experimental mode enables alpha-level features that aren't ready for chill mode. " +
  "Experimental features are listed below:<br>" +
  "<h4>End-to-End Longitudinal Control</h4><br>" +
  "Let the driving model control the gas and brakes. zoompilot will drive as it thinks a human would, including stopping for red lights and stop signs. " +
  "Since the driving model decides the speed to drive, the set speed will only act as an upper bound. This is an alpha quality feature; " +
  "mistakes should be expected.<br>" +
  "<h4>New Driving Visualization</h4><br>" +
  "The driving visualization will transition to the road-facing wide-angle camera at low speeds to better show some turns. " +
  "The Experimental mode logo will also be shown in the top right corner."
)


class AlphaLongitudinalToggles:
  """Not a panel: CruiseLayout lists `items` in its own scroller and drives the two hooks."""
  def __init__(self):
    self._alpha_long_toggle = toggle_item_sp(
      title=lambda: tr("Alpha Longitudinal"),
      description=lambda: tr(DEVELOPER_DESCRIPTIONS["alpha_longitudinal"]),
      callback=self._on_alpha_long,
      enabled=lambda: not ui_state.engaged)

    self._experimental_toggle = toggle_item_sp(
      title=lambda: tr("Experimental Mode"),
      description=lambda: tr(EXPERIMENTAL_MODE_DESCRIPTION),
      callback=ui_state.set_experimental_mode)

    self._set_speed_toggle = toggle_item_sp(
      title=lambda: tr("Set Speed Assist"),
      description=lambda: tr("In Experimental Mode, drive toward your set speed and following distance as chill mode does " +
                             "whenever the model holds back. The model still makes every slowdown."),
      param="ExperimentalModeSetSpeed")

    self._refresh_toggles = (
      ("AlphaLongitudinalEnabled", self._alpha_long_toggle),
      ("ExperimentalMode", self._experimental_toggle),
      ("ExperimentalModeSetSpeed", self._set_speed_toggle),
    )
    self.items = [item for _, item in self._refresh_toggles]

    ui_state.add_offroad_transition_callback(self.refresh)
    ui_state.add_engaged_transition_callback(self.refresh)

  def update_state(self):
    CP = ui_state.CP
    has_long = CP is not None and ui_state.has_longitudinal_control
    self._alpha_long_toggle.set_visible(CP is not None and CP.alphaLongitudinalAvailable)
    self._experimental_toggle.action_item.set_enabled(CP is None or has_long)
    # only acts in experimental mode: locked without it, keeping its value
    self._set_speed_toggle.action_item.set_enabled(has_long and self._experimental_toggle.action_item.get_state())

  def refresh(self):
    for key, item in self._refresh_toggles:
      item.action_item.set_state(ui_state.params.get_bool(key))

  @staticmethod
  def _confirm(item, callback) -> None:
    content = f"<h1>{item.title}</h1><br><p>{item.description}</p>"
    gui_app.push_widget(ConfirmDialog(content, tr("Enable"), rich=True, callback=callback))

  def _on_alpha_long(self, state: bool):
    if not state:
      ui_state.set_alpha_longitudinal(False)
      return

    def on_result(result: DialogResult):
      if result == DialogResult.CONFIRM:
        ui_state.set_alpha_longitudinal(True)
      else:
        self._alpha_long_toggle.action_item.set_state(False)

    self._confirm(self._alpha_long_toggle, on_result)
