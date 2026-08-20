"""Git remote helpers for arbitrary repo roots."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _git_push_env() -> dict[str, str]:
  env = os.environ.copy()
  skip = env.get("GIT_LFS_SKIP_PUSH", "").strip().lower()
  if skip not in ("0", "false", "no"):
    env["GIT_LFS_SKIP_PUSH"] = "1"
  return env


def _run_git(root: Path, args: list[str], *, timeout: int = 30) -> dict[str, Any]:
  try:
    proc = subprocess.run(
      ["git", "-C", str(root), *args],
      capture_output=True,
      text=True,
      timeout=timeout,
      check=False,
      env=_git_push_env(),
    )
    return {
      "ok": proc.returncode == 0,
      "stdout": (proc.stdout or "").strip(),
      "stderr": (proc.stderr or "").strip(),
      "returncode": proc.returncode,
    }
  except (OSError, subprocess.TimeoutExpired) as exc:
    return {"ok": False, "error": str(exc)}


def git_status_at(root: Path) -> dict[str, Any]:
  root = root.resolve()
  branch = _run_git(root, ["rev-parse", "--abbrev-ref", "HEAD"], timeout=10)
  head = _run_git(root, ["rev-parse", "--short", "HEAD"], timeout=10)
  status = _run_git(root, ["status", "--short", "-b"], timeout=30)
  lines = [ln for ln in (status.get("stdout") or "").splitlines() if ln.strip()]
  return {
    "ok": True,
    "branch": branch.get("stdout") if branch.get("ok") else None,
    "head": head.get("stdout") if head.get("ok") else None,
    "status_lines": lines[:200],
    "dirty_count": sum(1 for ln in lines if ln and not ln.startswith("##")),
    "repo": str(root),
  }


def git_remotes_at(root: Path) -> dict[str, str]:
  root = root.resolve()
  res = _run_git(root, ["remote", "-v"], timeout=15)
  remotes: dict[str, str] = {}
  for line in (res.get("stdout") or "").splitlines():
    parts = line.split()
    if len(parts) >= 2 and parts[1].endswith("(fetch)"):
      name = parts[0]
      url = parts[1]
      if name not in remotes:
        remotes[name] = url.replace(" (fetch)", "")
    elif len(parts) >= 2:
      name, url = parts[0], parts[1]
      if name not in remotes:
        remotes[name] = url
  return remotes


def _normalize_remote_url(url: str) -> str:
  u = (url or "").strip().rstrip("/")
  if u.endswith(".git"):
    u = u[:-4]
  return u


def git_remote_ensure(
  root: Path,
  *,
  remote_name: str,
  url: str,
) -> dict[str, Any]:
  root = root.resolve()
  name = (remote_name or "fork").strip()
  target = _normalize_remote_url(url)
  if not target or " " in name:
    return {"ok": False, "error": "invalid remote name or url"}
  remotes = git_remotes_at(root)
  existing = remotes.get(name)
  if existing:
    if _normalize_remote_url(existing) == target:
      return {"ok": True, "remote": name, "url": target, "action": "unchanged"}
    set_res = _run_git(root, ["remote", "set-url", name, target + ".git" if not target.endswith(".git") else target])
    if not set_res.get("ok"):
      return {"ok": False, "error": set_res.get("stderr") or "remote set-url failed"}
    return {"ok": True, "remote": name, "url": target, "action": "updated"}
  add_url = target if target.endswith(".git") else target + ".git"
  add_res = _run_git(root, ["remote", "add", name, add_url])
  if not add_res.get("ok"):
    return {"ok": False, "error": add_res.get("stderr") or "remote add failed"}
  return {"ok": True, "remote": name, "url": target, "action": "added"}


def git_push_at(
  root: Path,
  *,
  remote: str = "origin",
  branch: str = "",
  set_upstream: bool = False,
) -> dict[str, Any]:
  root = root.resolve()
  remote = (remote or "origin").strip()
  args = ["push"]
  if set_upstream and branch:
    args.extend(["-u", remote, branch])
  elif branch:
    args.extend([remote, branch])
  else:
    args.append(remote)
  res = _run_git(root, args, timeout=300)
  res["remote"] = remote
  res["branch"] = branch
  return res
