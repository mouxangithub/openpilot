"""GitHub Actions API tools for op助手 (workflow runs, runners, PAT)."""

from __future__ import annotations

import subprocess
import time
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
  from openpilot.common.params import Params

from ai.tools.domains.devops.github_api_client import (
  DEFAULT_REPO,
  PAT_KEY,
  cancel_workflow_run,
  find_latest_run_for_ref,
  get_pat,
  get_workflow_run,
  list_repo_runners,
  list_workflow_runs,
  parse_repo_url,
  rerun_workflow_run,
  set_pat,
  trigger_workflow_dispatch,
  verify_token,
)
from ai.tools.domains.devops.github_runner_tools import github_runner_status, resolve_service_name, runner_dir


def _params_or_none(params: "Params | None") -> "Params | None":
  if params is not None:
    return params
  try:
    from openpilot.common.params import Params
    return Params()
  except Exception:
    return None


def _require_pat(params: "Params | None") -> tuple[str | None, dict[str, Any] | None]:
  params = _params_or_none(params)
  token = get_pat(params)
  if not token:
    return None, {
      "ok": False,
      "error": "github_pat_not_configured",
      "hint": "Create a GitHub PAT (repo + actions) and call set_github_actions_pat(token=..., confirm=true).",
      "doc": "ai/docs/GITHUB_RUNNER.md",
    }
  return token, None


def github_actions_auth_status(params: "Params | None" = None, *, repo_url: str = DEFAULT_REPO) -> dict[str, Any]:
  """Check whether a PAT is stored and valid (token never returned)."""
  params = _params_or_none(params)
  token = get_pat(params)
  owner, repo = parse_repo_url(repo_url)
  out: dict[str, Any] = {
    "ok": True,
    "configured": bool(token),
    "repo": f"{owner}/{repo}",
    "repo_url": repo_url or DEFAULT_REPO,
    "config_key": PAT_KEY,
    "storage": "config.json",
    "doc": "ai/docs/GITHUB_RUNNER.md",
  }
  if not token:
    out["valid"] = False
    out["hint"] = "PAT not set. Scopes: repo, actions (read/write for cancel)."
    return out
  check = verify_token(token)
  out["valid"] = bool(check.get("valid"))
  if check.get("valid"):
    out["github_user"] = check.get("login")
  else:
    out["error_detail"] = check.get("message") or check.get("error")
    out["hint"] = "Token invalid or expired — set_github_actions_pat with a new PAT."
  return out


def set_github_actions_pat(
  *,
  token: str = "",
  confirm: bool = False,
  params: "Params | None" = None,
) -> dict[str, Any]:
  """Store or clear ai_github_actions_pat in config.json. Never logs or returns the token."""
  del params
  token = (token or "").strip()
  clearing = not token
  preview = {
    "action": "clear_pat" if clearing else "store_pat",
    "config_key": PAT_KEY,
    "storage": "config.json",
    "token_length": len(token) if token else 0,
    "hint": "Fine-grained or classic PAT with repo + actions scope.",
  }
  if not confirm:
    return {"ok": True, "needs_confirmation": True, "preview": preview}
  if clearing:
    set_pat(None, None)
    return {"ok": True, "configured": False, "cleared": True}
  if len(token) < 20:
    return {"ok": False, "error": "token looks too short"}
  check = verify_token(token)
  if not check.get("valid"):
    return {
      "ok": False,
      "error": "token_verification_failed",
      "message": check.get("message") or check.get("error"),
    }
  set_pat(None, token)
  return {
    "ok": True,
    "configured": True,
    "github_user": check.get("login"),
    "cleared": False,
  }


def list_github_workflow_runs(
  *,
  repo_url: str = DEFAULT_REPO,
  workflow: str = "build.yaml",
  status: str | None = None,
  branch: str | None = None,
  per_page: int = 10,
  params: "Params | None" = None,
) -> dict[str, Any]:
  token, err = _require_pat(params)
  if err:
    return err
  owner, repo = parse_repo_url(repo_url)
  data = list_workflow_runs(
    token,
    owner,
    repo,
    workflow=workflow or None,
    status=status or None,
    branch=branch or None,
    per_page=per_page,
  )
  if not data.get("ok", True) and data.get("error"):
    return data
  return {
    **data,
    "repo": f"{owner}/{repo}",
    "workflow": workflow,
    "filters": {"status": status, "branch": branch},
  }


def get_github_workflow_run(
  *,
  run_id: int,
  repo_url: str = DEFAULT_REPO,
  params: "Params | None" = None,
) -> dict[str, Any]:
  if not run_id:
    return {"ok": False, "error": "run_id required"}
  token, err = _require_pat(params)
  if err:
    return err
  owner, repo = parse_repo_url(repo_url)
  data = get_workflow_run(token, owner, repo, int(run_id))
  if data.get("ok"):
    data["repo"] = f"{owner}/{repo}"
  return data


def cancel_github_workflow_run(
  *,
  run_id: int,
  repo_url: str = DEFAULT_REPO,
  confirm: bool = False,
  params: "Params | None" = None,
) -> dict[str, Any]:
  if not run_id:
    return {"ok": False, "error": "run_id required"}
  owner, repo = parse_repo_url(repo_url)
  preview = {
    "action": "cancel_workflow_run",
    "run_id": int(run_id),
    "repo": f"{owner}/{repo}",
    "hint": "Cancels all pending/in_progress jobs in this run.",
  }
  if not confirm:
    return {"ok": True, "needs_confirmation": True, "preview": preview}
  token, err = _require_pat(params)
  if err:
    return err
  return cancel_workflow_run(token, owner, repo, int(run_id))


def list_github_runners(
  *,
  repo_url: str = DEFAULT_REPO,
  params: "Params | None" = None,
) -> dict[str, Any]:
  token, err = _require_pat(params)
  if err:
    return err
  owner, repo = parse_repo_url(repo_url)
  data = list_repo_runners(token, owner, repo)
  if data.get("ok"):
    data["repo"] = f"{owner}/{repo}"
    local = github_runner_status(params)
    data["local_runner"] = {
      "installed": local.get("installed"),
      "service_name": local.get("service_name"),
      "systemd_running": (local.get("systemd") or {}).get("running"),
      "runner_dir": local.get("runner_dir"),
    }
  return data


def stop_github_runner_service(*, confirm: bool = False, params: "Params | None" = None) -> dict[str, Any]:
  """Stop local systemd runner service (does not uninstall)."""
  status = github_runner_status(params)
  service = status.get("service_name") or resolve_service_name()
  preview = {
    "action": "systemctl_stop",
    "service_name": service,
    "runner_dir": str(runner_dir()),
    "hint": "Stops Runner.Listener; manager may restart if EnableGithubRunner gates pass.",
  }
  if not confirm:
    return {"ok": True, "needs_confirmation": True, "preview": preview}
  if not status.get("installed"):
    return {"ok": False, "error": "runner_not_installed"}
  try:
    proc = subprocess.run(
      ["sudo", "systemctl", "stop", service],
      capture_output=True,
      text=True,
      timeout=60,
    )
    return {
      "ok": proc.returncode == 0,
      "returncode": proc.returncode,
      "service_name": service,
      "stderr_tail": (proc.stderr or "")[-1000:],
      "next": "github_runner_status",
    }
  except Exception as e:
    return {"ok": False, "error": str(e), "preview": preview}


def github_api_snapshot(params: "Params | None" = None, *, repo_url: str = DEFAULT_REPO) -> dict[str, Any] | None:
  """Lightweight GitHub API summary for github_runner_status (no token in output)."""
  token = get_pat(_params_or_none(params))
  if not token:
    return None
  owner, repo = parse_repo_url(repo_url)
  runners = list_repo_runners(token, owner, repo)
  runs = list_workflow_runs(token, owner, repo, workflow="build.yaml", status="in_progress", per_page=5)
  if not runners.get("ok") and not runs.get("ok"):
    return {
      "configured": True,
      "api_reachable": False,
      "error": runners.get("message") or runs.get("message") or "github_api_error",
    }
  return {
    "configured": True,
    "api_reachable": True,
    "repo": f"{owner}/{repo}",
    "runners_online": len([r for r in (runners.get("runners") or []) if r.get("status") == "online"]),
    "runners_busy": runners.get("busy_runners") or [],
    "in_progress_runs": runs.get("in_progress") or runs.get("runs") or [],
  }


def trigger_github_workflow(
  *,
  repo_url: str = DEFAULT_REPO,
  workflow: str = "build.yaml",
  ref: str = "master-c3",
  confirm: bool = False,
  params: "Params | None" = None,
) -> dict[str, Any]:
  owner, repo = parse_repo_url(repo_url)
  preview = {
    "action": "workflow_dispatch",
    "workflow": workflow,
    "ref": ref,
    "repo": f"{owner}/{repo}",
  }
  if not confirm:
    return {"ok": True, "needs_confirmation": True, "preview": preview}
  token, err = _require_pat(params)
  if err:
    return err
  out = trigger_workflow_dispatch(token, owner, repo, workflow=workflow, ref=ref)
  if out.get("ok"):
    out["hint"] = "Dispatch queued; use wait_github_workflow or list_github_workflow_runs to track."
  return out


def rerun_github_workflow(
  *,
  run_id: int,
  repo_url: str = DEFAULT_REPO,
  confirm: bool = False,
  params: "Params | None" = None,
) -> dict[str, Any]:
  if not run_id:
    return {"ok": False, "error": "run_id required"}
  owner, repo = parse_repo_url(repo_url)
  preview = {"action": "rerun_workflow_run", "run_id": int(run_id), "repo": f"{owner}/{repo}"}
  if not confirm:
    return {"ok": True, "needs_confirmation": True, "preview": preview}
  token, err = _require_pat(params)
  if err:
    return err
  return rerun_workflow_run(token, owner, repo, int(run_id))


def wait_github_workflow(
  *,
  run_id: int = 0,
  repo_url: str = DEFAULT_REPO,
  workflow: str = "build.yaml",
  ref: str = "",
  timeout_seconds: int = 1800,
  poll_seconds: int = 30,
  notify_on_complete: bool = True,
  params: "Params | None" = None,
) -> dict[str, Any]:
  """Poll workflow run until completed or timeout."""
  token, err = _require_pat(params)
  if err:
    return err
  owner, repo = parse_repo_url(repo_url)
  rid = int(run_id or 0)
  if not rid and ref:
    latest = find_latest_run_for_ref(token, owner, repo, workflow=workflow, ref=ref)
    if not latest.get("ok"):
      return latest
    rid = int(latest["run"]["id"])
  if not rid:
    return {"ok": False, "error": "run_id or ref required"}

  deadline = time.time() + max(30, int(timeout_seconds))
  poll_seconds = max(10, min(int(poll_seconds), 120))
  last: dict[str, Any] = {}
  while time.time() < deadline:
    data = get_workflow_run(token, owner, repo, rid)
    if not data.get("ok"):
      return data
    run = data.get("run") or {}
    last = run
    status = run.get("status")
    if status == "completed":
      conclusion = run.get("conclusion")
      result = {
        "ok": True,
        "completed": True,
        "run_id": rid,
        "conclusion": conclusion,
        "run": run,
        "jobs": data.get("jobs") or [],
        "success": conclusion == "success",
      }
      if notify_on_complete:
        try:
          from ai.tools.domains.platform.notifications import push_notification
          level = "info" if conclusion == "success" else "error"
          push_notification(
            f"CI {conclusion or 'done'}",
            f"Workflow run {rid} on {ref or run.get('head_branch') or ''}",
            level=level,
          )
        except Exception:
          pass
      return result
    time.sleep(poll_seconds)
  return {
    "ok": True,
    "completed": False,
    "timed_out": True,
    "run_id": rid,
    "last_status": last.get("status"),
    "run": last,
  }


def check_github_runner_health(
  *,
  repo_url: str = DEFAULT_REPO,
  params: "Params | None" = None,
  notify: bool = False,
) -> dict[str, Any]:
  """Combine local runner status + GitHub API runners/in-progress runs."""
  from ai.tools.domains.devops.github_runner_tools import github_runner_status

  local = github_runner_status(params)
  out: dict[str, Any] = {
    "ok": True,
    "local": {
      "installed": local.get("installed"),
      "service_running": (local.get("systemd") or {}).get("running"),
      "manager_would_start": local.get("manager_would_start"),
      "enable_param": (local.get("param_gates") or {}).get("EnableGithubRunner"),
    },
    "issues": [],
  }
  token = get_pat(_params_or_none(params))
  if token:
    owner, repo = parse_repo_url(repo_url)
    runners = list_repo_runners(token, owner, repo)
    if runners.get("ok"):
      out["github"] = {
        "runners_online": len([r for r in runners.get("runners") or [] if r.get("status") == "online"]),
        "busy": runners.get("busy_runners") or [],
        "offline": runners.get("offline_runners") or [],
      }
      if runners.get("offline_runners"):
        out["issues"].append("github_runners_offline")
      if not runners.get("runners"):
        out["issues"].append("no_github_runners")
    failed = list_workflow_runs(token, owner, repo, workflow="build.yaml", status="completed", per_page=3)
    if failed.get("ok"):
      recent_fail = [r for r in (failed.get("runs") or []) if r.get("conclusion") == "failure"]
      if recent_fail:
        out["recent_failures"] = recent_fail[:2]
        out["issues"].append("recent_ci_failure")
  else:
    out["github"] = {"configured": False, "hint": "set_github_actions_pat for remote CI checks"}

  if not local.get("installed"):
    out["issues"].append("runner_not_installed")
  elif not (local.get("systemd") or {}).get("running"):
    out["issues"].append("local_service_not_running")

  out["healthy"] = len(out["issues"]) == 0
  if notify and out["issues"]:
    try:
      from ai.tools.domains.platform.notifications import push_notification
      push_notification("Runner/CI 告警", ", ".join(out["issues"]), level="warn")
    except Exception:
      pass
  return out
