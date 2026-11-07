"""SQLite-backed durable SpillStore implementation.

Implements the same async protocol as MemorySpillStore while using SQLite for
survival across process restarts. SQLite calls are small and synchronous by
nature; they execute in the event-loop thread because writes are bounded and
serialized.

Note on Windows: ``with sqlite3.connect(...)`` commits but does *not* close the
connection, keeping the file handle locked. Every access goes through
:meth:`_connect`, which uses ``contextlib.closing`` so handles are released
immediately — required for temp-dir cleanup and cross-instance durability on
Windows dev boxes.
"""

from __future__ import annotations

import contextlib
import hashlib
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ai.spill.manager import SpillRef


@contextlib.contextmanager
def _closed_connection(db_path: Path) -> Iterator[sqlite3.Connection]:
  """Yield a committed-on-exit connection that is ALWAYS closed afterwards."""
  conn = sqlite3.connect(str(db_path))
  try:
    yield conn
  finally:
    try:
      conn.close()
    except sqlite3.Error:
      pass


class SqliteSpillStore:
  """Durable local spill store keyed by deterministic session/content locator."""

  def __init__(self, db_path: str | Path) -> None:
    self.db_path = Path(db_path)
    self.db_path.parent.mkdir(parents=True, exist_ok=True)
    with _closed_connection(self.db_path) as conn:
      conn.execute(
        "CREATE TABLE IF NOT EXISTS spill (locator TEXT PRIMARY KEY, session_id TEXT NOT NULL, content TEXT NOT NULL, bytes INTEGER NOT NULL, created_at REAL NOT NULL)"
      )
      conn.commit()

  @staticmethod
  def _locator(session_id: str, content: str) -> str:
    digest = hashlib.sha256(f"{session_id}:{content}".encode("utf-8")).hexdigest()[:24]
    return f"spill://sqlite/{session_id}/{digest}"

  async def save_text(self, input: dict[str, Any]) -> SpillRef:
    owner = input.get("owner") if isinstance(input.get("owner"), dict) else {}
    session_id = str(owner.get("session_id") or "default")
    content = str(input.get("content") or "")
    locator = self._locator(session_id, content)
    size = len(content.encode("utf-8"))
    with _closed_connection(self.db_path) as conn:
      conn.execute(
        "INSERT OR REPLACE INTO spill(locator, session_id, content, bytes, created_at) VALUES (?, ?, ?, ?, strftime('%s','now'))",
        (locator, session_id, content, size),
      )
      conn.commit()
    return SpillRef(locator=locator, bytes=size, retrieval_hint=f"recall with locator {locator}")

  async def get_text(self, locator: str) -> str | None:
    with _closed_connection(self.db_path) as conn:
      row = conn.execute("SELECT content FROM spill WHERE locator = ?", (locator,)).fetchone()
    return str(row[0]) if row is not None else None

  def list_summaries(self, session_id: str) -> list[dict[str, Any]]:
    prefix = f"spill://sqlite/{session_id}/"
    with _closed_connection(self.db_path) as conn:
      rows = conn.execute(
        "SELECT locator, content FROM spill WHERE locator LIKE ? ORDER BY created_at DESC",
        (prefix + "%",),
      ).fetchall()
    return [
      {"locator": str(locator), "summary": str(content), "retrieval_hint": f"recall with locator {locator}"}
      for locator, content in rows
    ]

  def close(self) -> None:
    """Checkpoint and release SQLite resources (safe to call repeatedly)."""
    try:
      with _closed_connection(self.db_path) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.commit()
    except sqlite3.Error:
      pass
