"""Standard tool schema definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine


@dataclass
class ToolParameter:
    name: str
    type: str = "string"
    description: str = ""
    required: bool = True
    enum: list[str] | None = None
    default: Any = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": self.type,
            "description": self.description,
        }
        if self.enum is not None:
            d["enum"] = self.enum
        if self.default is not None:
            d["default"] = self.default
        return d


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)
    capability: str = ""
    requires_hitl: bool = False

    def to_openai_dict(self) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []
        for p in self.parameters:
            properties[p.name] = p.to_dict()
            if p.required:
                required.append(p.name)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


ToolResult = dict[str, Any]
ToolHandlerFn = Callable[..., Coroutine[Any, Any, ToolResult]]


def simple_tool_spec(
    name: str,
    description: str,
    params: list[tuple[str, str, str]] | None = None,
    capability: str = "",
    requires_hitl: bool = False,
) -> ToolSpec:
    parameters: list[ToolParameter] = []
    for p in params or []:
        parameters.append(ToolParameter(name=p[0], type=p[1], description=p[2]))
    return ToolSpec(name=name, description=description, parameters=parameters, capability=capability, requires_hitl=requires_hitl)
