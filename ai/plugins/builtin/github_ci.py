"""GitHub CI plugin — workflow dispatch, wait, runner health."""

from __future__ import annotations

from typing import Any, Callable


TOOL_META: dict[str, dict[str, Any]] = {
  "trigger_github_workflow": {"label": "触发 Workflow", "group": "write", "default_enabled": True, "driving": False},
  "rerun_github_workflow": {"label": "重跑 Workflow", "group": "write", "default_enabled": True, "driving": False},
  "wait_github_workflow": {"label": "等待 Workflow 完成", "group": "read", "default_enabled": True, "driving": False},
  "check_github_runner_health": {"label": "Runner/CI 健康检查", "group": "read", "default_enabled": True, "driving": True},
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
  {"type": "function", "function": {"name": "trigger_github_workflow", "description": "Dispatch GitHub Actions workflow (default build.yaml on master-c3). Requires ai_github_actions_pat; confirm=true.", "parameters": {"type": "object", "properties": {"repo_url": {"type": "string"}, "workflow": {"type": "string"}, "ref": {"type": "string"}, "confirm": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "rerun_github_workflow", "description": "Rerun a failed workflow run. confirm=true required.", "parameters": {"type": "object", "properties": {"run_id": {"type": "integer"}, "repo_url": {"type": "string"}, "confirm": {"type": "boolean"}}, "required": ["run_id"]}}},
  {"type": "function", "function": {"name": "wait_github_workflow", "description": "Poll workflow run until completed (blocks up to timeout_seconds). Optional notification on finish.", "parameters": {"type": "object", "properties": {"run_id": {"type": "integer"}, "repo_url": {"type": "string"}, "workflow": {"type": "string"}, "ref": {"type": "string"}, "timeout_seconds": {"type": "integer"}, "poll_seconds": {"type": "integer"}, "notify_on_complete": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "check_github_runner_health", "description": "Local runner + GitHub API health summary; optional notify on issues.", "parameters": {"type": "object", "properties": {"repo_url": {"type": "string"}, "notify": {"type": "boolean"}}, "required": []}}},
]


def make_handlers(ctx: dict) -> dict[str, Callable[..., Any]]:
  p = ctx.get("params")
  stationary_check = ctx.get("stationary_check")

  def h_trigger(args):
    err = stationary_check("run_shell")
    if err:
      return err
    from ai.tools.github_actions_tools import trigger_github_workflow
    return trigger_github_workflow(
      repo_url=str(args.get("repo_url", "") or ""),
      workflow=str(args.get("workflow", "") or "build.yaml"),
      ref=str(args.get("ref", "") or "master-c3"),
      confirm=bool(args.get("confirm")),
      params=p,
    )

  def h_rerun(args):
    from ai.tools.github_actions_tools import rerun_github_workflow
    return rerun_github_workflow(
      run_id=int(args.get("run_id") or 0),
      repo_url=str(args.get("repo_url", "") or ""),
      confirm=bool(args.get("confirm")),
      params=p,
    )

  def h_wait(args):
    from ai.tools.github_actions_tools import wait_github_workflow
    return wait_github_workflow(
      run_id=int(args.get("run_id") or 0),
      repo_url=str(args.get("repo_url", "") or ""),
      workflow=str(args.get("workflow", "") or "build.yaml"),
      ref=str(args.get("ref", "") or ""),
      timeout_seconds=int(args.get("timeout_seconds", 1800) or 1800),
      poll_seconds=int(args.get("poll_seconds", 30) or 30),
      notify_on_complete=bool(args.get("notify_on_complete", True)),
      params=p,
    )

  def h_health(args):
    from ai.tools.github_actions_tools import check_github_runner_health
    return check_github_runner_health(
      repo_url=str(args.get("repo_url", "") or ""),
      notify=bool(args.get("notify")),
      params=p,
    )

  return {
    "trigger_github_workflow": h_trigger,
    "rerun_github_workflow": h_rerun,
    "wait_github_workflow": h_wait,
    "check_github_runner_health": h_health,
  }
