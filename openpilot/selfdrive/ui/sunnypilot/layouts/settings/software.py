"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""

from openpilot.selfdrive.ui.layouts.settings.software import SoftwareLayout
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr, tr_noop
from openpilot.system.ui.widgets import DialogResult
from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog

from openpilot.system.ui.sunnypilot.widgets.list_view import toggle_item_sp


DESCRIPTIONS = {
  'disable_updates_offroad': tr_noop(
    "When enabled, automatic software updates will be off.<br><b>This requires a reboot to take effect.</b>"
  ),
  'disable_updates_onroad': tr_noop(
    "Please enable \"Always Offroad\" mode or turn off the vehicle to adjust these toggles."
  )
}


class SoftwareLayoutSP(SoftwareLayout):
  def __init__(self):
    super().__init__()
    self.disable_updates_toggle = toggle_item_sp(
      lambda: tr("Disable Updates"),
      description="",
      initial_state=ui_state.params.get_bool("DisableUpdates"),
      callback=self._on_disable_updates_toggled,
    )
    self._scroller.add_widget(self.disable_updates_toggle)

  def _handle_reboot(self, result):
    if result == DialogResult.CONFIRM:
      ui_state.params.put_bool("DisableUpdates", self.disable_updates_toggle.action_item.get_state())
      ui_state.params.put_bool("DoReboot", True)
    else:
      self.disable_updates_toggle.action_item.set_state(ui_state.params.get_bool("DisableUpdates"))

  def _on_disable_updates_toggled(self, enabled):
    dialog = ConfirmDialog(tr("System reboot required for changes to take effect. Reboot now?"), tr("Reboot"), callback=self._handle_reboot)
    gui_app.push_widget(dialog)

  def _update_state(self):
    super()._update_state()
    show_advanced = ui_state.params.get_bool("ShowAdvancedControls")
    self.disable_updates_toggle.action_item.set_enabled(ui_state.is_offroad())
    self.disable_updates_toggle.set_visible(show_advanced)

    disable_updates_desc = tr(DESCRIPTIONS["disable_updates_offroad"] if ui_state.is_offroad() else DESCRIPTIONS["disable_updates_onroad"])
    self.disable_updates_toggle.set_description(disable_updates_desc)
