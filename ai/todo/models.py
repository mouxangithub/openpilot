"""Todo domain models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

TodoStatus = Literal["pending", "in_progress", "completed"]


@dataclass
class TodoItem:
  content: str
  status: TodoStatus = "pending"
  metadata: dict[str, Any] | None = None

  def to_dict(self) -> dict[str, Any]:
    out: dict[str, Any] = {
      "content": self.content,
      "status": self.status,
    }
    if self.metadata:
      out["metadata"] = dict(self.metadata)
    return out

  @staticmethod
  def from_dict(data: dict[str, Any]) -> TodoItem:
    return TodoItem(
      content=str(data.get("content", "")),
      status=str(data.get("status", "pending")),
      metadata=dict(data.get("metadata") or {}),
    )


@dataclass
class TodoCounts:
  pending: int
  in_progress: int
  completed: int

  def to_dict(self) -> dict[str, Any]:
    return {
      "pending": self.pending,
      "inProgress": self.in_progress,
      "completed": self.completed,
    }

  @staticmethod
  def from_dict(data: dict[str, Any]) -> TodoCounts:
    return TodoCounts(
      pending=int(data.get("pending", 0)),
      in_progress=int(data.get("inProgress", data.get("in_progress", 0))),
      completed=int(data.get("completed", 0)),
    )
