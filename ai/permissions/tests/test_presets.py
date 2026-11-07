"""Tests for ai.permissions.presets."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai.common.config_store import AiConfigStore
from ai.permissions.presets import (
  PermissionPreset,
  PermissionPresetService,
)


class TestPermissionPresetService(unittest.TestCase):
  def _service(self) -> PermissionPresetService:
    tmp = tempfile.TemporaryDirectory()
    self.addCleanup(tmp.cleanup)
    store = AiConfigStore(path=Path(tmp.name) / "config.json")
    return PermissionPresetService(store=store)

  def test_builtin_presets(self) -> None:
    service = self._service()
    names = {p.name for p in service.list_presets()}
    self.assertEqual(names, {"strict", "workspace", "danger"})

  def test_default_active_is_strict(self) -> None:
    service = self._service()
    preset = service.get_active_preset()
    self.assertEqual(preset.name, "strict")
    self.assertEqual(preset.sandbox_mode, "read-only")
    self.assertEqual(preset.approval_policy, "ask")

  def test_apply_preset_persists(self) -> None:
    service = self._service()
    applied = service.apply_preset("workspace")
    self.assertEqual(applied.name, "workspace")
    active = service.get_active_preset()
    self.assertEqual(active.name, "workspace")
    # Also load from a fresh service pointing at the same store.
    preset = PermissionPresetService(store=service._store).get_active_preset()
    self.assertEqual(preset.name, "workspace")

  def test_unknown_preset_falls_back(self) -> None:
    service = self._service()
    service._store.put("ai_permission_preset", "unknown")
    preset = service.get_active_preset()
    self.assertEqual(preset.name, "strict")

  def test_to_dict(self) -> None:
    preset = PermissionPreset(
      name="x",
      sandbox_mode="read-only",
      approval_policy="ask",
      label="X",
      description="desc",
    )
    self.assertEqual(preset.to_dict()["name"], "x")


if __name__ == "__main__":
  unittest.main()
