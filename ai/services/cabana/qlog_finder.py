"""Public qlog/rlog discovery API for tools and tests."""
from __future__ import annotations
from pathlib import Path
from ai.services.cabana.replay import _find_qlogs, _find_rlogs

def find_qlogs(route_dir: Path) -> list[Path]:
  return _find_qlogs(route_dir)

def find_rlogs(route_dir: Path) -> list[Path]:
  return _find_rlogs(route_dir)
