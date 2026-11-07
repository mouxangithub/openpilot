"""Stable structured errors for the LSP seam."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass
class LspError(Exception):
  """Structured LSP failure with a stable machine-readable code."""
  message: str
  code: str
  detail: Any = None

  def __post_init__(self) -> None:
    Exception.__init__(self, self.message)

  def to_dict(self) -> dict[str, Any]:
    result = {"ok": False, "error": self.message, "code": self.code}
    if self.detail is not None:
      result["detail"] = self.detail
    return result


NO_PROVIDER = "NO_PROVIDER"
WORKSPACE_OUTSIDE = "WORKSPACE_OUTSIDE"
INVALID_RESPONSE = "INVALID_RESPONSE"
TIMEOUT = "TIMEOUT"
