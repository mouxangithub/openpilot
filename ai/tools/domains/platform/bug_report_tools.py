"""Structured bug report → Pull Request for op助手 Web / openpilot."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from ai.common.repo_targets import repo_target_meta, suggest_pr_labels
from ai.tools.domains.devops.git_pr_tools import git_publish_pull_request
from ai.system.host_env import get_host_environment

if TYPE_CHECKING:
  from openpilot.common.params import Params


def _audit_excerpt(limit: int = 15) -> list[dict[str, Any]]:
  try:
    from ai.tools.domains.platform.audit_store import list_audit_trail
    res = list_audit_trail(limit=limit)
    return res.get("entries") or res.get("audit") or []
  except Exception:
    return []


def report_bug_and_publish_pr(
  *,
  repo_target: str = "assistant",
  title: str = "",
  repro_steps: str = "",
  expected: str = "",
  actual: str = "",
  severity: str = "ui",
  attach_audit: bool = True,
  request_auto_fix: bool = False,
  paths: list[str] | None = None,
  confirm: bool = False,
  params: "Params | None" = None,
) -> dict[str, Any]:
  """Capture bug context and publish PR to mouxangithub/ai or openpilot."""
  meta = repo_target_meta(repo_target)
  env = get_host_environment()
  audit = _audit_excerpt() if attach_audit else []

  body_parts = [
    "## Bug report (op助手)",
    "",
    "### Reproduction",
    (repro_steps or "_(not provided)_").strip(),
    "",
    "### Expected",
    (expected or "_(not provided)_").strip(),
    "",
    "### Actual",
    (actual or "_(not provided)_").strip(),
    "",
    f"**Severity**: `{severity}`",
    "",
    "### Environment",
    f"- Host: `{env.get('platform')}` / `{env.get('host_role')}`",
    f"- openpilot_root: `{env.get('openpilot_root')}`",
    f"- assistant_repo: `{meta.get('repo_root')}`",
    "",
  ]
  if audit:
    body_parts.append("### Recent audit trail")
    for entry in audit[:10]:
      body_parts.append(f"- `{entry.get('tool', entry.get('action', '?'))}` ok={entry.get('ok')}")
    body_parts.append("")

  body_parts.extend([
    "### Automation",
    "PR labeled `ai-auto-review`; Actions will post AI review.",
    "Low-risk UI fixes may get `ai-safe-merge` for auto squash merge.",
    "",
    f"Target: {meta.get('pulls_url')}",
  ])

  pr_title = (title or "").strip()
  if not pr_title:
    pr_title = f"fix(ai): {severity} bug from op助手"

  path_list = paths
  if repo_target in ("assistant", "ai", "op-assistant", "op助手") and not path_list:
    path_list = None  # commit all in ai repo clone

  preview = {
    "action": "report_bug_and_publish_pr",
    "repo_target": meta.get("repo_target"),
    "repo_url": meta.get("repo_url"),
    "title": pr_title,
    "severity": severity,
    "labels": suggest_pr_labels(
      repo_target=repo_target,
      severity=severity,
      request_auto_fix=request_auto_fix,
    ),
    "attach_audit": attach_audit,
    "audit_entries": len(audit),
  }
  if not confirm:
    return {"ok": True, "needs_confirmation": True, "preview": preview}

  return git_publish_pull_request(
    title=pr_title,
    body="\n".join(body_parts),
    repo_target=repo_target,
    paths=path_list,
    severity=severity,
    request_auto_fix=request_auto_fix,
    confirm=True,
    params=params,
  )
