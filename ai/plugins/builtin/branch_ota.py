"""Branch / prebuilt / OTA preflight plugin."""

from __future__ import annotations

from typing import Any, Callable


TOOL_META: dict[str, dict[str, Any]] = {
  "prebuilt_branch_status": {"label": "Prebuilt 分支状态", "group": "read", "default_enabled": True, "driving": True},
  "checkout_prebuilt_branch": {"label": "切换 Prebuilt 分支", "group": "write", "default_enabled": True, "driving": False},
  "ota_preflight_checklist": {"label": "OTA 更新预检", "group": "read", "default_enabled": True, "driving": True},
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
  {"type": "function", "function": {"name": "prebuilt_branch_status", "description": "Compare dev branch vs *-prebuilt and local prebuilt file.", "parameters": {"type": "object", "properties": {"dev_branch": {"type": "string"}, "remote": {"type": "string"}}, "required": []}}},
  {"type": "function", "function": {"name": "checkout_prebuilt_branch", "description": "Offroad: git fetch + reset --hard origin/<branch>-prebuilt; verify prebuilt file. confirm=true.", "parameters": {"type": "object", "properties": {"dev_branch": {"type": "string"}, "remote": {"type": "string"}, "confirm": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "ota_preflight_checklist", "description": "Disk/thermal/panda/OTA checklist before update or branch switch.", "parameters": {"type": "object", "properties": {}, "required": []}}},
]


def make_handlers(ctx: dict) -> dict[str, Callable[..., Any]]:
  p = ctx.get("params")
  stationary_check = ctx.get("stationary_check")

  def h_status(args):
    from ai.tools.branch_tools import prebuilt_branch_status
    return prebuilt_branch_status(
      dev_branch=str(args.get("dev_branch", "") or "master-c3"),
      remote=str(args.get("remote", "") or "origin"),
    )

  def h_checkout(args):
    err = stationary_check("run_shell")
    if err:
      return err
    from ai.tools.branch_tools import checkout_prebuilt_branch
    return checkout_prebuilt_branch(
      dev_branch=str(args.get("dev_branch", "") or "master-c3"),
      remote=str(args.get("remote", "") or "origin"),
      confirm=bool(args.get("confirm")),
    )

  def h_preflight(_a):
    from ai.tools.branch_tools import ota_preflight_checklist
    return ota_preflight_checklist(p)

  return {
    "prebuilt_branch_status": h_status,
    "checkout_prebuilt_branch": h_checkout,
    "ota_preflight_checklist": h_preflight,
  }
