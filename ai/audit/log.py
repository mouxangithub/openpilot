"""Audit log with SHA256 hash chain."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ai.audit.head import AuditHead, read_head, write_head


GENESIS_HASH: str = "0" * 64


@dataclass
class AuditEntry:
    index: int
    timestamp: int
    action: str
    data: dict[str, Any]
    prev_hash: str
    hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "action": self.action,
            "data": self.data,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditEntry:
        return cls(
            index=int(data["index"]),
            timestamp=int(data["timestamp"]),
            action=str(data["action"]),
            data=dict(data.get("data") or {}),
            prev_hash=str(data.get("prev_hash", GENESIS_HASH)),
            hash=str(data.get("hash", "")),
        )


def compute_hash(entry_data: dict[str, Any], prev_hash: str) -> str:
    payload = json.dumps(entry_data, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256((payload + prev_hash).encode("utf-8")).hexdigest()


class AuditLog:
    """Append-only hash-chain audit log."""

    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.log_dir / "audit.jsonl"
        self.head_path = self.log_dir / "audit.head"

    @classmethod
    def for_session(cls, cwd: str) -> AuditLog:
        return cls(Path(cwd) / ".ai" / "audit")

    def _read_entries(self) -> list[AuditEntry]:
        entries: list[AuditEntry] = []
        if not self.log_path.exists():
            return entries
        with self.log_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(AuditEntry.from_dict(json.loads(line)))
                except Exception:
                    continue
        return entries

    def _tail_hash(self) -> str:
        entries = self._read_entries()
        if not entries:
            return GENESIS_HASH
        return entries[-1].hash

    def _next_index(self) -> int:
        entries = self._read_entries()
        if not entries:
            return 1
        return entries[-1].index + 1

    def append(self, action: str, data: dict[str, Any]) -> AuditEntry:
        index = self._next_index()
        timestamp = int(time.time())
        prev_hash = self._tail_hash()
        entry_data = {"index": index, "timestamp": timestamp, "action": action, "data": data}
        entry_hash = compute_hash(entry_data, prev_hash)
        entry = AuditEntry(index=index, timestamp=timestamp, action=action, data=data, prev_hash=prev_hash, hash=entry_hash)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False, default=str) + "\n")
            f.flush()
        write_head(self.head_path, AuditHead(count=index, head=entry_hash))
        return entry

    def verify(self) -> tuple[bool, str]:
        entries = self._read_entries()
        prev_hash = GENESIS_HASH
        for entry in entries:
            entry_data = {"index": entry.index, "timestamp": entry.timestamp, "action": entry.action, "data": entry.data}
            expected = compute_hash(entry_data, prev_hash)
            if entry.hash != expected:
                return False, f"Hash mismatch at index {entry.index}"
            if entry.prev_hash != prev_hash:
                return False, f"Prev hash mismatch at index {entry.index}"
            prev_hash = entry.hash
        head = read_head(self.head_path)
        if head is None:
            if not entries:
                return True, "Empty log, no head"
            return False, "Head anchor missing"
        if head.count != (entries[-1].index if entries else 0):
            return False, "Head count mismatch"
        if head.head != prev_hash:
            return False, "Head hash mismatch"
        return True, f"Verified {len(entries)} entries"
