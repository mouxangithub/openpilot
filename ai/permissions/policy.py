"""SandboxPolicy and CapabilityGrant models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from ai.permissions.capability import Capability


class SandboxMode(str, Enum):
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    DANGER_FULL_ACCESS = "danger_full_access"


class GrantState(str, Enum):
    ALLOWED = "allowed"
    ASK = "ask"
    DENIED = "denied"


@dataclass
class CapabilityGrant:
    capability: str
    state: GrantState = GrantState.DENIED
    source: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"capability": self.capability, "state": self.state.value, "source": self.source, "reason": self.reason}


@dataclass
class SandboxPolicy:
    mode: SandboxMode = SandboxMode.READ_ONLY
    containment_root: Path = field(default_factory=Path)
    grants: dict[str, CapabilityGrant] = field(default_factory=dict)

    def is_allowed(self, capability: str) -> bool:
        grant = self.grants.get(capability)
        if grant is None:
            return False
        return grant.state == GrantState.ALLOWED

    def requires_hitl(self, capability: str) -> bool:
        grant = self.grants.get(capability)
        if grant is None:
            return False
        return grant.state == GrantState.ASK

    def set_grant(self, capability: str, state: GrantState, source: str = "", reason: str = "") -> None:
        self.grants[capability] = CapabilityGrant(capability=capability, state=state, source=source, reason=reason)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "containment_root": str(self.containment_root),
            "grants": {k: v.to_dict() for k, v in self.grants.items()},
        }

    @classmethod
    def default(cls, containment_root: Path) -> SandboxPolicy:
        # User requested default fully-open sandbox. Keep vehicle guard in
        # SandboxPolicyService to block writes/flash when the car is enabled or
        # moving.
        policy = cls(mode=SandboxMode.DANGER_FULL_ACCESS, containment_root=containment_root)
        for cap in Capability.all():
            policy.set_grant(cap, GrantState.ALLOWED, source="default_policy", reason="default fully-open sandbox")
        return policy
