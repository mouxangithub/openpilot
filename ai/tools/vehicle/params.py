"""Vehicle parameter read/write, diff, and snapshot."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ParamWriteResult:
    ok: bool
    message: str
    diff: dict[str, tuple[Any, Any]]
    snapshot_path: str = ""
    error: str = ""


class VehicleParams:
    """In-memory vehicle params store for tests/demo.

    Production delegates to openpilot Params() API.
    """

    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._params_file = self.storage_dir / "vehicle_params.json"
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self._params_file.exists():
            try:
                self._data = json.loads(self._params_file.read_text(encoding="utf-8"))
            except Exception:
                self._data = {}
        else:
            self._data = {}

    def _save(self) -> None:
        self._params_file.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    def read(self, key: str | None = None) -> dict[str, Any] | Any:
        if key is None:
            return copy.deepcopy(self._data)
        return copy.deepcopy(self._data.get(key))

    def generate_diff(self, proposed: dict[str, Any]) -> dict[str, tuple[Any, Any]]:
        diff: dict[str, tuple[Any, Any]] = {}
        for k, v in proposed.items():
            old = self._data.get(k)
            if old != v:
                diff[k] = (old, v)
        return diff

    def snapshot(self) -> Path:
        snapshot_file = self.storage_dir / "snapshots" / f"params_{__import__('time').time():.0f}.json"
        snapshot_file.parent.mkdir(parents=True, exist_ok=True)
        snapshot_file.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        return snapshot_file

    def write_params(self, proposed: dict[str, Any]) -> ParamWriteResult:
        diff = self.generate_diff(proposed)
        if not diff:
            return ParamWriteResult(ok=True, message="No changes", diff={})
        snapshot = self.snapshot()
        for k, v in proposed.items():
            self._data[k] = v
        self._save()
        return ParamWriteResult(
            ok=True,
            message=f"Wrote {len(diff)} params",
            diff=diff,
            snapshot_path=str(snapshot),
        )
