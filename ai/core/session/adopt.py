"""Session adoptability checks (D-P0.5).

Learned from ``@deepseek-ai/dsh`` headless ``assertAdoptable``: before resuming
or reusing a persisted session we must reject ones that were created under a
different profile / subagent origin / parent lineage / cwd. This prevents a
session from being silently adopted into the wrong context.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


class SessionNotAdoptable(Exception):
    """Raised when a session cannot be adopted for the requested context."""


@dataclass(frozen=True)
class AdoptableCheck:
    ok: bool
    reason: str = ""

    def raise_if_rejected(self) -> None:
        if not self.ok:
            raise SessionNotAdoptable(self.reason)


def _same_or_empty(a: str, b: str) -> bool:
    """True when equal, or when either side is empty (don't over-restrict)."""
    a, b = (a or "").strip(), (b or "").strip()
    if not a or not b:
        return True
    return a == b


def _cwd_matches(record_cwd: str, requested_cwd: str | None) -> bool:
    if not requested_cwd:
        return True
    a = (record_cwd or "").strip()
    if not a:
        # Record carries no cwd constraint; treat as unconstrained.
        return True
    a = os.path.abspath(a)
    b = os.path.abspath(requested_cwd)
    try:
        rel = os.path.relpath(a, b)
    except ValueError:  # cross-drive on Windows
        return False
    return rel == "." or rel == "" or not rel.startswith("..")


def check_adoptable(
    header: Any,
    *,
    session_id: str = "",
    cwd: str | None = None,
    reject_preset_override: bool = True,
    reject_subagent_origin: bool = True,
    reject_parent_lineage: bool = True,
) -> AdoptableCheck:
    """Validate whether ``header`` may be adopted for the requested context.

    Args:
        header: A ``SessionHeader``-like object (or dict) to inspect.
        session_id: The session being adopted (for error context).
        cwd: Requested working directory; a non-empty record cwd that escapes it
            fails adoption.
        reject_preset_override: Reject records whose ``agent_preset`` was set to
            something other than the default ``default``.
        reject_subagent_origin: Reject records whose ``origin`` is ``subagent``
            (a subagent session must not be adopted as a top-level session).
        reject_parent_lineage: Reject records with a ``parent_session`` set.

    Returns:
        An :class:`AdoptableCheck`; ``ok=False`` carries a human reason.
    """
    rec_cwd = getattr(header, "cwd", None)
    if rec_cwd is None and isinstance(header, dict):
        rec_cwd = header.get("cwd", "")
    rec_cwd = str(rec_cwd or "")

    preset = getattr(header, "agent_preset", None)
    if preset is None and isinstance(header, dict):
        preset = header.get("agent_preset", "")
    preset = str(preset or "")

    origin = getattr(header, "origin", None)
    if origin is None and isinstance(header, dict):
        origin = header.get("origin", "")
    origin = str(origin or "").strip().lower()

    parent = getattr(header, "parent_session", None)
    if parent is None and isinstance(header, dict):
        parent = header.get("parent_session", "")
    parent = str(parent or "")

    ctx = session_id or rec_cwd or "?"

    if reject_parent_lineage and parent:
        return AdoptableCheck(False, f"session {ctx}: has parent lineage (parent_session={parent!r}); not adoptable")

    if reject_preset_override and preset and preset != "default":
        return AdoptableCheck(False, f"session {ctx}: agent_preset={preset!r} is not default; not adoptable")

    if reject_subagent_origin and origin in ("subagent", "child", "agent"):
        return AdoptableCheck(False, f"session {ctx}: origin={origin!r} is a subagent; not adoptable")

    if not _cwd_matches(rec_cwd, cwd):
        return AdoptableCheck(False, f"session {ctx}: cwd mismatch (record={rec_cwd!r}, requested={cwd!r})")

    return AdoptableCheck(True, "adoptable")


def assert_adoptable(
    header: Any,
    *,
    session_id: str = "",
    cwd: str | None = None,
    **kwargs: Any,
) -> None:
    """Raise :class:`SessionNotAdoptable` if the header is not adoptable."""
    check_adoptable(header, session_id=session_id, cwd=cwd, **kwargs).raise_if_rejected()


__all__ = [
    "AdoptableCheck",
    "SessionNotAdoptable",
    "assert_adoptable",
    "check_adoptable",
]