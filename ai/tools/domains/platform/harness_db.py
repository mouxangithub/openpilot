"""SQLite store for harness audit + usage events (queryable)."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_DB: sqlite3.Connection | None = None

HARNESS_DB = Path(__file__).resolve().parent.parent / "data" / "harness.db"


def _conn() -> sqlite3.Connection:
  global _DB
  if _DB is not None:
    return _DB
  HARNESS_DB.parent.mkdir(parents=True, exist_ok=True)
  _DB = sqlite3.connect(str(HARNESS_DB), check_same_thread=False)
  _DB.row_factory = sqlite3.Row
  _DB.execute("PRAGMA journal_mode=WAL")
  _DB.executescript(
    """
    CREATE TABLE IF NOT EXISTS audit_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts INTEGER NOT NULL,
      action TEXT NOT NULL,
      tool TEXT,
      ok INTEGER NOT NULL DEFAULT 1,
      detail_json TEXT,
      session_id TEXT,
      agent_id TEXT,
      hash TEXT,
      prev_hash TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_events(ts DESC);
    CREATE INDEX IF NOT EXISTS idx_audit_tool ON audit_events(tool);

    CREATE TABLE IF NOT EXISTS usage_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts INTEGER NOT NULL,
      provider TEXT,
      model TEXT,
      source TEXT,
      prompt_tokens INTEGER DEFAULT 0,
      completion_tokens INTEGER DEFAULT 0,
      total_tokens INTEGER DEFAULT 0,
      session_id TEXT,
      job_id TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage_events(ts DESC);
    CREATE INDEX IF NOT EXISTS idx_usage_model ON usage_events(model);
    """
  )
  _DB.commit()
  return _DB


def close_db() -> None:
  global _DB
  if _DB is not None:
    try:
      _DB.close()
    except Exception:
      pass
    _DB = None


def record_audit_event(
  *,
  action: str,
  tool: str = "",
  ok: bool = True,
  detail: dict[str, Any] | None = None,
  session_id: str = "",
  agent_id: str = "",
  chain_hash: str = "",
  prev_hash: str = "",
) -> None:
  try:
    with _LOCK:
      _conn().execute(
        """
        INSERT INTO audit_events (ts, action, tool, ok, detail_json, session_id, agent_id, hash, prev_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
          int(time.time() * 1000),
          action,
          tool,
          1 if ok else 0,
          json.dumps(detail or {}, ensure_ascii=False, default=str),
          session_id or "",
          agent_id or "",
          chain_hash,
          prev_hash,
        ),
      )
      _conn().commit()
  except Exception:
    pass


def record_usage_event(
  *,
  provider: str = "",
  model: str = "",
  source: str = "chat",
  usage: dict[str, Any] | None = None,
  session_id: str = "",
  job_id: str = "",
) -> None:
  u = usage or {}
  try:
    with _LOCK:
      _conn().execute(
        """
        INSERT INTO usage_events
          (ts, provider, model, source, prompt_tokens, completion_tokens, total_tokens, session_id, job_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
          int(time.time()),
          provider or "unknown",
          model or "unknown",
          source or "chat",
          int(u.get("prompt_tokens") or 0),
          int(u.get("completion_tokens") or 0),
          int(u.get("total_tokens") or 0),
          session_id or "",
          job_id or "",
        ),
      )
      _conn().commit()
  except Exception:
    pass


def query_audit(
  *,
  limit: int = 50,
  tool: str = "",
  since_ms: int = 0,
) -> dict[str, Any]:
  limit = max(1, min(int(limit), 500))
  clauses = ["1=1"]
  params: list[Any] = []
  if tool:
    clauses.append("tool = ?")
    params.append(tool)
  if since_ms > 0:
    clauses.append("ts >= ?")
    params.append(since_ms)
  sql = f"SELECT * FROM audit_events WHERE {' AND '.join(clauses)} ORDER BY ts DESC LIMIT ?"
  params.append(limit)
  try:
    with _LOCK:
      rows = _conn().execute(sql, params).fetchall()
    entries = [dict(r) for r in rows]
    for e in entries:
      e["ok"] = bool(e.get("ok"))
      if e.get("detail_json"):
        try:
          e["detail"] = json.loads(e["detail_json"])
        except json.JSONDecodeError:
          e["detail"] = {}
    return {"ok": True, "entries": entries, "count": len(entries)}
  except Exception as e:
    return {"ok": False, "error": str(e)}


def query_usage_summary(
  *,
  group_by: str = "model",
  since_ts: int = 0,
  limit: int = 20,
) -> dict[str, Any]:
  group_col = "model" if group_by == "model" else "provider"
  clauses = ["1=1"]
  params: list[Any] = []
  if since_ts > 0:
    clauses.append("ts >= ?")
    params.append(since_ts)
  sql = f"""
    SELECT {group_col} AS key,
           COUNT(*) AS calls,
           SUM(prompt_tokens) AS prompt_tokens,
           SUM(completion_tokens) AS completion_tokens,
           SUM(total_tokens) AS total_tokens
    FROM usage_events
    WHERE {' AND '.join(clauses)}
    GROUP BY {group_col}
    ORDER BY total_tokens DESC
    LIMIT ?
  """
  params.append(max(1, min(int(limit), 100)))
  try:
    with _LOCK:
      rows = _conn().execute(sql, params).fetchall()
    return {"ok": True, "groupBy": group_col, "rows": [dict(r) for r in rows]}
  except Exception as e:
    return {"ok": False, "error": str(e)}
