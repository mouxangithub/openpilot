"""Create GitHub/Gitee issues from templates with publish target resolution."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, TYPE_CHECKING

from ai.common.publish_config import get_publish_settings
from ai.system.host_env import get_host_environment
from ai.tools.forge import (
  get_forge_client,
  get_forge_token,
  infer_forge_from_url,
  parse_repo_url,
  repo_slug,
)
from ai.tools.domains.platform.issue_template_lib import (
  get_builtin_template,
  list_builtin_templates,
  load_local_repo_templates,
  render_issue_body,
)
from ai.tools.domains.platform.publish_tools import resolve_publish_target
from ai.tools.domains.platform.publish_units import get_unit

if TYPE_CHECKING:
  from openpilot.common.params import Params


def _issue_settings() -> dict[str, Any]:
  s = get_publish_settings().get("settings") or {}
  return s.get("issue_publish") or {}


def _git_version(git_root: Path) -> str:
  try:
    proc = subprocess.run(
      ["git", "-C", str(git_root), "rev-parse", "--short", "HEAD"],
      capture_output=True,
      text=True,
      timeout=8,
      check=False,
    )
    if proc.returncode == 0:
      return proc.stdout.strip()
  except OSError:
    pass
  return ""


def _audit_excerpt(limit: int = 10) -> list[dict[str, Any]]:
  try:
    from ai.tools.domains.platform.audit_store import list_audit_trail
    res = list_audit_trail(limit=limit)
    return res.get("entries") or res.get("audit") or []
  except Exception:
    return []


def _auto_footer(*, unit: dict[str, Any] | None, attach_audit: bool) -> str:
  env = get_host_environment()
  lines = [
    "### Environment (op助手)",
    f"- Host: `{env.get('platform')}` / `{env.get('host_role')}`",
    f"- openpilot_root: `{env.get('openpilot_root')}`",
  ]
  if unit:
    lines.append(f"- unit: `{unit.get('id')}` @ `{unit.get('branch')}`")
    ver = _git_version(Path(unit.get("git_root") or ""))
    if ver:
      lines.append(f"- commit: `{ver}`")
  if attach_audit:
    audit = _audit_excerpt()
    if audit:
      lines.append("")
      lines.append("### Recent audit")
      for entry in audit[:8]:
        lines.append(f"- `{entry.get('tool', entry.get('action', '?'))}` ok={entry.get('ok')}")
  lines.append("")
  lines.append("_Submitted via op助手_")
  return "\n".join(lines)


def resolve_issue_target(
  unit_id: str = "assistant",
  *,
  target_mode: str = "",
  repo_url: str = "",
) -> dict[str, Any]:
  issue_cfg = _issue_settings()
  uid = (unit_id or issue_cfg.get("default_unit") or "assistant").strip()
  unit = get_unit(uid)
  if not unit and uid != "assistant":
    unit = get_unit("openpilot")
  if not unit:
    unit = get_unit("assistant")
  if not unit:
    return {"ok": False, "error": "no_publish_unit"}

  if uid == "assistant" or unit.get("kind") == "assistant":
    target = resolve_publish_target(unit, target_mode=target_mode or "assistant_upstream")
  else:
    mode = target_mode or issue_cfg.get("default_mode") or ""
    target = resolve_publish_target(unit, target_mode=mode)

  if repo_url:
    try:
      forge, owner, repo = parse_repo_url(repo_url)
      target = {
        **target,
        "ok": True,
        "repo_url": repo_url,
        "forge": forge,
        "repo": repo_slug(owner, repo),
      }
    except ValueError as exc:
      return {"ok": False, "error": str(exc)}

  if not target.get("ok"):
    return target
  return {**target, "unit_id": unit.get("id"), "unit": unit}


def discover_issue_templates(
  *,
  unit_id: str = "assistant",
  repo_url: str = "",
  include_builtin: bool = True,
) -> dict[str, Any]:
  target = resolve_issue_target(unit_id, repo_url=repo_url)
  if not target.get("ok"):
    return target

  templates: list[dict[str, Any]] = []
  if include_builtin:
    templates.extend(list_builtin_templates())

  unit = target.get("unit") or {}
  git_root = Path(unit.get("git_root") or "")
  if git_root.is_dir():
    local = load_local_repo_templates(git_root)
    seen = {t["id"] for t in templates}
    for t in local:
      if t["id"] not in seen:
        templates.append(t)
        seen.add(t["id"])

  forge = target.get("forge") or "github"
  url = target.get("repo_url") or ""
  token = get_forge_token(forge)
  if token and url:
    try:
      _, owner, repo = parse_repo_url(url)
      client = get_forge_client(forge)
      if hasattr(client, "list_issue_templates"):
        remote = client.list_issue_templates(token, owner, repo)
        if remote.get("ok"):
          seen = {t["id"] for t in templates}
          for t in remote.get("templates") or []:
            if t.get("id") not in seen:
              templates.append(t)
    except ValueError:
      pass

  default_tpl = _issue_settings().get("default_template") or "bug"
  return {
    "ok": True,
    "templates": templates,
    "default_template": default_tpl,
    "target": {
      "unit_id": target.get("unit_id"),
      "repo_url": url,
      "forge": forge,
      "repo": target.get("repo") or "",
      "target_mode": target.get("target_mode"),
    },
  }


def _find_similar_issues(
  forge: str,
  token: str,
  owner: str,
  repo: str,
  title: str,
) -> list[dict[str, Any]]:
  if not _issue_settings().get("dedupe_search", True):
    return []
  client = get_forge_client(forge)
  if not hasattr(client, "search_issues"):
    return []
  words = [w for w in re.split(r"\W+", title.lower()) if len(w) > 3][:6]
  if not words:
    return []
  query = " ".join(words[:4])
  res = client.search_issues(token, owner, repo, query=query, per_page=5)
  if not res.get("ok"):
    return []
  return res.get("issues") or []


def create_issue(
  *,
  unit_id: str = "assistant",
  target_mode: str = "",
  repo_url: str = "",
  template_id: str = "bug",
  title: str = "",
  body: str = "",
  fields: dict[str, str] | None = None,
  labels: list[str] | None = None,
  attach_audit: bool = True,
  confirm: bool = False,
  params: "Params | None" = None,
) -> dict[str, Any]:
  del params
  target = resolve_issue_target(unit_id, target_mode=target_mode, repo_url=repo_url)
  if not target.get("ok"):
    return target

  url = (target.get("repo_url") or "").strip()
  if not url:
    return {"ok": False, "error": "repo_url_missing"}

  try:
    forge, owner, repo = parse_repo_url(url)
  except ValueError as exc:
    return {"ok": False, "error": str(exc)}

  forge = target.get("forge") or infer_forge_from_url(url)
  tpl_id = (template_id or _issue_settings().get("default_template") or "bug").strip().lower()
  template = get_builtin_template(tpl_id)
  if not template:
    disc = discover_issue_templates(unit_id=unit_id, repo_url=url, include_builtin=False)
    for t in disc.get("templates") or []:
      if t.get("id") == tpl_id:
        template = t
        break
  if not template:
    template = get_builtin_template("bug") or list_builtin_templates()[0]

  field_map = dict(fields or {})
  unit = target.get("unit")
  footer = _auto_footer(unit=unit, attach_audit=attach_audit)
  issue_body = (body or "").strip() or render_issue_body(template, field_map, footer=footer)
  issue_title = (title or "").strip()
  if not issue_title:
    issue_title = field_map.get("summary") or field_map.get("description") or field_map.get("problem") or "op助手 feedback"
    issue_title = issue_title.split("\n", 1)[0][:120]

  label_list = list(labels) if labels else list(template.get("labels") or [])
  token = get_forge_token(forge)
  similar = _find_similar_issues(forge, token or "", owner, repo, issue_title) if token else []

  preview = {
    "action": "create_issue",
    "unit_id": target.get("unit_id"),
    "template_id": tpl_id,
    "title": issue_title,
    "repo": repo_slug(owner, repo),
    "repo_url": url,
    "forge": forge,
    "labels": label_list,
    "body_preview": issue_body[:2000],
    "similar_issues": similar[:3],
  }

  if not confirm:
    if similar:
      preview["hint"] = "Similar open issues found — review before creating."
    return {"ok": True, "needs_confirmation": True, "preview": preview}

  token = get_forge_token(forge)
  if not token:
    return {
      "ok": False,
      "error": "forge_token_not_configured",
      "forge": forge,
      "hint": "Configure token in Settings → Development → Code publish.",
      "preview": preview,
    }

  client = get_forge_client(forge)
  created = client.create_issue(
    token, owner, repo, title=issue_title, body=issue_body, labels=label_list,
  )
  if not created.get("ok"):
    return {**created, "preview": preview}

  return {
    "ok": True,
    "issue_url": created.get("html_url"),
    "issue": created.get("issue"),
    "issue_number": created.get("number"),
    "repo": repo_slug(owner, repo),
    "forge": forge,
    "template_id": tpl_id,
    "similar_issues": similar[:3],
  }


def report_issue(
  *,
  kind: str = "bug",
  unit_id: str = "",
  title: str = "",
  repro_steps: str = "",
  expected: str = "",
  actual: str = "",
  summary: str = "",
  proposal: str = "",
  severity: str = "ui",
  attach_audit: bool = True,
  confirm: bool = False,
  params: "Params | None" = None,
) -> dict[str, Any]:
  """High-level issue reporter (bug / feature / suggestion)."""
  k = (kind or "bug").strip().lower()
  template_map = {
    "bug": "bug",
    "feature": "feature",
    "enhancement": "feature",
    "suggestion": "suggestion",
    "assistant": "assistant",
    "pc": "openpilot_pc",
  }
  tpl = template_map.get(k, "bug")
  uid = unit_id or ("assistant" if k in ("assistant", "bug", "feature", "suggestion") else "openpilot")

  fields: dict[str, str] = {}
  if k in ("bug", "assistant", "pc"):
    fields = {
      "description": summary or title,
      "repro": repro_steps,
      "expected": expected,
      "actual": actual,
    }
    if k == "pc":
      env = get_host_environment()
      fields["os"] = str(env.get("platform") or "")
  elif k in ("feature", "enhancement"):
    fields = {
      "problem": summary or title,
      "proposal": proposal or expected,
      "alternatives": actual,
    }
  else:
    fields = {"summary": summary or title, "benefit": proposal, "extra": repro_steps}

  issue_title = title.strip() or summary.strip() or f"[{severity}] op助手 {k} report"
  labels = list(get_builtin_template(tpl).get("labels") or []) if get_builtin_template(tpl) else ["bug"]
  if severity:
    labels.append(f"severity-{severity}")

  return create_issue(
    unit_id=uid,
    template_id=tpl,
    title=issue_title,
    fields=fields,
    labels=labels,
    attach_audit=attach_audit,
    confirm=confirm,
    params=params,
  )


def issue_status() -> dict[str, Any]:
  from ai.tools.domains.platform.publish_tools import publish_status

  pub = publish_status()
  issue_cfg = _issue_settings()
  return {
    "ok": True,
    "settings": issue_cfg,
    "forge_auth": pub.get("forge_auth"),
    "templates": list_builtin_templates(),
    "default_template": issue_cfg.get("default_template") or "bug",
    "default_unit": issue_cfg.get("default_unit") or "assistant",
  }
