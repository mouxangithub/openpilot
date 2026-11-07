"""Tool dispatch with capability/policy checks and audit logging."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from ai.audit.log import AuditLog
from ai.permissions.capability import Capability
from ai.permissions.hitl import ApprovalRequest, HumanInLoop
from ai.permissions.policy import SandboxMode
from ai.permissions.service import SandboxPolicyService
from ai.permissions.vehicle_guard import VehicleState
from ai.tools.schemas import ToolSpec


class ToolDispatchError(Exception):
    """Raised when a tool call is denied or fails validation."""


class ToolDispatcher:
    """Dispatches tool calls with sandbox policy + HITL + audit."""

    def __init__(
        self,
        handlers: dict[str, Any],
        schemas: dict[str, ToolSpec],
        sandbox: SandboxPolicyService,
        audit: AuditLog,
        hitl: HumanInLoop,
        vehicle_state: VehicleState | None = None,
    ) -> None:
        self.handlers = handlers
        self.schemas = schemas
        self.sandbox = sandbox
        self.audit = audit
        self.hitl = hitl
        self.vehicle_state = vehicle_state
        self._counter = 0

    def new_call_id(self, tool_name: str) -> str:
        self._counter += 1
        return f"call_{tool_name}_{time.time_ns()}_{self._counter}"

    async def run(self, name: str, argument: dict[str, Any], session: Any, tool_call_id: str = "") -> dict[str, Any]:
        call_id = tool_call_id or self.new_call_id(name)
        schema = self.schemas.get(name)
        if schema is None:
            return {"ok": False, "error": f"Unknown tool: {name}", "tool_call_id": call_id}

        capability = schema.capability
        if capability:
            policy = self.sandbox.get_policy(session.cwd)
            check = self.sandbox.check_capability(capability, policy, self.vehicle_state)
            if not check["allowed"]:
                self.audit.append("tool_denied", {"tool": name, "capability": capability, "reason": check["reason"], "tool_call_id": call_id})
                return {"ok": False, "error": check["reason"], "tool_call_id": call_id}
            if check.get("hitl_required") or schema.requires_hitl:
                approved = await self.hitl.request_approval(ApprovalRequest(
                    action=name,
                    capability=capability,
                    description=f"Tool '{name}' requires approval",
                    tool_call_id=call_id,
                    metadata={"arguments": argument},
                ))
                if not approved:
                    self.audit.append("tool_denied", {"tool": name, "capability": capability, "reason": "user_denied", "tool_call_id": call_id})
                    return {"ok": False, "error": "User denied", "tool_call_id": call_id}

        handler = self.handlers.get(name)
        if handler is None:
            return {"ok": False, "error": f"No handler for tool: {name}", "tool_call_id": call_id}

        self.audit.append("tool_call", {"tool": name, "capability": capability, "arguments": argument, "tool_call_id": call_id})
        try:
            if asyncio.iscoroutinefunction(handler):
                result = await handler(argument, session, call_id)
            else:
                result = handler(argument, session, call_id)
        except Exception as exc:
            result = {"ok": False, "error": str(exc), "tool_call_id": call_id}
        self.audit.append("tool_result", {"tool": name, "capability": capability, "result": result, "tool_call_id": call_id})
        return result
