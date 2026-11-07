"""Tool schemas for vehicle parameter operations."""

from __future__ import annotations

from ai.permissions.capability import Capability
from ai.tools.schemas import ToolParameter, ToolSpec


def build_vehicle_tool_specs() -> dict[str, ToolSpec]:
  return {
    "read_params": ToolSpec(
      name="read_params",
      description="Read current vehicle parameters. Optionally filter by key prefix.",
      parameters=[
        ToolParameter(name="key", type="string", description="Optional specific key to read", required=False),
        ToolParameter(name="prefix", type="string", description="Optional prefix filter", required=False),
      ],
      capability=Capability.VEHICLE_LOG_READ.value,
      requires_hitl=False,
    ),
    "write_params": ToolSpec(
      name="write_params",
      description="Write vehicle parameters. A snapshot is created automatically before writing.",
      parameters=[
        ToolParameter(name="params", type="object", description="Dict of parameter key -> value", required=True),
      ],
      capability=Capability.WORKSPACE_WRITE.value,
      requires_hitl=False,
    ),
    "snapshot_params": ToolSpec(
      name="snapshot_params",
      description="Create a snapshot of current vehicle parameters.",
      parameters=[],
      capability=Capability.VEHICLE_LOG_READ.value,
      requires_hitl=False,
    ),
    "generate_diff": ToolSpec(
      name="generate_diff",
      description="Show diff between current params and a proposed set without writing.",
      parameters=[
        ToolParameter(name="params", type="object", description="Proposed parameter changes", required=True),
      ],
      capability=Capability.VEHICLE_LOG_READ.value,
      requires_hitl=False,
    ),
  }


def build_vehicle_handlers(store_factory):
  """Return handler dict bound to a VehicleParams factory."""

  async def read_params(args: dict, session, call_id: str) -> dict:
    store = store_factory(session.cwd)
    key = args.get("key")
    if key:
      return {"ok": True, "value": store.read(key)}
    prefix = args.get("prefix")
    data = store.read()
    if prefix:
      data = {k: v for k, v in data.items() if str(k).startswith(prefix)}
    return {"ok": True, "params": data}

  async def write_params(args: dict, session, call_id: str) -> dict:
    store = store_factory(session.cwd)
    proposed = args.get("params", {})
    result = store.write_params(proposed)
    return {
      "ok": result.ok,
      "message": result.message,
      "diff": result.diff,
      "snapshot_path": result.snapshot_path,
      "error": result.error,
    }

  async def snapshot_params(args: dict, session, call_id: str) -> dict:
    store = store_factory(session.cwd)
    path = store.snapshot()
    return {"ok": True, "snapshot_path": str(path)}

  async def generate_diff(args: dict, session, call_id: str) -> dict:
    store = store_factory(session.cwd)
    proposed = args.get("params", {})
    diff = store.generate_diff(proposed)
    return {"ok": True, "diff": diff}

  return {
    "read_params": read_params,
    "write_params": write_params,
    "snapshot_params": snapshot_params,
    "generate_diff": generate_diff,
  }
