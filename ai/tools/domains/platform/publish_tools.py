"""Unified code publish: commit, push, open PR/MR on GitHub/Gitee."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING

from ai.common.publish_config import (
  assistant_upstream,
  project_default_mode,
  project_fork_config,
)
from ai.common.repo_targets import suggest_pr_labels
from ai.tools.domains.vehicle.adaptation_pr_tools import generate_adaptation_pr_draft
from ai.tools.forge import (
  forge_auth_status,
  get_forge_client,
  get_forge_token,
  infer_forge_from_url,
  parse_repo_url,
  repo_slug,
  set_forge_token,
)
from ai.tools.domains.devops.git_remote_tools import git_push_at, git_remote_ensure, git_status_at
from ai.tools.domains.devops.git_repo_context import git_repo_context
from ai.tools.domains.devops.git_tools import (
  git_commit,
  git_create_branch,
  git_diff,
  git_status,
  _git,
)
from ai.tools.domains.platform.publish_units import discover_publish_units, get_unit

if TYPE_CHECKING:
  from openpilot.common.params import Params

PROTECTED_BASES = frozenset({"master", "main", "master-c3", "release", "production"})
AI_BRANCH_PREFIX = "ai/"


def _slug(text: str, max_len: int = 32) -> str:
  s = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "change").lower()).strip("-")
  return (s[:max_len] or "change").strip("-")


def _require_forge_token(forge: str) -> tuple[str | None, dict[str, Any] | None]:
  token = get_forge_token(forge)
  if not token:
    return None, {
      "ok": False,
      "error": "forge_token_not_configured",
      "forge": forge,
      "hint": f"Configure token for {forge} in Settings → Development → Code publish.",
    }
  return token, None


def set_forge_token_tool(
  *,
  forge: str = "github",
  token: str = "",
  confirm: bool = False,
) -> dict[str, Any]:
  forge = (forge or "github").strip().lower()
  preview = {
    "action": "set_forge_token",
    "forge": forge,
    "clearing": not bool((token or "").strip()),
  }
  if not confirm:
    return {"ok": True, "needs_confirmation": True, "preview": preview}
  set_forge_token(forge, (token or "").strip() or None)
  return forge_auth_status(forge)


def resolve_publish_target(
  unit: dict[str, Any],
  *,
  target_mode: str = "",
) -> dict[str, Any]:
  kind = unit.get("kind") or "project"
  mode = (target_mode or "").strip().lower()

  if kind == "assistant":
    up = assistant_upstream()
    if mode == "user_fork":
      fork = project_fork_config("assistant") or {}
      url = (fork.get("fork_url") or "").strip()
      if not url:
        return {"ok": False, "error": "assistant fork_url not configured"}
      forge = fork.get("forge") or infer_forge_from_url(url)
      return {
        "ok": True,
        "target_mode": "user_fork",
        "repo_url": url,
        "forge": forge,
        "git_remote": fork.get("git_remote") or "fork",
        "base_branch": fork.get("default_branch") or up.get("default_branch") or "main",
      }
    return {
      "ok": True,
      "target_mode": "assistant_upstream",
      "repo_url": up.get("repo_url"),
      "forge": up.get("forge") or "github",
      "git_remote": "origin",
      "base_branch": up.get("default_branch") or "main",
    }

  mode = mode or project_default_mode()
  origin = (unit.get("origin_url") or "").strip()

  if mode == "user_fork":
    fork = project_fork_config(unit.get("id") or "openpilot") or {}
    url = (fork.get("fork_url") or "").strip()
    if not url:
      return {
        "ok": False,
        "error": "fork_not_configured",
        "unit_id": unit.get("id"),
        "hint": "Set fork URL in Development → Code publish, or use current_remote.",
      }
    forge = fork.get("forge") or infer_forge_from_url(url)
    return {
      "ok": True,
      "target_mode": "user_fork",
      "repo_url": url,
      "forge": forge,
      "git_remote": fork.get("git_remote") or "fork",
      "base_branch": fork.get("default_branch") or unit.get("branch") or "master-c3",
    }

  if not origin:
    return {"ok": False, "error": "no_origin_remote", "hint": "git remote add origin <your-repo-url>"}
  return {
    "ok": True,
    "target_mode": "current_remote",
    "repo_url": origin,
    "forge": unit.get("forge") or infer_forge_from_url(origin),
    "git_remote": "origin",
    "base_branch": unit.get("branch") or "master-c3",
  }


def _ensure_branch(
  *,
  base_branch: str,
  branch: str = "",
  title: str = "",
) -> tuple[str | None, dict[str, Any] | None]:
  status = git_status()
  current = status.get("branch") or ""
  dirty = int(status.get("dirty_count", 0) or 0)

  if branch:
    b = branch.strip()
    if current == b:
      return b, None
    exists = _git(["rev-parse", "--verify", b], timeout=10)
    if exists.get("ok"):
      if dirty:
        return None, {
          "ok": False,
          "error": "cannot switch to existing branch with uncommitted changes",
          "branch": b,
        }
      from ai.tools.domains.devops.git_tools import git_checkout
      co = git_checkout(branch=b)
      if not co.get("ok"):
        return None, co
      return b, {"checked_out": b}
    created = git_create_branch(branch=b)
    if not created.get("ok"):
      return None, created
    return b, {"created_branch": b}

  if current and current not in PROTECTED_BASES:
    return current, {"used_existing_branch": current}

  if dirty == 0:
    return None, {"ok": False, "error": "no changes to publish"}

  new_branch = f"{AI_BRANCH_PREFIX}{_slug(title)}-{int(time.time()) % 100000}"
  created = git_create_branch(branch=new_branch)
  if not created.get("ok"):
    return None, created
  return new_branch, {"created_branch": new_branch}


def publish_changes(
  *,
  unit_id: str = "openpilot",
  target_mode: str = "",
  title: str = "",
  body: str = "",
  base_branch: str = "",
  branch: str = "",
  commit_message: str = "",
  paths: list[str] | None = None,
  draft: bool = False,
  remote: str = "",
  repo_url: str = "",
  severity: str = "",
  request_auto_fix: bool = False,
  auto_label: bool = True,
  confirm: bool = False,
  params: "Params | None" = None,
) -> dict[str, Any]:
  del params
  unit = get_unit(unit_id)
  if not unit:
    return {"ok": False, "error": "unknown_unit", "unit_id": unit_id}

  target = resolve_publish_target(unit, target_mode=target_mode)
  if not target.get("ok"):
    return target

  url = (repo_url or target.get("repo_url") or "").strip()
  if not url:
    return {"ok": False, "error": "repo_url_missing"}

  try:
    forge, owner, repo = parse_repo_url(url)
  except ValueError as exc:
    return {"ok": False, "error": str(exc)}

  forge = target.get("forge") or forge
  base = (base_branch or target.get("base_branch") or unit.get("branch") or "main").strip()
  push_remote = (remote or target.get("git_remote") or "origin").strip()
  git_root = Path(unit["git_root"])
  repo_target = "assistant" if unit.get("kind") == "assistant" else "openpilot"

  if target.get("target_mode") == "user_fork":
    ensure = git_remote_ensure(git_root, remote_name=push_remote, url=url)
    if not ensure.get("ok"):
      return ensure

  prefix = (unit.get("path_prefix") or "").replace("\\", "/").strip("/")
  path_list = [str(x) for x in paths] if isinstance(paths, list) else None
  if not path_list and prefix:
    path_list = list(unit.get("dirty_files") or [])

  if not title:
    title = f"chore(ai): update {unit_id}"

  labels = []
  if auto_label and unit.get("kind") == "assistant":
    labels = suggest_pr_labels(repo_target="assistant", severity=severity, request_auto_fix=request_auto_fix)
  elif auto_label:
    labels = suggest_pr_labels(repo_target="openpilot", severity=severity, request_auto_fix=request_auto_fix)

  with git_repo_context(repo_target, repo_root=git_root):
    status = git_status()
    diff_stat = git_diff(stat=True)

    preview = {
      "action": "publish_changes",
      "unit_id": unit_id,
      "kind": unit.get("kind"),
      "target_mode": target.get("target_mode"),
      "title": title,
      "repo": repo_slug(owner, repo),
      "repo_url": url,
      "forge": forge,
      "head_branch": branch or "(auto)",
      "base": base,
      "push_remote": push_remote,
      "git_root": str(git_root),
      "dirty_count": status.get("dirty_count"),
      "diff_stat": (diff_stat.get("stdout") or "")[:2000],
      "labels": labels,
      "paths": path_list,
    }

    if not confirm:
      return {"ok": True, "needs_confirmation": True, "preview": preview}

    head_branch, branch_err = _ensure_branch(base_branch=base, branch=branch, title=title)
    if branch_err and not head_branch:
      if branch_err.get("ok") is False:
        return {**branch_err, "preview": preview}
      return {"ok": False, "error": "branch_setup_failed", **branch_err, "preview": preview}
    if not head_branch:
      return {"ok": False, "error": "could not determine head branch", "preview": preview}

    if status.get("dirty_count", 0) == 0 and not branch_err:
      return {"ok": False, "error": "nothing to commit", "preview": preview}

    msg = (commit_message or title).strip()[:500]
    committed = git_commit(message=msg, add_all=not path_list, paths=path_list)
    if not committed.get("ok"):
      return {**committed, "preview": preview}

    pushed = git_push_at(git_root, remote=push_remote, branch=head_branch, set_upstream=True)
    if not pushed.get("ok"):
      return {
        "ok": False,
        "error": pushed.get("stderr") or pushed.get("error") or "git push failed",
        "preview": preview,
        "hint": "commit succeeded; configure git credentials and retry",
        "partial": True,
      }

  token, err = _require_forge_token(forge)
  if err:
    return {
      **err,
      "partial": True,
      "committed": True,
      "pushed": True,
      "branch": head_branch,
      "hint": "Code pushed; configure forge token then create PR manually",
    }

  pr_body = body.strip()
  if not pr_body:
    draft_md = generate_adaptation_pr_draft(project_name=title, summary=msg)
    pr_body = draft_md.get("markdown", "")

  client = get_forge_client(forge)
  head_ref = head_branch
  if target.get("target_mode") == "user_fork" and push_remote != "origin":
    head_ref = f"{owner}:{head_branch}"

  pr = client.create_merge_request(
    token,
    owner,
    repo,
    title=title[:250],
    head=head_ref,
    base=base,
    body=pr_body[:65000],
    draft=draft,
  )
  if not pr.get("ok"):
    return {**pr, "partial": True, "branch": head_branch, "pushed": True}

  pull_number = (pr.get("pull") or {}).get("number")
  return {
    "ok": True,
    "pull_request_url": pr.get("html_url"),
    "pull": pr.get("pull"),
    "pull_number": pull_number,
    "labels": labels,
    "branch": head_branch,
    "base": base,
    "unit_id": unit_id,
    "target_mode": target.get("target_mode"),
    "forge": forge,
    "repo": repo_slug(owner, repo),
    "commit": committed.get("staged_stat"),
    "next": "Review PR on forge web UI",
  }


def publish_status() -> dict[str, Any]:
  from ai.common.publish_config import get_publish_settings
  from ai.tools.forge import infer_forge_from_url

  units_payload = discover_publish_units(include_clean=True)
  units = units_payload.get("units") or []
  settings = get_publish_settings()
  auth = {
    "github": forge_auth_status("github"),
    "gitee": forge_auth_status("gitee"),
  }
  forge_counts: dict[str, int] = {}
  for unit in units:
    url = str(unit.get("origin_url") or "").strip()
    if url:
      forge = infer_forge_from_url(url)
      forge_counts[forge] = forge_counts.get(forge, 0) + 1
  primary_forge = "github"
  if forge_counts:
    primary_forge = max(forge_counts, key=forge_counts.get)
  secondary_forges = sorted(f for f in forge_counts if f != primary_forge)
  return {
    "ok": True,
    **units_payload,
    "settings": settings.get("settings"),
    "forge_auth": auth,
    "primary_forge": primary_forge,
    "secondary_forges": secondary_forges,
  }
