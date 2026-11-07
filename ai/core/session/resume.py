"""Unified session resume path (A-P0.3).

Consolidates the resume/repair logic that previously lived in multiple places
(``SessionStorage.load_session``, ``SessionLog.load_persisted`` and ad-hoc
repair). This module is the single entry point callers use to resume a session:

1. Load the persisted session through ``SessionStore`` (typed, folded state).
2. Validate adoptability via :mod:`ai.core.session.adopt`.
3. Repair broken transcripts by rebuilding from the raw JSONL when the in-memory
   surface cannot be folded cleanly.

It does NOT rewrite ``SessionStorage`` or ``SessionLog``; it composes them so
existing callers keep working while new callers get one consistent path.
"""

from __future__ import annotations

from typing import Any

from ai.core.session.adopt import AdoptableCheck, check_adoptable
from ai.core.session.log import SessionLog, get_session_store


class ResumeError(RuntimeError):
    """Raised when a session cannot be resumed."""


def unified_resume(
    session_id: str,
    *,
    cwd: str | None = None,
    repair: bool = True,
    **adopt_kwargs: Any,
) -> SessionLog:
    """Resume a session through the unified path.

    Args:
        session_id: The session to resume.
        cwd: Requested working directory; passed to the adoptability check.
        repair: If True, a corrupt/incomplete transcript is rebuilt from raw
            events instead of failing.
        **adopt_kwargs: Forwarded to :func:`check_adoptable`.

    Returns:
        The resumed :class:`SessionLog`.

    Raises:
        ResumeError: If the session cannot be adopted or is unresolvable.
    """
    store = get_session_store()

    # 1. Try to get-or-create loading persisted events.
    log = store.get_or_create(session_id, load_persisted=True)

    # 2. Adoptability check against the header if present.
    header = log.session_header()
    if header is not None:
        check: AdoptableCheck = check_adoptable(header, session_id=session_id, cwd=cwd, **adopt_kwargs)
        if not check.ok:
            raise ResumeError(check.reason)

    # 3. Repair when the surface is broken but raw events exist.
    if repair and log.seq > 0:
        try:
            messages = log.derive_messages()
            _ = messages  # exercises the surface fold
        except Exception as exc:  # pragma: no cover - defensive
            log.reset()
            log = store.get_or_create(session_id, load_persisted=True)

    return log


__all__ = ["ResumeError", "unified_resume"]