"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of zoompilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

The user's say over the Jetlink setting, shared by the mici and tici models panels:
Off, USB (a Jetson, a Linux PC or a Mac), iOS (an iPhone), or Wi-Fi (the
device whose hotspot the comma joined), stored as an index into the adapter's
MODES. The small model is picked as ever: manager runs whichever modeld that
bundle needs and the link joins it, so the setting never changes which modeld
runs. Everything else here reads ui_state.jetlink, the snapshot the params
pass takes, and what the models panels say of the big models jetlink runs.
"""
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.sunnypilot import jetlink_adapter
from openpilot.sunnypilot.jetlink_adapter import KEYS, MODES
from openpilot.system.ui.lib.multilang import tr

# the setting is an index into the adapter's MODES (off/usb/ios/wifi)
LINK_MODES = MODES
LINK_PARAM = KEYS.link
LINK_MODE_TITLES = {"off": "Off", "usb": "USB", "ios": "iOS", "wifi": "Wi-Fi"}


def link_mode() -> str:
  """The setting as stored, one of MODES: the panel shows it even when
  jetlink cannot run, so a link that will not start can be turned off."""
  index = ui_state.params.get(KEYS.link, return_default=True)
  return MODES[index] if isinstance(index, int) and 0 <= index < len(MODES) else "off"


def link_toggle_meaningful() -> bool:
  """Offered wherever jetlink is checked out, as the chestnut slot is offered
  whether or not a board is fitted, except beside a chestnut, which runs the
  big model itself; and while the setting is on, whatever else. Presence
  cannot be the gate: with the link off there is no gadget for a Jetson to
  enumerate, so the toggle that turns it on would wait for the thing it enables."""
  if ui_state.chestnut_present:
    return False
  return ui_state.jetlink is not None or link_mode() != "off"


def link_status() -> str:
  """One line under the toggle: what is on the comma's USB-C port right now.

  jetlink knows a Jetson, or a phone, and the transport says which. Below that
  only the CC pin speaks: it says a cable with a host behind it is plugged in,
  not what the host is. Empty where the kernel does not expose it, rather
  than claiming an empty port.
  """
  jetlink = ui_state.jetlink
  if jetlink is None:
    return ""
  if jetlink.present:
    return f"{tr('Jetlink connected:')} {jetlink.transport}."
  # Wi-Fi leaves the USB-C port alone: point the user at the hotspot instead
  if getattr(jetlink, "mode", None) == "wifi":
    return tr("Join the device's hotspot and open Jetlink there.")
  if jetlink.port is None:
    return ""
  return tr("Nothing on the USB port.") if jetlink.port == "empty" else tr("A device is on the USB port.")


def big_model_progress() -> tuple[str, float, str] | None:
  """(stage, 0..1, message) while jetlink is working, else None. The message
  is carried because a stage like "waiting for jetlink" has no meaningful fraction,
  and it names the cable once jetlink counts enough link drops to blame it"""
  jetlink = ui_state.jetlink
  progress = jetlink.progress if jetlink is not None else None
  if not progress:
    return None
  stage = str(progress.get('stage', ''))
  if stage in ('', 'ready'):
    return None
  msg = tr(str(progress.get('msg', '')))
  if drops := progress.get('drops'):
    # on iOS the phone app is the other suspect
    hint = tr("check cable or app") if jetlink.mode == 'ios' else tr("check cable")
    msg = tr("{}, {} ({} drops)").format(msg, hint, drops)
  return stage, float(progress.get('frac', 0.0)), msg


def standin_model() -> str | None:
  """The big model jetlink drives while the pick is still being downloaded or
  built: the last one the Jetson built. None with a chestnut fitted."""
  return None if ui_state.chestnut_present else getattr(ui_state.jetlink, 'standin', None)


def big_model_note(ref: str) -> str | None:
  """What jetlink says of one big model for the picker's list: built on the
  Jetson, or downloaded to the comma. None with a chestnut fitted."""
  if ui_state.chestnut_present or ui_state.jetlink is None:
    return None
  return {'ready': tr("ready on Jetson"), 'downloaded': tr("downloaded")}.get(jetlink_adapter.model_state(ref))
