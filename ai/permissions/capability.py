"""Capability definitions."""

from __future__ import annotations

from enum import Enum


class Capability(str, Enum):
    """Vehicle/system capability units."""

    USB_DEVICE_ACCESS = "usb_device_access"
    CAN_BUS_ACCESS = "can_bus_access"
    VEHICLE_FLASH = "vehicle_flash"
    VEHICLE_LOG_READ = "vehicle_log_read"
    DBC_PARSE = "dbc_parse"
    WORKSPACE_WRITE = "workspace_write"
    SHELL_EXEC = "shell_exec"

    @classmethod
    def all(cls) -> set[str]:
        return {c.value for c in cls}
