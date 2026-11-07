"""Context manager to run git commands against openpilot or assistant ai repo."""

from __future__ import annotations

import contextvars
from pathlib import Path

_git_repo_target: contextvars.ContextVar[str] = contextvars.ContextVar("git_repo_target", default="openpilot")
_git_repo_root_override: contextvars.ContextVar[str | None] = contextvars.ContextVar(
  "git_repo_root_override", default=None,
)


def current_git_repo_target() -> str:
  return _git_repo_target.get()


def current_git_repo_root_override() -> Path | None:
  raw = _git_repo_root_override.get()
  return Path(raw).resolve() if raw else None


class git_repo_context:
  def __init__(self, repo_target: str = "openpilot", *, repo_root: str | Path | None = None) -> None:
    self._repo_target = repo_target or "openpilot"
    self._repo_root = str(repo_root.resolve()) if repo_root else None
    self._token_target = None
    self._token_root = None

  def __enter__(self) -> "git_repo_context":
    self._token_target = _git_repo_target.set(self._repo_target)
    self._token_root = _git_repo_root_override.set(self._repo_root)
    return self

  def __exit__(self, *_args) -> None:
    if self._token_root is not None:
      _git_repo_root_override.reset(self._token_root)
    if self._token_target is not None:
      _git_repo_target.reset(self._token_target)
