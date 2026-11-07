"""Forge adapters for PR/MR APIs (GitHub, Gitee, …)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from ai.tools.forge.gitee import GiteeForge
from ai.tools.forge.github import GitHubForge

FORGE_GITHUB = "github"
FORGE_GITEE = "gitee"
FORGE_GITLAB = "gitlab"

_TOKEN_KEYS = {
  FORGE_GITHUB: "ai_github_actions_pat",
  FORGE_GITEE: "ai_gitee_token",
  FORGE_GITLAB: "ai_gitlab_token",
}


def infer_forge_from_url(url: str) -> str:
  host = (urlparse(url or "").netloc or "").lower()
  if "gitee.com" in host:
    return FORGE_GITEE
  if "gitlab" in host:
    return FORGE_GITLAB
  return FORGE_GITHUB


def parse_repo_url(repo_url: str) -> tuple[str, str, str]:
  """Return (forge, owner, repo) from a web or git URL."""
  text = (repo_url or "").strip().rstrip("/")
  if text.endswith(".git"):
    text = text[:-4]
  m = re.match(r"https?://(?:www\.)?github\.com/([^/]+)/([^/]+)$", text, re.I)
  if m:
    return FORGE_GITHUB, m.group(1).lower(), m.group(2).lower()
  m = re.match(r"https?://(?:www\.)?gitee\.com/([^/]+)/([^/]+)$", text, re.I)
  if m:
    return FORGE_GITEE, m.group(1).lower(), m.group(2).lower()
  m = re.match(r"https?://([^/]+)/([^/]+)/([^/]+)$", text, re.I)
  if m and "gitlab" in m.group(1).lower():
    return FORGE_GITLAB, m.group(2).lower(), m.group(3).lower()
  if "/" in text and not text.startswith("http"):
    owner, repo = text.split("/", 1)
    return FORGE_GITHUB, owner.lower(), repo.lower().removesuffix(".git")
  raise ValueError(f"unsupported repo URL: {repo_url}")


def repo_slug(owner: str, repo: str) -> str:
  return f"{owner}/{repo}"


def get_forge_client(forge: str):
  f = (forge or FORGE_GITHUB).strip().lower()
  if f == FORGE_GITEE:
    return GiteeForge()
  return GitHubForge()


def token_config_key(forge: str) -> str:
  return _TOKEN_KEYS.get((forge or FORGE_GITHUB).lower(), "ai_github_actions_pat")


def get_forge_token(forge: str) -> str | None:
  from ai.common.config_store import get_config_store

  key = token_config_key(forge)
  raw = str(get_config_store().get(key, "") or "").strip()
  return raw or None


def set_forge_token(forge: str, token: str | None) -> None:
  from ai.common.storage import remove_param, write_param

  key = token_config_key(forge)
  if token:
    write_param(None, key, token.strip())
  else:
    remove_param(None, key)


def forge_auth_status(forge: str, *, repo_url: str = "") -> dict[str, Any]:
  client = get_forge_client(forge)
  token = get_forge_token(forge)
  out: dict[str, Any] = {
    "ok": True,
    "forge": (forge or FORGE_GITHUB).lower(),
    "configured": bool(token),
    "config_key": token_config_key(forge),
    "storage": "config.json",
  }
  if repo_url:
    try:
      f, owner, repo = parse_repo_url(repo_url)
      out["repo"] = repo_slug(owner, repo)
      out["forge_inferred"] = f
    except ValueError:
      pass
  if not token:
    out["valid"] = False
    out["hint"] = "Token not set."
    return out
  check = client.verify_token(token)
  out["valid"] = bool(check.get("valid"))
  if check.get("valid"):
    out["user"] = check.get("login") or check.get("name")
  else:
    out["error_detail"] = check.get("message") or check.get("error")
  return out
