"""Vehicle safety guard: vEgo / enabled / ignition checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class VehicleState:
    enabled: bool = False
    v_ego_m_s: float = 0.0
    ignition: bool = True
    parking_brake: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VehicleState:
        return cls(
            enabled=bool(data.get("enabled", False)),
            v_ego_m_s=float(data.get("v_ego_m_s", 0.0)),
            ignition=bool(data.get("ignition", True)),
            parking_brake=bool(data.get("parking_brake", False)),
        )


class VehicleGuard:
    """Block high-consequence writes when vehicle is enabled or moving."""

    def __init__(self, v_ego_threshold_m_s: float = 0.1) -> None:
        self.v_ego_threshold_m_s = v_ego_threshold_m_s

    def check_write_allowed(self, state: VehicleState) -> tuple[bool, str]:
        if state.enabled:
            return False, "Vehicle is enabled: write operations blocked."
        if state.v_ego_m_s > self.v_ego_threshold_m_s:
            return False, f"Vehicle moving ({state.v_ego_m_s:.2f} m/s): write operations blocked."
        if not state.ignition:
            return False, "Ignition off: write operations blocked."
        return True, ""

    def check_control_allowed(self, state: VehicleState) -> tuple[bool, str]:
        if state.v_ego_m_s > self.v_ego_threshold_m_s:
            return False, "Vehicle moving: control-message transmission blocked."
        return True, ""
