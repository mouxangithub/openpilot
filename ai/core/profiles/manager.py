"""Profile manager — unified apply/merge interface.

This sits in front of the existing domain-specific implementations
(tune presets, profile_sync manifest, agent config) and exposes a single
``ProfileManager`` that other layers can call.
"""

from __future__ import annotations

from typing import Any

from ai.core.profiles.profile import Profile, ProfileDomain
from ai.core.profiles.store import ProfileStore


class ProfileManager:
  def __init__(self, store: ProfileStore | None = None) -> None:
    self.store = store or ProfileStore(_default_profile_dir())

  def list(self, domain: ProfileDomain | None = None) -> list[Profile]:
    return self.store.list(domain)

  def get(self, domain: ProfileDomain, profile_id: str) -> Profile | None:
    return self.store.get(domain, profile_id)

  def save(self, profile: Profile) -> None:
    self.store.save(profile)

  def remove(self, domain: ProfileDomain, profile_id: str) -> bool:
    return self.store.remove(domain, profile_id)

  def apply(self, profile: Profile, *, params: Any | None = None, brand: str = "") -> dict[str, Any]:
    """Apply a profile. Returns a result dict compatible with tool results."""
    if profile.domain == ProfileDomain.TUNE:
      return _apply_tune_profile(profile, brand=brand)
    if profile.domain == ProfileDomain.VEHICLE:
      return _apply_vehicle_profile(profile, params=params)
    if profile.domain == ProfileDomain.HARNESS:
      return _apply_harness_profile(profile, params=params)
    if profile.domain == ProfileDomain.AGENTS:
      return _apply_agents_profile(profile, params=params)
    return {"ok": False, "error": f"Domain '{profile.domain}' apply not implemented"}

  def import_remote(self, payload: dict[str, Any], *, replace: bool = False) -> dict[str, Any]:
    imported = self.store.import_all(payload, replace=replace)
    return {"ok": True, "imported": len(imported), "profiles": [p.id for p in imported]}

  def export_manifest(self) -> dict[str, Any]:
    return self.store.export_all()


def _default_profile_dir() -> str:
  try:
    from ai.system.paths import workspace_path
    return str(workspace_path("ai_profiles"))
  except Exception:
    import tempfile
    return tempfile.mkdtemp(prefix="ai_profiles_")


def _apply_tune_profile(profile: Profile, *, brand: str = "") -> dict[str, Any]:
  preset_id = profile.settings.get("preset_id") or profile.id
  try:
    from ai.tools.domains.tune.sp_presets import get_sp_preset
    preset = get_sp_preset(preset_id)
    if preset is None:
      from ai.tools.domains.tune.presets import get_preset
      preset = get_preset(preset_id)
    if preset is None:
      return {"ok": False, "error": f"Unknown tune preset '{preset_id}'"}
    return {"ok": True, "applied": preset_id, "stack": preset.get("stack", "openpilot"), "params": list(preset.get("params", {}).keys())}
  except Exception as e:
    return {"ok": False, "error": f"Failed to resolve tune preset: {e}"}


def _apply_vehicle_profile(profile: Profile, *, params: Any | None = None) -> dict[str, Any]:
  try:
    from ai.common.storage import write_param
    write_param(params, "ai_vehicle_profile", profile.settings)
    return {"ok": True, "applied": profile.id, "params": list(profile.settings.keys())}
  except Exception as e:
    return {"ok": False, "error": f"Failed to write vehicle profile: {e}"}


def _apply_harness_profile(profile: Profile, *, params: Any | None = None) -> dict[str, Any]:
  try:
    from ai.common.storage import write_param, write_param_bool
    settings = profile.settings
    if "modelTier" in settings:
      write_param(params, "ai_model_tier", str(settings["modelTier"]))
    if "deferredTools" in settings:
      write_param_bool(params, "ai_deferred_tools", bool(settings["deferredTools"]))
    if "externalizeResults" in settings:
      write_param_bool(params, "ai_externalize_results", bool(settings["externalizeResults"]))
    return {"ok": True, "applied": profile.id, "params": list(settings.keys())}
  except Exception as e:
    return {"ok": False, "error": f"Failed to write harness profile: {e}"}


def _apply_agents_profile(profile: Profile, *, params: Any | None = None) -> dict[str, Any]:
  try:
    disabled = profile.settings.get("disabled") or []
    from ai.agents.config import save_disabled_agent_ids
    save_disabled_agent_ids(params, list(disabled))
    return {"ok": True, "applied": profile.id, "disabled": list(disabled)}
  except Exception as e:
    return {"ok": False, "error": f"Failed to apply agents profile: {e}"}
