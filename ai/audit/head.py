"""Audit head anchor management."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class AuditHead:
    count: int
    head: str

    def to_dict(self) -> dict[str, Any]:
        return {"count": self.count, "head": self.head}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditHead:
        return cls(count=int(data.get("count", 0)), head=str(data.get("head", "")))


def read_head(path: Path) -> AuditHead | None:
    if not path.exists():
        return None
    try:
        return AuditHead.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return None


def write_head(path: Path, head: AuditHead) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(head.to_dict(), ensure_ascii=False), encoding="utf-8")
