from collections.abc import Callable
from openpilot.common.params import Params
from openpilot.system.ui.widgets.scroller import NavScroller
from openpilot.selfdrive.ui.mici.widgets.button import BigButton
from openpilot.selfdrive.ui.mici.layouts.settings.toggles import TogglesLayoutMici
from openpilot.selfdrive.ui.mici.layouts.settings.network.network_layout import NetworkLayoutMici
from openpilot.selfdrive.ui.mici.layouts.settings.device import DeviceLayoutMici, PairBigButton
from openpilot.selfdrive.ui.mici.layouts.settings.developer import DeveloperLayoutMici
from openpilot.selfdrive.ui.mici.layouts.settings.imu_calibration import ImuCalibrationLayoutMici
from openpilot.selfdrive.ui.mici.layouts.settings.software import SoftwareLayoutMici
from openpilot.selfdrive.ui.mici.layouts.settings.firehose import FirehoseLayout
from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.system.ui.lib.multilang import tr


class SettingsBigButton(BigButton):
  def _get_label_font_size(self):
    return 64


class SettingsLayout(NavScroller):
  def __init__(self):
    super().__init__()
    self._params = Params()
    self._preview_callback: Callable | None = None

    toggles_panel = TogglesLayoutMici()
    toggles_btn = SettingsBigButton(tr("toggles"), "", gui_app.texture("icons_mici/settings.png", 64, 64))
    toggles_btn.set_click_callback(lambda: gui_app.push_widget(toggles_panel))

    network_panel = NetworkLayoutMici()
    network_btn = SettingsBigButton(tr("network"), "", gui_app.texture("icons_mici/settings/network/wifi_strength_full.png", 76, 56))
    network_btn.set_click_callback(lambda: gui_app.push_widget(network_panel))

    device_panel = DeviceLayoutMici()
    device_btn = SettingsBigButton(tr("device"), "", gui_app.texture("icons_mici/settings/device_icon.png", 72, 58))
    device_btn.set_click_callback(lambda: gui_app.push_widget(device_panel))
    device_panel.set_preview_callback(self._enter_onroad_preview)

    software_panel = SoftwareLayoutMici()
    software_btn = SettingsBigButton(tr("software"), "", gui_app.texture("icons_mici/settings/software.png", 64, 75))
    software_btn.set_click_callback(lambda: gui_app.push_widget(software_panel))

    developer_panel = DeveloperLayoutMici()
    developer_btn = SettingsBigButton(tr("developer"), "", gui_app.texture("icons_mici/settings/developer_icon.png", 64, 60))
    developer_btn.set_click_callback(lambda: gui_app.push_widget(developer_panel))

    firehose_panel = FirehoseLayout()
    firehose_btn = SettingsBigButton(tr("firehose"), "", gui_app.texture("icons_mici/settings/firehose.png", 52, 62))
    firehose_btn.set_click_callback(lambda: gui_app.push_widget(firehose_panel))

    imu_calibration_panel = ImuCalibrationLayoutMici()
    imu_calibration_btn = SettingsBigButton(tr("imu calibration"), "", gui_app.texture("icons_mici/settings/developer_icon.png", 64, 60))
    imu_calibration_btn.set_click_callback(lambda: gui_app.push_widget(imu_calibration_panel))

    self._scroller.add_widgets([
      toggles_btn,
      network_btn,
      device_btn,
      software_btn,
      PairBigButton(),
      firehose_btn,
      imu_calibration_btn,
      developer_btn,
    ])

    self._font_medium = gui_app.font(FontWeight.MEDIUM)

  def set_preview_callback(self, callback: Callable | None) -> None:
    self._preview_callback = callback

  def _enter_onroad_preview(self) -> None:
    self._params.put_bool("IsOnroadPreview", True)
    if self._preview_callback is not None:
      self._preview_callback()
