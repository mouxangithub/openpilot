"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

Bluetooth audio manager client API, ported from StarPilot's
`starpilot/system/bluetooth/` package. The daemon side (bluetooth_managerd) lives in
this package too; consumers only ever need `BluetoothClient` and the status types.

The re-exports below are lazy (PEP 562): importing the package must not pull
openpilot.common.params (and transitively cereal/opendbc), so PC test suites can
stub that chain before touching any submodule.
"""
_LAZY_EXPORTS = ("BluetoothClient", "BluetoothDevice", "BluetoothStatus")

__all__ = list(_LAZY_EXPORTS)


def __getattr__(name: str):
  if name in _LAZY_EXPORTS:
    from openpilot.sunnypilot.system.bluetooth.protocol import BluetoothClient, BluetoothDevice, BluetoothStatus
    return {"BluetoothClient": BluetoothClient, "BluetoothDevice": BluetoothDevice, "BluetoothStatus": BluetoothStatus}[name]
  raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
