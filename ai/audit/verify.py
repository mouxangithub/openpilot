"""Audit verify CLI/API helpers."""

from __future__ import annotations

from pathlib import Path

from ai.audit.log import AuditLog


def verify_audit(cwd: str) -> dict[str, Any]:
    audit = AuditLog.for_session(cwd)
    ok, message = audit.verify()
    return {"ok": ok, "message": message, "path": str(audit.log_path)}
