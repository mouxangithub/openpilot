"""Git commit/push + GitHub Pull Request plugin."""

from __future__ import annotations

from typing import Any, Callable


TOOL_META: dict[str, dict[str, Any]] = {
  "git_publish_pull_request": {"label": "发布 PR", "group": "write", "default_enabled": True, "driving": False},
  "list_github_pull_requests": {"label": "PR 列表", "group": "read", "default_enabled": True, "driving": True},
  "get_github_pull_request": {"label": "PR 详情", "group": "read", "default_enabled": True, "driving": True},
  "review_github_pull_request": {"label": "PR 审阅", "group": "write", "default_enabled": True, "driving": False},
  "merge_github_pull_request": {"label": "合并 PR", "group": "write", "default_enabled": True, "driving": False},
  "auto_review_pull_request": {"label": "PR 自动审阅", "group": "write", "default_enabled": True, "driving": False},
  "report_bug_and_publish_pr": {"label": "Bug 报告 PR", "group": "write", "default_enabled": True, "driving": False},
  "publish_changes": {"label": "发布改动", "group": "write", "default_enabled": True, "driving": False},
  "discover_publish_units": {"label": "扫描发布单元", "group": "read", "default_enabled": True, "driving": True},
  "set_forge_token": {"label": "配置 Forge Token", "group": "write", "default_enabled": True, "driving": False},
  "forge_auth_status": {"label": "Forge 凭据状态", "group": "read", "default_enabled": True, "driving": True},
  "discover_issue_templates": {"label": "Issue 模板", "group": "read", "default_enabled": True, "driving": True},
  "create_issue": {"label": "创建 Issue", "group": "write", "default_enabled": True, "driving": False},
  "report_issue": {"label": "报告 Issue", "group": "write", "default_enabled": True, "driving": False},
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
  {
    "type": "function",
    "function": {
      "name": "git_publish_pull_request",
      "description": (
        "Offroad: commit local changes, push branch, open GitHub Pull Request. "
        "Auto-creates ai/* branch from protected base. Requires git credentials + ai_github_actions_pat (repo scope). "
        "confirm=true to execute. See ai/docs/GIT_PR.md."
      ),
      "parameters": {
        "type": "object",
        "properties": {
          "title": {"type": "string"},
          "body": {"type": "string"},
          "base_branch": {"type": "string", "description": "Target branch, default master-c3"},
          "branch": {"type": "string", "description": "Head branch; auto ai/* if empty"},
          "commit_message": {"type": "string"},
          "paths": {"type": "array", "items": {"type": "string"}},
          "draft": {"type": "boolean"},
          "remote": {"type": "string"},
          "repo_url": {"type": "string"},
          "repo_target": {
            "type": "string",
            "enum": ["openpilot", "assistant", "ai"],
            "description": "openpilot 或独立 ai 仓库",
          },
          "severity": {"type": "string"},
          "request_auto_fix": {"type": "boolean"},
          "confirm": {"type": "boolean"},
        },
        "required": [],
      },
    },
  },
  {
    "type": "function",
    "function": {
      "name": "list_github_pull_requests",
      "description": "List GitHub pull requests. Requires ai_github_actions_pat in config.json.",
      "parameters": {
        "type": "object",
        "properties": {
          "repo_url": {"type": "string"},
          "state": {"type": "string", "enum": ["open", "closed", "all"]},
          "base": {"type": "string"},
          "head": {"type": "string"},
          "per_page": {"type": "integer"},
        },
        "required": [],
      },
    },
  },
  {
    "type": "function",
    "function": {
      "name": "get_github_pull_request",
      "description": "Get PR details and changed files list.",
      "parameters": {
        "type": "object",
        "properties": {"pull_number": {"type": "integer"}, "repo_url": {"type": "string"}},
        "required": ["pull_number"],
      },
    },
  },
  {
    "type": "function",
    "function": {
      "name": "review_github_pull_request",
      "description": "Post PR review (COMMENT/APPROVE/REQUEST_CHANGES). confirm=true required.",
      "parameters": {
        "type": "object",
        "properties": {
          "pull_number": {"type": "integer"},
          "body": {"type": "string"},
          "event": {"type": "string", "enum": ["COMMENT", "APPROVE", "REQUEST_CHANGES"]},
          "repo_url": {"type": "string"},
          "confirm": {"type": "boolean"},
        },
        "required": ["pull_number", "body"],
      },
    },
  },
  {
    "type": "function",
    "function": {
      "name": "merge_github_pull_request",
      "description": (
        "Merge PR (squash by default). Protected bases only accept ai/* head branches. confirm=true required."
      ),
      "parameters": {
        "type": "object",
        "properties": {
          "pull_number": {"type": "integer"},
          "merge_method": {"type": "string", "enum": ["merge", "squash", "rebase"]},
          "repo_url": {"type": "string"},
          "repo_target": {"type": "string", "enum": ["openpilot", "assistant", "ai"]},
          "confirm": {"type": "boolean"},
        },
        "required": ["pull_number"],
      },
    },
  },
  {
    "type": "function",
    "function": {
      "name": "auto_review_pull_request",
      "description": (
        "Summarize PR diff and post review comment; optional approve + merge_if_clean. confirm=true required."
      ),
      "parameters": {
        "type": "object",
        "properties": {
          "pull_number": {"type": "integer"},
          "repo_url": {"type": "string"},
          "approve": {"type": "boolean"},
          "merge_if_clean": {"type": "boolean"},
          "confirm": {"type": "boolean"},
        },
        "required": ["pull_number"],
      },
    },
  },
  {
    "type": "function",
    "function": {
      "name": "report_bug_and_publish_pr",
      "description": (
        "Structured bug report from op助手 → PR to mouxangithub/ai (default) or openpilot. "
        "Auto-labels ai-auto-review. confirm=true to execute."
      ),
      "parameters": {
        "type": "object",
        "properties": {
          "repo_target": {"type": "string", "enum": ["assistant", "ai", "openpilot"]},
          "title": {"type": "string"},
          "repro_steps": {"type": "string"},
          "expected": {"type": "string"},
          "actual": {"type": "string"},
          "severity": {"type": "string", "enum": ["ui", "docs", "typo", "web", "logic", "crash"]},
          "attach_audit": {"type": "boolean"},
          "request_auto_fix": {"type": "boolean"},
          "paths": {"type": "array", "items": {"type": "string"}},
          "confirm": {"type": "boolean"},
        },
        "required": [],
      },
    },
  },
  {
    "type": "function",
    "function": {
      "name": "publish_changes",
      "description": (
        "Offroad: commit, push, and open PR/MR for a publish unit (openpilot, opendbc, assistant, …). "
        "Assistant defaults to mouxangithub/ai upstream; project repos use current_remote or user_fork. "
        "confirm=false previews; confirm=true executes. See ai/docs/PUBLISH.md."
      ),
      "parameters": {
        "type": "object",
        "properties": {
          "unit_id": {"type": "string", "description": "openpilot, assistant, opendbc, panda, …"},
          "target_mode": {
            "type": "string",
            "enum": ["", "assistant_upstream", "current_remote", "user_fork"],
          },
          "title": {"type": "string"},
          "body": {"type": "string"},
          "base_branch": {"type": "string"},
          "branch": {"type": "string"},
          "commit_message": {"type": "string"},
          "paths": {"type": "array", "items": {"type": "string"}},
          "draft": {"type": "boolean"},
          "remote": {"type": "string"},
          "repo_url": {"type": "string"},
          "confirm": {"type": "boolean"},
        },
        "required": [],
      },
    },
  },
  {
    "type": "function",
    "function": {
      "name": "discover_publish_units",
      "description": "List git publish units with dirty file counts (openpilot, submodules, assistant).",
      "parameters": {
        "type": "object",
        "properties": {"dirty_only": {"type": "boolean"}},
        "required": [],
      },
    },
  },
  {
    "type": "function",
    "function": {
      "name": "set_forge_token",
      "description": "Store or clear forge API token (github/gitee/gitlab) in config.json. confirm=true required.",
      "parameters": {
        "type": "object",
        "properties": {
          "forge": {"type": "string", "enum": ["github", "gitee", "gitlab"]},
          "token": {"type": "string"},
          "confirm": {"type": "boolean"},
        },
        "required": [],
      },
    },
  },
  {
    "type": "function",
    "function": {
      "name": "forge_auth_status",
      "description": "Check whether forge token is configured and valid (never returns token).",
      "parameters": {
        "type": "object",
        "properties": {
          "forge": {"type": "string", "enum": ["github", "gitee", "gitlab"]},
          "repo_url": {"type": "string"},
        },
        "required": [],
      },
    },
  },
  {
    "type": "function",
    "function": {
      "name": "discover_issue_templates",
      "description": "List issue templates (builtin + repo .github/ISSUE_TEMPLATE). See ai/docs/ISSUES.md.",
      "parameters": {
        "type": "object",
        "properties": {
          "unit_id": {"type": "string"},
          "repo_url": {"type": "string"},
        },
        "required": [],
      },
    },
  },
  {
    "type": "function",
    "function": {
      "name": "create_issue",
      "description": (
        "Create GitHub/Gitee issue from template. Uses forge token. "
        "confirm=false previews; confirm=true creates. See ai/docs/ISSUES.md."
      ),
      "parameters": {
        "type": "object",
        "properties": {
          "unit_id": {"type": "string"},
          "target_mode": {"type": "string"},
          "repo_url": {"type": "string"},
          "template_id": {"type": "string"},
          "title": {"type": "string"},
          "body": {"type": "string"},
          "fields": {"type": "object"},
          "labels": {"type": "array", "items": {"type": "string"}},
          "attach_audit": {"type": "boolean"},
          "confirm": {"type": "boolean"},
        },
        "required": [],
      },
    },
  },
  {
    "type": "function",
    "function": {
      "name": "report_issue",
      "description": (
        "Structured bug/feature/suggestion → GitHub/Gitee issue (not PR). "
        "confirm=true to create."
      ),
      "parameters": {
        "type": "object",
        "properties": {
          "kind": {"type": "string", "enum": ["bug", "feature", "suggestion", "assistant", "pc"]},
          "unit_id": {"type": "string"},
          "title": {"type": "string"},
          "repro_steps": {"type": "string"},
          "expected": {"type": "string"},
          "actual": {"type": "string"},
          "summary": {"type": "string"},
          "proposal": {"type": "string"},
          "severity": {"type": "string"},
          "attach_audit": {"type": "boolean"},
          "confirm": {"type": "boolean"},
        },
        "required": [],
      },
    },
  },
]


def make_handlers(ctx: dict) -> dict[str, Callable[..., Any]]:
  p = ctx.get("params")
  stationary_check = ctx.get("stationary_check")
  needs_confirm = ctx.get("needs_confirm")

  def _git_write_gate(args, hint: str):
    if not args.get("confirm") and needs_confirm():
      return {"ok": True, "needs_confirmation": True, "hint": hint}
    err = stationary_check("write_param")
    return err

  def h_publish(args):
    from ai.tools.git_pr_tools import git_publish_pull_request
    paths = args.get("paths")
    path_list = [str(x) for x in paths] if isinstance(paths, list) else None
    common = dict(
      title=str(args.get("title", "") or ""),
      body=str(args.get("body", "") or ""),
      base_branch=str(args.get("base_branch", "") or ""),
      branch=str(args.get("branch", "") or ""),
      commit_message=str(args.get("commit_message", "") or ""),
      paths=path_list,
      draft=bool(args.get("draft")),
      remote=str(args.get("remote", "") or "origin"),
      repo_url=str(args.get("repo_url", "") or ""),
      repo_target=str(args.get("repo_target", "") or "openpilot"),
      severity=str(args.get("severity", "") or ""),
      request_auto_fix=bool(args.get("request_auto_fix")),
      params=p,
    )
    if not args.get("confirm") and needs_confirm():
      return git_publish_pull_request(**common, confirm=False)
    err = stationary_check("write_param")
    if err:
      return err
    return git_publish_pull_request(**common, confirm=True)

  def h_list_prs(args):
    from ai.tools.git_pr_tools import list_github_pull_requests
    return list_github_pull_requests(
      repo_url=str(args.get("repo_url", "") or ""),
      state=str(args.get("state", "") or "open"),
      base=str(args.get("base", "") or ""),
      head=str(args.get("head", "") or ""),
      per_page=int(args.get("per_page", 10) or 10),
      params=p,
    )

  def h_get_pr(args):
    from ai.tools.git_pr_tools import get_github_pull_request
    return get_github_pull_request(
      pull_number=int(args.get("pull_number") or 0),
      repo_url=str(args.get("repo_url", "") or ""),
      params=p,
    )

  def h_review(args):
    gate = _git_write_gate(args, "Set confirm=true to post PR review.")
    if gate:
      return gate
    from ai.tools.git_pr_tools import review_github_pull_request
    return review_github_pull_request(
      pull_number=int(args.get("pull_number") or 0),
      body=str(args.get("body", "") or ""),
      event=str(args.get("event", "") or "COMMENT"),
      repo_url=str(args.get("repo_url", "") or ""),
      confirm=True,
      params=p,
    )

  def h_merge(args):
    gate = _git_write_gate(args, "Set confirm=true to merge PR.")
    if gate:
      return gate
    from ai.tools.git_pr_tools import merge_github_pull_request
    return merge_github_pull_request(
      pull_number=int(args.get("pull_number") or 0),
      merge_method=str(args.get("merge_method", "") or "squash"),
      repo_url=str(args.get("repo_url", "") or ""),
      repo_target=str(args.get("repo_target", "") or "openpilot"),
      confirm=True,
      params=p,
    )

  def h_report_bug(args):
    from ai.tools.bug_report_tools import report_bug_and_publish_pr
    paths = args.get("paths")
    path_list = [str(x) for x in paths] if isinstance(paths, list) else None
    common = dict(
      repo_target=str(args.get("repo_target", "") or "assistant"),
      title=str(args.get("title", "") or ""),
      repro_steps=str(args.get("repro_steps", "") or ""),
      expected=str(args.get("expected", "") or ""),
      actual=str(args.get("actual", "") or ""),
      severity=str(args.get("severity", "") or "ui"),
      attach_audit=bool(args.get("attach_audit", True)),
      request_auto_fix=bool(args.get("request_auto_fix")),
      paths=path_list,
      params=p,
    )
    if not args.get("confirm") and needs_confirm():
      return report_bug_and_publish_pr(**common, confirm=False)
    err = stationary_check("write_param")
    if err:
      return err
    return report_bug_and_publish_pr(**common, confirm=True)

  def h_publish_changes(args):
    from ai.tools.publish_tools import publish_changes
    paths = args.get("paths")
    path_list = [str(x) for x in paths] if isinstance(paths, list) else None
    common = dict(
      unit_id=str(args.get("unit_id", "") or "openpilot"),
      target_mode=str(args.get("target_mode", "") or ""),
      title=str(args.get("title", "") or ""),
      body=str(args.get("body", "") or ""),
      base_branch=str(args.get("base_branch", "") or ""),
      branch=str(args.get("branch", "") or ""),
      commit_message=str(args.get("commit_message", "") or ""),
      paths=path_list,
      draft=bool(args.get("draft")),
      remote=str(args.get("remote", "") or ""),
      repo_url=str(args.get("repo_url", "") or ""),
      params=p,
    )
    if not args.get("confirm") and needs_confirm():
      return publish_changes(**common, confirm=False)
    err = stationary_check("write_param")
    if err:
      return err
    return publish_changes(**common, confirm=True)

  def h_discover_units(args):
    from ai.tools.publish_units import discover_publish_units
    return discover_publish_units(include_clean=not bool(args.get("dirty_only")))

  def h_set_forge_token(args):
    gate = _git_write_gate(args, "Set confirm=true to store forge token.")
    if gate:
      return gate
    from ai.tools.publish_tools import set_forge_token_tool
    return set_forge_token_tool(
      forge=str(args.get("forge", "") or "github"),
      token=str(args.get("token", "") or ""),
      confirm=True,
    )

  def h_forge_auth(args):
    from ai.tools.forge import forge_auth_status
    return forge_auth_status(
      str(args.get("forge", "") or "github"),
      repo_url=str(args.get("repo_url", "") or ""),
    )

  def h_auto_review(args):
    gate = _git_write_gate(args, "Set confirm=true to auto-review PR.")
    if gate:
      return gate
    from ai.tools.git_pr_tools import auto_review_pull_request
    return auto_review_pull_request(
      pull_number=int(args.get("pull_number") or 0),
      repo_url=str(args.get("repo_url", "") or ""),
      approve=bool(args.get("approve")),
      merge_if_clean=bool(args.get("merge_if_clean")),
      confirm=True,
      params=p,
    )

  def h_discover_issue_templates(args):
    from ai.tools.issue_tools import discover_issue_templates
    return discover_issue_templates(
      unit_id=str(args.get("unit_id", "") or "assistant"),
      repo_url=str(args.get("repo_url", "") or ""),
    )

  def h_create_issue(args):
    from ai.tools.issue_tools import create_issue
    fields = args.get("fields")
    field_map = {str(k): str(v) for k, v in fields.items()} if isinstance(fields, dict) else None
    labels = args.get("labels")
    label_list = [str(x) for x in labels] if isinstance(labels, list) else None
    common = dict(
      unit_id=str(args.get("unit_id", "") or "assistant"),
      target_mode=str(args.get("target_mode", "") or ""),
      repo_url=str(args.get("repo_url", "") or ""),
      template_id=str(args.get("template_id", "") or "bug"),
      title=str(args.get("title", "") or ""),
      body=str(args.get("body", "") or ""),
      fields=field_map,
      labels=label_list,
      attach_audit=bool(args.get("attach_audit", True)),
      params=p,
    )
    if not args.get("confirm") and needs_confirm():
      return create_issue(**common, confirm=False)
    err = stationary_check("write_param")
    if err:
      return err
    return create_issue(**common, confirm=True)

  def h_report_issue(args):
    from ai.tools.issue_tools import report_issue
    common = dict(
      kind=str(args.get("kind", "") or "bug"),
      unit_id=str(args.get("unit_id", "") or ""),
      title=str(args.get("title", "") or ""),
      repro_steps=str(args.get("repro_steps", "") or ""),
      expected=str(args.get("expected", "") or ""),
      actual=str(args.get("actual", "") or ""),
      summary=str(args.get("summary", "") or ""),
      proposal=str(args.get("proposal", "") or ""),
      severity=str(args.get("severity", "") or "ui"),
      attach_audit=bool(args.get("attach_audit", True)),
      params=p,
    )
    if not args.get("confirm") and needs_confirm():
      return report_issue(**common, confirm=False)
    err = stationary_check("write_param")
    if err:
      return err
    return report_issue(**common, confirm=True)

  return {
    "git_publish_pull_request": h_publish,
    "list_github_pull_requests": h_list_prs,
    "get_github_pull_request": h_get_pr,
    "review_github_pull_request": h_review,
    "merge_github_pull_request": h_merge,
    "auto_review_pull_request": h_auto_review,
    "report_bug_and_publish_pr": h_report_bug,
    "publish_changes": h_publish_changes,
    "discover_publish_units": h_discover_units,
    "set_forge_token": h_set_forge_token,
    "forge_auth_status": h_forge_auth,
    "discover_issue_templates": h_discover_issue_templates,
    "create_issue": h_create_issue,
    "report_issue": h_report_issue,
  }
