"""OP Agent built-in self-evolution (Hermes GEPA architecture).

See ai/evolution/gepa_engine.py — lazy imports to keep unit tests importable on PC.
"""

from __future__ import annotations

from typing import Any


def evolve_skill_gepa(*args: Any, **kwargs: Any) -> Any:
  from ai.evolution.gepa_engine import evolve_skill_gepa as _run
  return _run(*args, **kwargs)


def gepa_status() -> dict[str, Any]:
  from ai.evolution.gepa_engine import gepa_status as _status
  return _status()


__all__ = ["evolve_skill_gepa", "gepa_status"]
