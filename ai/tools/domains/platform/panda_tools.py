"""Unified Panda hardware/firmware tool facade (T-P2.3).

Historically Panda capabilities were split between device health checks and
flash/firmware tools. This module re-exports them under a single name so
callers and UI panels can treat Panda as one capability domain.
"""

from __future__ import annotations

from typing import Any, Callable

from ai.tools.domains.platform.device_health_tools import panda_status as _panda_status
from ai.tools.domains.platform.panda_flash_tools import (
  build_panda_firmware as _build_panda_firmware,
  build_panda_h7_firmware as _build_panda_h7_firmware,
  list_all_pandas as _list_all_pandas,
  list_f4_pandas as _list_f4_pandas,
  panda_recovery_hint as _panda_recovery_hint,
  rebuild_pandad as _rebuild_pandad,
  recover_dos_panda as _recover_dos_panda,
)


def panda_status(get_state_reader: Callable[..., Any] | None = None) -> dict[str, Any]:
  """Return Panda connection and health summary."""
  return _panda_status(get_state_reader=get_state_reader)


def list_all_pandas() -> dict[str, Any]:
  """List all detected Pandas with hardware details."""
  return _list_all_pandas()


def list_f4_pandas() -> dict[str, Any]:
  """List F4 (DOS/black panda) devices."""
  return _list_f4_pandas()


def build_panda_h7_firmware(*, jobs: int = 4) -> dict[str, Any]:
  """Build the H7 Panda firmware."""
  return _build_panda_h7_firmware(jobs=jobs)


def build_panda_firmware(*, jobs: int = 4, target: str = "auto") -> dict[str, Any]:
  """Build panda/board firmware."""
  return _build_panda_firmware(jobs=jobs, target=target)


def rebuild_pandad(*, confirm: bool = False) -> dict[str, Any]:
  """Rebuild the pandad binary."""
  return _rebuild_pandad(confirm=confirm)


def recover_dos_panda(
  panda_jungle: bool = True,
  *,
  get_state_reader: Callable[..., Any] | None = None,
) -> dict[str, Any]:
  """Recover/re-flash an F4 Panda."""
  return _recover_dos_panda(panda_jungle=panda_jungle, get_state_reader=get_state_reader)


def panda_recovery_hint(get_state_reader: Callable[..., Any] | None = None) -> dict[str, Any]:
  """Return recovery steps when no Panda is detected."""
  return _panda_recovery_hint(get_state_reader=get_state_reader)


__all__ = [
  "panda_status",
  "list_all_pandas",
  "list_f4_pandas",
  "build_panda_h7_firmware",
  "build_panda_firmware",
  "rebuild_pandad",
  "recover_dos_panda",
  "panda_recovery_hint",
]
