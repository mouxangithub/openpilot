"""Graph node definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class NodeKind(StrEnum):
  START = "start"
  LLM = "llm"
  TOOL_CALL = "tool_call"
  TOOL_RESULT = "tool_result"
  OUTPUT = "output"
  DECISION = "decision"


@dataclass
class Node:
  id: str
  kind: NodeKind
  label: str = ""
  config: dict[str, Any] = field(default_factory=dict)
  inputs: list[str] = field(default_factory=list)
  outputs: list[str] = field(default_factory=list)
  position: dict[str, float] = field(default_factory=lambda: {"x": 0.0, "y": 0.0})

  def to_dict(self) -> dict[str, Any]:
    return {
      "id": self.id,
      "kind": self.kind.value,
      "label": self.label,
      "config": self.config,
      "inputs": self.inputs,
      "outputs": self.outputs,
      "position": self.position,
    }

  @staticmethod
  def from_dict(data: dict[str, Any]) -> Node:
    return Node(
      id=str(data.get("id", "")),
      kind=NodeKind(str(data.get("kind", NodeKind.START.value))),
      label=str(data.get("label", "")),
      config=dict(data.get("config") or {}),
      inputs=list(data.get("inputs") or []),
      outputs=list(data.get("outputs") or []),
      position=dict(data.get("position") or {"x": 0.0, "y": 0.0}),
    )
