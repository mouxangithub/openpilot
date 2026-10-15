"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of zoompilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

ADB and Jetlink share the comma's USB port. The link on turns ADB off, and the
developer panels grey its toggle out. Nothing did that in this fork, so a comma
with ADB on and the link set kept AGNOS's ADB gadget (g1) on the only device
controller and jetlink could not build its own:

  Jetlink unavailable: USB gadget 'g1' already holds the device controller
  (a600000.dwc3); tear it down first
"""
import os

os.environ.setdefault("SCALE", "1")  # the ui import probes the monitor for its scale otherwise

from openpilot.common.params import Params
from openpilot.common.prefix import OpenpilotPrefix
from openpilot.common.test import OpenpilotTestCase
from openpilot.selfdrive.ui.ui_state import ui_state
from unittest import mock


class snapshot:
  """jetlink's Status, nothing to show unless a field says so."""

  def __new__(cls, **fields):
    from jetlink.openpilot import Status
    base = {'enabled': False, 'mode': 'off', 'transport': 'USB', 'present': False, 'port': None, 'ready': False,
            'reason': None, 'progress': None, 'model': None, 'default_model': None, 'standin': None}
    if fields.get('enabled'):
      base['mode'] = 'usb'
    return Status(**{**base, **fields})


# The widget check builds the real panels, whose textures need a raylib window.
# OpenpilotPrefix gives every test its own param store, so nothing here can
# reach a device's real /data/params.
_window_prefix = OpenpilotPrefix()


def setUpModule():
  import pyray as rl
  from openpilot.system.ui.lib.application import gui_app
  _window_prefix.__enter__()
  rl.set_config_flags(rl.FLAG_WINDOW_HIDDEN)
  gui_app.init_window("test_usb_port", fps=30)


def tearDownModule():
  from openpilot.system.ui.lib.application import gui_app
  gui_app.close()
  _window_prefix.__exit__(None, None, None)


class TestTheUsbPort(OpenpilotTestCase):
  """ADB and Jetlink share the comma's USB port: the link on turns ADB off and
  greys its toggle out. In the params pass, not the panels, so a link set from
  sunnylink or the web panel counts too."""

  def setUp(self):
    super().setUp()
    self.params = Params()
    ui_state.params = self.params
    self.saved = ui_state.jetlink

  def tearDown(self):
    ui_state.jetlink = self.saved
    super().tearDown()

  def set(self, adb, link, mode='usb'):
    """link is jetlink's snapshot: None (a chestnut, or no jetlink), or enabled or not."""
    self.params.put_bool("AdbEnabled", adb, block=True)
    ui_state.jetlink = None if link is None else snapshot(enabled=link, mode=mode)
    ui_state._enforce_usb_port()
    return self.params.get_bool("AdbEnabled"), ui_state.adb_blocked

  def test_the_link_on_turns_adb_off_and_blocks_it(self):
    self.assertEqual(self.set(adb=True, link=True), (False, True))

  def test_the_link_off_leaves_adb_alone(self):
    self.assertEqual(self.set(adb=True, link=False), (True, False))
    self.assertEqual(self.set(adb=False, link=False), (False, False))

  def test_no_jetlink_snapshot_leaves_adb_alone(self):
    # a fitted chestnut, or no jetlink on this device
    self.assertEqual(self.set(adb=True, link=None), (True, False))

  def test_the_wifi_link_leaves_the_port_alone(self):
    # over Wi-Fi the comma joins a hotspot and builds no gadget, so ADB stays
    self.assertEqual(self.set(adb=True, link=True, mode='wifi'), (True, False))
    self.assertEqual(self.set(adb=False, link=True, mode='wifi'), (False, False))

  def test_both_developer_panels_grey_adb_out(self):
    from openpilot.selfdrive.ui.layouts.settings.developer import DeveloperLayout
    from openpilot.selfdrive.ui.mici.layouts.settings.developer import DeveloperLayoutMici
    tici, mici = DeveloperLayout(), DeveloperLayoutMici()
    with mock.patch.object(ui_state, 'is_offroad', return_value=True):
      for link, enabled in ((False, True), (True, False)):
        self.set(adb=False, link=link)
        self.assertEqual(tici._adb_toggle.action_item.enabled, enabled)
        self.assertEqual(mici._adb_toggle.enabled, enabled)


class TestTheWifiMode(OpenpilotTestCase):
  """Wi-Fi is the fourth Jetlink mode: the setting's index must match jetlink's
  MODES, and every panel that names a mode must name this one."""

  def test_the_adapter_agrees_with_jetlink_on_the_modes(self):
    import jetlink
    from openpilot.sunnypilot import jetlink_adapter
    self.assertEqual(jetlink_adapter.MODES, jetlink.openpilot.MODES)
    self.assertIn('wifi', jetlink_adapter.MODES)

  def test_every_mode_has_a_title_and_a_label(self):
    from openpilot.selfdrive.ui.sunnypilot.accelerator_link import LINK_MODE_TITLES, LINK_MODES
    from openpilot.selfdrive.ui.sunnypilot.mici.layouts.models import LINK_MODE_LABELS
    for mode in LINK_MODES:
      self.assertIn(mode, LINK_MODE_TITLES, f"{mode} has no tici title")
      self.assertIn(mode, LINK_MODE_LABELS, f"{mode} has no mici label")

  def test_the_status_asks_for_the_hotspot_instead_of_the_port(self):
    # through tr: the device runs the translated UI, so an English literal would
    # only pass on a machine with no catalog
    from openpilot.selfdrive.ui.sunnypilot.accelerator_link import link_status
    from openpilot.system.ui.lib.multilang import tr
    with mock.patch.object(ui_state, 'jetlink', snapshot(enabled=True, mode='wifi', port='empty')):
      # nothing is on the USB-C port in this mode, and saying so would mislead
      self.assertEqual(link_status(), tr("Join the device's hotspot and open Jetlink there."))
    with mock.patch.object(ui_state, 'jetlink', snapshot(enabled=True, mode='usb', port='empty')):
      self.assertEqual(link_status(), tr("Nothing on the USB port."))
