"""Native Bluetooth HID remotes for sunnypilot.

Supports pairing and configuring Bluetooth HID remotes (e.g. Yiser-J6, generic HID keyboards)
to send cruise control and lane change commands via shared memory JSON files.

Architecture:
  carrot_bluetooth daemon  (evdev reader + HID decoder + CommandWriter)
    → /dev/shm/carrot-bluetooth/cruise.json   → cruise.py CommandReader
    → /dev/shm/carrot-bluetooth/lane.json     → desire_helper.py CommandReader
    → /dev/shm/carrot-bluetooth/status.json    → webui / native GUI status polling

  bluetooth_api.py (webui HTTP API)
    ↔ BlueZ D-Bus (bluez.py)
      → scan / pair / connect / disconnect / forget

Safety:
  - All configuration requires the vehicle to be stationary and cruise disengaged.
  - Commands expire after 400 ms.
  - Physical button presses take priority over Bluetooth commands.
  - Long-press actions repeat every 500 ms (accel/decel only).
"""

from openpilot.sunnypilot.carrot.bluetooth.model import (
  ACTIONS,
  BLUETOOTH_CANCEL,
  COMMAND_TTL,
  DEFAULT_MAPPING,
  CONFIG_PATH,
  REMOTE_BUTTONS,
  RUNTIME,
  AddressValidator,
  AtomicJSON,
  Clicks,
  CommandReader,
  CommandWriter,
  Decoder,
  config,
  read_json,
  validate_config,
)

__all__ = [
  "ACTIONS",
  "BLUETOOTH_CANCEL",
  "COMMAND_TTL",
  "CONFIG_PATH",
  "DEFAULT_MAPPING",
  "REMOTE_BUTTONS",
  "RUNTIME",
  "AddressValidator",
  "AtomicJSON",
  "Clicks",
  "CommandReader",
  "CommandWriter",
  "Decoder",
  "config",
  "read_json",
  "validate_config",
]
