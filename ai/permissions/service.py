"""SandboxPolicyService evaluates commands, paths, and capabilities."""

from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Any

from ai.core.config.schema import AIOPConfig
from ai.permissions.capability import Capability
from ai.permissions.policy import GrantState, SandboxMode, SandboxPolicy
from ai.permissions.vehicle_guard import VehicleGuard, VehicleState


class PathEscapeError(Exception):
    """Raised when a path escapes the containment root."""


class SandboxPolicyService:
    """Central policy evaluation service."""

    def __init__(self, config: AIOPConfig) -> None:
        self.config = config
        self.vehicle_guard = VehicleGuard(config.vehicle_safety.v_ego_threshold_m_s)

    @classmethod
    def from_defaults(cls) -> SandboxPolicyService:
        return cls(AIOPConfig())

    def get_policy(self, containment_root: Path) -> SandboxPolicy:
        policy = SandboxPolicy.default(containment_root)
        mode = getattr(self.config.conversation, "ai_sandbox_mode", SandboxMode.READ_ONLY.value)
        try:
            policy.mode = SandboxMode(mode)
        except ValueError:
            policy.mode = SandboxMode.READ_ONLY
        if policy.mode == SandboxMode.WORKSPACE_WRITE:
            policy.set_grant(Capability.WORKSPACE_WRITE.value, GrantState.ALLOWED, source="config", reason="workspace-write mode")
        elif policy.mode == SandboxMode.DANGER_FULL_ACCESS:
            for cap in Capability.all():
                # Fully open by default; HITL can still be required per capability
                # through VehicleSafetyConfig.hitl_capabilities if desired.
                policy.set_grant(cap, GrantState.ALLOWED, source="config", reason="danger-full-access mode")
        return policy

    def check_path(self, path: str | Path, policy: SandboxPolicy) -> Path:
        target = Path(path).resolve()
        root = policy.containment_root.resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise PathEscapeError(f"Path {target} escapes containment root {root}") from exc
        return target

    def check_command(self, command: str, policy: SandboxPolicy) -> dict[str, Any]:
        parts = shlex.split(command)
        if not parts:
            return {"allowed": False, "reason": "empty command"}
        if policy.mode == SandboxMode.DANGER_FULL_ACCESS:
            return {"allowed": True, "reason": "danger mode", "hitl": True}
        blocked = {"sudo", "rm", "mkfs", "dd", "shutdown", "reboot"}
        if parts[0] in blocked:
            return {"allowed": False, "reason": f"blocked command: {parts[0]}"}
        return {"allowed": policy.mode != SandboxMode.READ_ONLY, "reason": "workspace shell"}

    def check_capability(
        self,
        capability: str,
        policy: SandboxPolicy,
        vehicle_state: VehicleState | None = None,
    ) -> dict[str, Any]:
        if capability not in Capability.all():
            return {"allowed": False, "reason": f"unknown capability: {capability}"}
        grant = policy.grants.get(capability)
        if grant is None or grant.state == GrantState.DENIED:
            return {"allowed": False, "reason": "capability denied by policy"}

        result: dict[str, Any] = {"allowed": True, "reason": grant.reason or "allowed"}
        if grant.state == GrantState.ASK:
            result["hitl_required"] = True

        # Fully-open mode: skip vehicle-guard while driving checks entirely so
        # every capability can execute regardless of vehicle state (user opted
        # into unrestricted operation). Audit logging still records the call.
        if (
            policy.mode == SandboxMode.DANGER_FULL_ACCESS
            and capability in {
                Capability.VEHICLE_FLASH.value,
                Capability.VEHICLE_LOG_READ.value,
                Capability.WORKSPACE_WRITE.value,
            }
        ):
            return result

        if vehicle_state is not None and capability in {
            Capability.VEHICLE_FLASH.value,
            Capability.VEHICLE_LOG_READ.value,
            Capability.WORKSPACE_WRITE.value,
        }:
            ok, reason = self.vehicle_guard.check_write_allowed(vehicle_state)
            if not ok:
                return {"allowed": False, "reason": reason}
        return result
