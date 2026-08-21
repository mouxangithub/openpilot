"""Toolset groups — driving_readonly / offroad_full / secoc / devops / pc_dev."""

from __future__ import annotations

from typing import Any

from ai.tools.agent_tools import TOOL_META

TOOLSETS: dict[str, dict[str, Any]] = {
  "driving_readonly": {
    "label": "行驶只读",
    "description": "行驶中允许的诊断与读取工具",
    "groups": frozenset({"read", "memory", "shell"}),
    "extra": frozenset(),
    "exclude": frozenset({"write_file", "write_params", "apply_tune_preset", "apply_sp_tune_preset"}),
  },
  "offroad_full": {
    "label": "Offroad 全工具",
    "description": "停车后可写参数、调参、重启",
    "groups": None,
    "extra": frozenset(),
    "exclude": frozenset(),
  },
  "secoc_pipeline": {
    "label": "SecOC 流水线",
    "description": "TSK / SecOC 密钥相关",
    "prefixes": ("tsk_", "get_tsk", "lookup_secoc"),
    "extra": frozenset({
      "get_vehicle_state", "read_params", "grep_log", "read_manager_log",
      "search_knowledge_base", "trip_review", "read_onroad_events",
    }),
  },
  "devops_ci": {
    "label": "DevOps / CI",
    "description": "Git、Runner、OTA、PR",
    "prefixes": ("git_", "github_", "prebuilt_", "ota_", "install_github"),
    "extra": frozenset({"run_pytest", "run_scons_build", "list_plugins"}),
  },
  "pc_replay": {
    "label": "PC 联调",
    "description": "Replay、Cabana、PlotJuggler",
    "prefixes": ("pc_", "plotjuggler_", "cabana_", "openpilotci_"),
    "extra": frozenset({"list_drive_routes", "cabana_list_routes", "analyze_route_summary", "route_time_series"}),
  },
}


def resolve_toolset(driving: bool, *, agent_id: str = "", explicit: str = "") -> str:
  if explicit and explicit in TOOLSETS:
    return explicit
  if driving:
    return "driving_readonly"
  if agent_id == "secoc":
    return "secoc_pipeline"
  if agent_id == "devops":
    return "devops_ci"
  if agent_id == "pc":
    return "pc_replay"
  return "offroad_full"


def tool_allowed_in_set(name: str, toolset_id: str) -> bool:
  spec = TOOLSETS.get(toolset_id)
  if not spec:
    return True
  meta = TOOL_META.get(name, {})
  if name in spec.get("exclude", ()):
    return False
  if name in spec.get("extra", ()):
    return True
  groups = spec.get("groups")
  if groups is None:
    return True
  if meta.get("group") in groups:
    return True
  prefixes = spec.get("prefixes") or ()
  return any(name.startswith(p) for p in prefixes)


def filter_tools_by_toolset(tools: list[dict[str, Any]] | None, toolset_id: str) -> list[dict[str, Any]] | None:
  if not tools:
    return tools
  out = []
  for tool in tools:
    name = tool.get("function", {}).get("name", "")
    if tool_allowed_in_set(name, toolset_id):
      out.append(tool)
  return out or None


def list_toolsets() -> list[dict[str, str]]:
  return [{"id": k, "label": v.get("label", k), "description": v.get("description", "")} for k, v in TOOLSETS.items()]
