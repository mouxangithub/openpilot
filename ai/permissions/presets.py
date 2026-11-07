"""Permission presets for the AI OP assistant.

Presets bundle a sandbox mode with an approval policy and persist the
active preset through ``AiConfigStore``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai.common.config_store import AiConfigStore


PRESET_KEY = "ai_permission_preset"


@dataclass(frozen=True)
class PermissionPreset:
  """Named permission preset.

  Attributes:
    name: Machine identifier (e.g. ``strict``).
    sandbox_mode: Target sandbox mode string.
    approval_policy: ``ask`` or ``never``.
    label: Human-readable label.
    description: Optional longer explanation.
  """

  name: str
  sandbox_mode: str
  approval_policy: str
  label: str
  description: str = ""

  def to_dict(self) -> dict[str, Any]:
    return {
      "name": self.name,
      "sandbox_mode": self.sandbox_mode,
      "approval_policy": self.approval_policy,
      "label": self.label,
      "description": self.description,
    }


class PermissionPresetService:
  """Manage builtin permission presets and persist the active selection."""

  BUILTIN_STRICT: PermissionPreset = PermissionPreset(
    name="strict",
    sandbox_mode="read-only",
    approval_policy="ask",
    label="Strict",
    description="Read-only sandbox; every high-consequence action asks.",
  )

  BUILTIN_WORKSPACE: PermissionPreset = PermissionPreset(
    name="workspace",
    sandbox_mode="workspace-write",
    approval_policy="ask",
    label="Workspace",
    description="Workspace write allowed; high-consequence actions ask.",
  )

  BUILTIN_DANGER: PermissionPreset = PermissionPreset(
    name="danger",
    sandbox_mode="danger-full-access",
    approval_policy="never",
    label="Danger",
    description="Full access; approvals are never requested.",
  )

  def __init__(self, store: AiConfigStore | None = None) -> None:
    self._store = store or AiConfigStore()
    # Force load now to avoid a re-entrant lock issue in AiConfigStore when
    # ``put`` is called before ``get`` on a fresh store.
    self._store.get(PRESET_KEY)

  def list_presets(self) -> list[PermissionPreset]:
    """Return all builtin presets."""
    return [
      self.BUILTIN_STRICT,
      self.BUILTIN_WORKSPACE,
      self.BUILTIN_DANGER,
    ]

  def apply_preset(self, name: str) -> PermissionPreset:
    """Activate ``name`` and persist it.

    Args:
      name: Preset name to activate.

    Returns:
      The activated preset.

    Raises:
      ValueError: If the preset is unknown.
    """
    preset = self._require_preset(name)
    self._store.put(PRESET_KEY, name)
    return preset

  def get_active_preset(self) -> PermissionPreset:
    """Return the currently active preset, defaulting to strict."""
    name = self._store.get(PRESET_KEY, "strict")
    if not name:
      return self.BUILTIN_STRICT
    try:
      return self._require_preset(str(name))
    except ValueError:
      return self.BUILTIN_STRICT

  def _require_preset(self, name: str) -> PermissionPreset:
    for preset in self.list_presets():
      if preset.name == name:
        return preset
    raise ValueError(f"unknown permission preset: {name}")
