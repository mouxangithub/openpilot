"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from openpilot.selfdrive.ui.sunnypilot.layouts.settings.vehicle.brands.base import BrandSettings
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr, tr_noop
from openpilot.system.ui.widgets import DialogResult
from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog
from openpilot.system.ui.sunnypilot.widgets.list_view import toggle_item_sp


ONROAD_ONLY_DESCRIPTION = tr_noop("Start the vehicle to check vehicle compatibility.")
SNG_HACK_UNAVAILABLE = tr_noop("sunnypilot Longitudinal Control must be available and enabled for your vehicle to use this feature.")

DESCRIPTIONS = {
  'enforce_stock_longitudinal': tr_noop(
    'sunnypilot will not take over control of gas and brakes. Factory Toyota longitudinal control will be used.'
  ),
  'stop_and_go_hack': tr_noop(
    'sunnypilot will allow some Toyota/Lexus cars to auto resume during stop and go traffic. '
    'This feature is only applicable to certain models that are able to use longitudinal control. This is an alpha feature. Use at your own risk.'
  ),
  'auto_hold': tr_noop(
    'Use the vehicle\'s auto brake hold feature on supported TSS2 hybrid Toyotas.'
  ),
  'enhanced_bsm': tr_noop(
    'Enable enhanced blind-spot monitoring behavior for certain Prius TSS2 and TSS-P Toyotas.'
  ),
  'tss2_long': tr_noop(
    'Use a custom longitudinal tuning profile for TSS2 Toyota vehicles.'
  ),
  'drive_mode': tr_noop(
    'Link the Toyota drive-mode button (ECO/NORMAL/SPORT) into sunnypilot logic.'
  ),
}


class ToyotaSettings(BrandSettings):
  def __init__(self):
    super().__init__()

    self.enforce_stock_longitudinal = toggle_item_sp(
      lambda: tr("Enforce Factory Longitudinal Control"),
      description=lambda: tr(DESCRIPTIONS["enforce_stock_longitudinal"]),
      initial_state=ui_state.params.get_bool("ToyotaEnforceStockLongitudinal"),
      callback=self._on_enable_enforce_stock_longitudinal,
      enabled=lambda: not ui_state.engaged,
    )

    self.stop_and_go_hack = toggle_item_sp(
      lambda: tr("Stop and Go Hack (Alpha)"),
      description=lambda: tr(DESCRIPTIONS["stop_and_go_hack"]),
      initial_state=ui_state.params.get_bool("ToyotaStopAndGoHack"),
      callback=self._on_enable_stop_and_go_hack,
      enabled=lambda: not ui_state.engaged,
    )

    self.auto_hold = toggle_item_sp(
      lambda: tr("Toyota: Auto Brake Hold FOR TSS2 HYBRID CARS"),
      description=lambda: tr(DESCRIPTIONS["auto_hold"]),
      initial_state=ui_state.params.get_bool("ToyotaAutoHold"),
      callback=lambda state: self._on_simple_toyota_toggle("ToyotaAutoHold", state),
      enabled=lambda: not ui_state.engaged,
    )

    self.enhanced_bsm = toggle_item_sp(
      lambda: tr("Toyota: Prius TSS2 BSM and some tssp"),
      description=lambda: tr(DESCRIPTIONS["enhanced_bsm"]),
      initial_state=ui_state.params.get_bool("ToyotaEnhancedBsm"),
      callback=lambda state: self._on_simple_toyota_toggle("ToyotaEnhancedBsm", state),
      enabled=lambda: not ui_state.engaged,
    )

    self.tss2_long = toggle_item_sp(
      lambda: tr("Toyota: custom longitudinal for TSS2"),
      description=lambda: tr(DESCRIPTIONS["tss2_long"]),
      initial_state=ui_state.params.get_bool("ToyotaTSS2Long"),
      callback=lambda state: self._on_simple_toyota_toggle("ToyotaTSS2Long", state),
      enabled=lambda: not ui_state.engaged,
    )

    self.drive_mode = toggle_item_sp(
      lambda: tr("Enable drive mode btn link"),
      description=lambda: tr(DESCRIPTIONS["drive_mode"]),
      initial_state=ui_state.params.get_bool("ToyotaDriveMode"),
      callback=lambda state: self._on_simple_toyota_toggle("ToyotaDriveMode", state),
      enabled=lambda: not ui_state.engaged,
    )

    self.items = [
      self.enforce_stock_longitudinal,
      self.stop_and_go_hack,
      self.auto_hold,
      self.enhanced_bsm,
      self.tss2_long,
      self.drive_mode,
    ]

  def _on_enable_enforce_stock_longitudinal(self, state: bool):
    if state:
      def confirm_callback(result: int):
        if result == DialogResult.CONFIRM:
          ui_state.params.put_bool("ToyotaEnforceStockLongitudinal", True)
          if ui_state.params.get_bool("AlphaLongitudinalEnabled"):
            ui_state.params.put_bool("AlphaLongitudinalEnabled", False)
          ui_state.params.put_bool("ToyotaStopAndGoHack", False)
          self.stop_and_go_hack.action_item.set_state(False)
          ui_state.params.put_bool("OnroadCycleRequested", True)
        else:
          self.enforce_stock_longitudinal.action_item.set_state(False)

      content = (f"<h1>{self.enforce_stock_longitudinal.title}</h1><br>" +
                 f"<p>{self.enforce_stock_longitudinal.description}</p>")

      dlg = ConfirmDialog(content, tr("Enable"), rich=True, callback=confirm_callback)
      gui_app.push_widget(dlg)

    else:
      ui_state.params.put_bool("ToyotaEnforceStockLongitudinal", False)
      ui_state.params.put_bool("OnroadCycleRequested", True)

  def _on_simple_toyota_toggle(self, param: str, state: bool):
    ui_state.params.put_bool(param, state)
    ui_state.params.put_bool("OnroadCycleRequested", True)

  def _on_enable_stop_and_go_hack(self, state: bool):
    if state:
      def confirm_callback(result: int):
        if result == DialogResult.CONFIRM:
          ui_state.params.put_bool("ToyotaStopAndGoHack", True)
          ui_state.params.put_bool("OnroadCycleRequested", True)
        else:
          self.stop_and_go_hack.action_item.set_state(False)

      content = (f"<h1>{self.stop_and_go_hack.title}</h1><br>" +
                 f"<p>{self.stop_and_go_hack.description}</p>")

      dlg = ConfirmDialog(content, tr("Enable"), rich=True, callback=confirm_callback)
      gui_app.push_widget(dlg)

    else:
      ui_state.params.put_bool("ToyotaStopAndGoHack", False)
      ui_state.params.put_bool("OnroadCycleRequested", True)

  def update_settings(self):
    if ui_state.CP is not None:
      longitudinal = ui_state.CP.openpilotLongitudinalControl
      enforce_stock = self.enforce_stock_longitudinal.action_item.get_state()

      if longitudinal and not enforce_stock:
        self.stop_and_go_hack.action_item.set_enabled(not ui_state.engaged)
        new_desc = tr(DESCRIPTIONS["stop_and_go_hack"])
        show_desc = False
      else:
        self.stop_and_go_hack.action_item.set_enabled(False)
        self.stop_and_go_hack.action_item.set_state(False)
        new_desc = "<b>" + tr(SNG_HACK_UNAVAILABLE) + "</b>\n\n" + tr(DESCRIPTIONS["stop_and_go_hack"])
        show_desc = True

      if self.stop_and_go_hack.description != new_desc:
        self.stop_and_go_hack.set_description(new_desc)
        if show_desc:
          self.stop_and_go_hack.show_description(True)
    else:
      self.stop_and_go_hack.action_item.set_enabled(False)
      new_desc = "<b>" + tr(ONROAD_ONLY_DESCRIPTION) + "</b>\n\n" + tr(DESCRIPTIONS["stop_and_go_hack"])
      if self.stop_and_go_hack.description != new_desc:
        self.stop_and_go_hack.set_description(new_desc)
        self.stop_and_go_hack.show_description(True)
