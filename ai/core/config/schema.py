"""Six-domain JSON schema for AI OP assistant configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConversationConfig:
    ai_use_agent_loop: bool = True
    ai_compaction_max_tokens: int = 32768
    ai_externalize_threshold: int = 51200
    ai_max_turns: int = 16
    ai_sandbox_mode: str = "danger_full_access"
    ai_model: str = "offline-mock"
    ai_provider: str = "offline"
    ai_temperature: float = 0.7

    def to_dict(self) -> dict[str, Any]:
        return {
            "ai_use_agent_loop": self.ai_use_agent_loop,
            "ai_compaction_max_tokens": self.ai_compaction_max_tokens,
            "ai_externalize_threshold": self.ai_externalize_threshold,
            "ai_max_turns": self.ai_max_turns,
            "ai_sandbox_mode": self.ai_sandbox_mode,
            "ai_model": self.ai_model,
            "ai_provider": self.ai_provider,
            "ai_temperature": self.ai_temperature,
        }


@dataclass
class EvolutionConfig:
    enabled: bool = False
    mutation_budget: int = 4
    reflection_depth: int = 2

    def to_dict(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "mutation_budget": self.mutation_budget, "reflection_depth": self.reflection_depth}


@dataclass
class VehicleSafetyConfig:
    block_writes_when_enabled: bool = True
    block_writes_when_moving: bool = True
    v_ego_threshold_m_s: float = 0.1
    hitl_capabilities: list[str] = field(default_factory=lambda: ["vehicle_flash", "can_bus_access"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_writes_when_enabled": self.block_writes_when_enabled,
            "block_writes_when_moving": self.block_writes_when_moving,
            "v_ego_threshold_m_s": self.v_ego_threshold_m_s,
            "hitl_capabilities": list(self.hitl_capabilities),
        }


@dataclass
class DataBackupConfig:
    auto_snapshot_before_write: bool = True
    max_snapshots: int = 10

    def to_dict(self) -> dict[str, Any]:
        return {"auto_snapshot_before_write": self.auto_snapshot_before_write, "max_snapshots": self.max_snapshots}


@dataclass
class DevDiagnosticsConfig:
    log_level: str = "INFO"
    enable_audit: bool = True
    enable_provider_tracing: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "log_level": self.log_level,
            "enable_audit": self.enable_audit,
            "enable_provider_tracing": self.enable_provider_tracing,
        }


@dataclass
class AgentSchedulerConfig:
    automations_enabled: bool = False
    default_timezone: str = "UTC"

    def to_dict(self) -> dict[str, Any]:
        return {"automations_enabled": self.automations_enabled, "default_timezone": self.default_timezone}


@dataclass
class AIOPConfig:
    conversation: ConversationConfig = field(default_factory=ConversationConfig)
    evolution: EvolutionConfig = field(default_factory=EvolutionConfig)
    vehicle_safety: VehicleSafetyConfig = field(default_factory=VehicleSafetyConfig)
    data_backup: DataBackupConfig = field(default_factory=DataBackupConfig)
    dev_diagnostics: DevDiagnosticsConfig = field(default_factory=DevDiagnosticsConfig)
    agent_scheduler: AgentSchedulerConfig = field(default_factory=AgentSchedulerConfig)

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation": self.conversation.to_dict(),
            "evolution": self.evolution.to_dict(),
            "vehicle_safety": self.vehicle_safety.to_dict(),
            "data_backup": self.data_backup.to_dict(),
            "dev_diagnostics": self.dev_diagnostics.to_dict(),
            "agent_scheduler": self.agent_scheduler.to_dict(),
        }


def load_config(raw: dict[str, Any] | None = None) -> AIOPConfig:
    raw = raw or {}
    return AIOPConfig(
        conversation=ConversationConfig(**raw.get("conversation", {})),
        evolution=EvolutionConfig(**raw.get("evolution", {})),
        vehicle_safety=VehicleSafetyConfig(**raw.get("vehicle_safety", {})),
        data_backup=DataBackupConfig(**raw.get("data_backup", {})),
        dev_diagnostics=DevDiagnosticsConfig(**raw.get("dev_diagnostics", {})),
        agent_scheduler=AgentSchedulerConfig(**raw.get("agent_scheduler", {})),
    )
