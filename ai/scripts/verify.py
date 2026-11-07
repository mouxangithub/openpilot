"""End-to-end verification script for AI OP Assistant P0 capabilities.

Runs without API keys and without openpilot/cereal dependencies.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

from ai.audit.log import AuditLog
from ai.core.agent.simple_loop import SimpleAgentLoop
from ai.core.config.schema import AIOPConfig, ConversationConfig
from ai.core.session.manager import SessionManager
from ai.core.session.storage import SessionStorage
from ai.permissions.hitl import HumanInLoop
from ai.permissions.service import SandboxPolicyService
from ai.providers.offline import OfflineProvider
from ai.tools.dispatch import ToolDispatcher
from ai.tools.spill import SpillWaterfall
from ai.tools.vehicle.params import VehicleParams
from ai.tools.vehicle.schemas import build_vehicle_handlers, build_vehicle_tool_specs


def _vehicle_params_factory(cwd: str) -> VehicleParams:
  return VehicleParams(Path(cwd) / ".ai" / "vehicle")


def _make_dispatcher(cwd: str, config: AIOPConfig) -> ToolDispatcher:
  schemas = build_vehicle_tool_specs()
  handlers = build_vehicle_handlers(_vehicle_params_factory)
  sandbox = SandboxPolicyService(config)
  audit = AuditLog.for_session(cwd)
  hitl = HumanInLoop()
  return ToolDispatcher(handlers, schemas, sandbox, audit, hitl)


async def scenario_1_vehicle_tune_write() -> dict[str, Any]:
  with tempfile.TemporaryDirectory() as tmp:
    config = AIOPConfig(conversation=ConversationConfig(ai_sandbox_mode="workspace_write"))
    sessions = SessionManager(tmp)
    session = sessions.create(title="tune test")
    dispatcher = _make_dispatcher(tmp, config)
    spill = SpillWaterfall(tmp)
    provider = OfflineProvider()
    loop = SimpleAgentLoop(session, sessions.storage, dispatcher, provider, config, spill=spill)
    result = await loop.run("make the lane change more aggressive by tuning params")
    ok = result.get("ok") and any(
      tr["name"] == "write_params" and tr["result"].get("ok")
      for tr in result.get("tool_results", [])
    )
    return {"scenario": "vehicle_tune_write", "ok": ok, "result": result}


async def scenario_2_tool_call_audit_chain() -> dict[str, Any]:
  with tempfile.TemporaryDirectory() as tmp:
    config = AIOPConfig(conversation=ConversationConfig(ai_sandbox_mode="workspace_write"))
    sessions = SessionManager(tmp)
    session = sessions.create(title="audit test")
    dispatcher = _make_dispatcher(tmp, config)
    spill = SpillWaterfall(tmp)
    provider = OfflineProvider()
    loop = SimpleAgentLoop(session, sessions.storage, dispatcher, provider, config, spill=spill)
    await loop.run("snapshot params")
    audit = AuditLog.for_session(tmp)
    verified, message = audit.verify()
    return {"scenario": "tool_call_audit_chain", "ok": verified, "audit_message": message}


async def scenario_3_session_resume_repair() -> dict[str, Any]:
  with tempfile.TemporaryDirectory() as tmp:
    sessions = SessionManager(tmp)
    session = sessions.create(title="resume test")
    sessions.storage.append_event(
      session,
      "function_call",
      {"call_id": "call_orphan_1", "name": "write_params", "arguments": {"params": {"x": 1}}},
    )
    resumed, repaired = sessions.resume(session.id)
    transcript = sessions.storage.read_transcript(resumed)
    has_repair = any(
      ev.type in ("function_call_result", "tool/result") and ev.payload.get("errorCode") == "TOOL_OUTCOME_UNKNOWN"
      for ev in transcript
    )
    return {"scenario": "session_resume_repair", "ok": has_repair, "repaired_count": len(repaired)}


async def main() -> int:
  results = await asyncio.gather(
    scenario_1_vehicle_tune_write(),
    scenario_2_tool_call_audit_chain(),
    scenario_3_session_resume_repair(),
  )
  all_ok = all(r["ok"] for r in results)
  output = json.dumps({"all_ok": all_ok, "scenarios": results}, ensure_ascii=False, indent=2, default=str)
  out_path = Path(__file__).with_name("verify_result.json")
  out_path.write_text(output + "\n", encoding="utf-8")
  print(output)
  return 0 if all_ok else 1


if __name__ == "__main__":
  raise SystemExit(asyncio.run(main()))
