"""Git read/write helpers for op助手 (openpilot repo)."""

from __future__ import annotations

import subprocess
from typing import Any

from ai.system.paths import openpilot_root


def _git(args: list[str], *, timeout: int = 120) -> dict[str, Any]:
  root = openpilot_root()
  try:
    proc = subprocess.run(
      ["git", "-C", str(root), *args],
      capture_output=True,
      text=True,
      timeout=timeout,
    )
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if len(out) > 12000:
      out = out[:12000] + "\n... (truncated)"
    if len(err) > 4000:
      err = err[:4000] + "\n... (truncated)"
    return {
      "ok": proc.returncode == 0,
      "returncode": proc.returncode,
      "stdout": out,
      "stderr": err,
      "cwd": str(root),
    }
  except subprocess.TimeoutExpired:
    return {"ok": False, "error": f"git timed out after {timeout}s"}
  except FileNotFoundError:
    return {"ok": False, "error": "git not installed"}
  except Exception as e:
    return {"ok": False, "error": str(e)}


def git_status() -> dict[str, Any]:
  branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], timeout=10)
  head = _git(["rev-parse", "--short", "HEAD"], timeout=10)
  status = _git(["status", "--short", "-b"], timeout=30)
  if not status.get("ok") and not status.get("stdout"):
    return status
  lines = [ln for ln in (status.get("stdout") or "").splitlines() if ln.strip()]
  return {
    "ok": True,
    "branch": branch.get("stdout") if branch.get("ok") else None,
    "head": head.get("stdout") if head.get("ok") else None,
    "status_lines": lines[:200],
    "dirty_count": sum(1 for ln in lines if ln and not ln.startswith("##")),
    "repo": str(openpilot_root()),
  }


def git_diff(*, path: str = "", stat: bool = False) -> dict[str, Any]:
  args = ["diff"]
  if stat:
    args.append("--stat")
  p = (path or "").strip()
  if p and ".." not in p:
    args.extend(["--", p])
  res = _git(args, timeout=60)
  if res.get("ok") or res.get("stdout"):
    res["ok"] = True
  return res


def git_pull(*, remote: str = "origin", branch: str = "") -> dict[str, Any]:
  remote = (remote or "origin").strip()
  if not remote or " " in remote:
    return {"ok": False, "error": "invalid remote"}
  args = ["pull", remote]
  if branch:
    b = branch.strip()
    if not b or " " in b:
      return {"ok": False, "error": "invalid branch"}
    args.append(b)
  return _git(args, timeout=180)


def _valid_branch_name(name: str) -> str | None:
  b = (name or "").strip()
  if not b or " " in b or b.startswith("-") or ".." in b:
    return None
  return b


def git_list_branches(*, include_remote: bool = True, limit: int = 80) -> dict[str, Any]:
  current = _git(["rev-parse", "--abbrev-ref", "HEAD"], timeout=10)
  local = _git(["branch", "--format=%(refname:short)"], timeout=30)
  if not local.get("ok"):
    return local
  local_branches = [ln.strip() for ln in (local.get("stdout") or "").splitlines() if ln.strip()]
  remote_branches: list[str] = []
  if include_remote:
    remote = _git(["branch", "-r", "--format=%(refname:short)"], timeout=30)
    if remote.get("ok"):
      remote_branches = [
        ln.strip()
        for ln in (remote.get("stdout") or "").splitlines()
        if ln.strip() and "HEAD" not in ln
      ]
  lim = max(1, min(int(limit or 80), 200))
  return {
    "ok": True,
    "current": current.get("stdout") if current.get("ok") else None,
    "local": local_branches[:lim],
    "remote": remote_branches[:lim],
    "repo": str(openpilot_root()),
  }


def git_checkout(
  *,
  branch: str,
  create: bool = False,
  start_point: str = "",
) -> dict[str, Any]:
  b = _valid_branch_name(branch)
  if not b:
    return {"ok": False, "error": "invalid branch name"}

  dirty = _git(["status", "--porcelain"], timeout=20)
  dirty_lines = [ln for ln in (dirty.get("stdout") or "").splitlines() if ln.strip()]
  if dirty_lines:
    return {
      "ok": False,
      "error": "working tree has uncommitted changes; commit or stash before switching branch",
      "dirty_count": len(dirty_lines),
      "hint": "Run git_status / git_diff first, then commit or stash on the device.",
    }

  before = _git(["rev-parse", "--abbrev-ref", "HEAD"], timeout=10)
  args = ["checkout"]
  if create:
    args.append("-b")
  args.append(b)
  sp = _valid_branch_name(start_point) if start_point else None
  if create and sp:
    args.append(sp)
  res = _git(args, timeout=120)
  after = _git(["rev-parse", "--abbrev-ref", "HEAD"], timeout=10)
  res["previous_branch"] = before.get("stdout") if before.get("ok") else None
  res["branch"] = after.get("stdout") if after.get("ok") else b
  res["created"] = bool(create)
  return res


def git_fetch(*, remote: str = "origin", prune: bool = True) -> dict[str, Any]:
  remote = (remote or "origin").strip()
  if not remote or " " in remote:
    return {"ok": False, "error": "invalid remote"}
  args = ["fetch", remote]
  if prune:
    args.append("--prune")
  return _git(args, timeout=180)


def git_stash(*, message: str = "op助手 auto-stash", include_untracked: bool = False) -> dict[str, Any]:
  msg = (message or "op助手 stash").strip()[:200]
  args = ["stash", "push", "-m", msg]
  if include_untracked:
    args.append("-u")
  res = _git(args, timeout=60)
  if res.get("stdout") == "No local changes to save":
    return {"ok": True, "stashed": False, "message": res.get("stdout")}
  res["stashed"] = res.get("ok", False)
  return res


def git_stash_pop(*, index: int = 0) -> dict[str, Any]:
  idx = max(0, min(int(index or 0), 9))
  args = ["stash", "pop"] if idx == 0 else ["stash", "pop", f"stash@{{{idx}}}"]
  return _git(args, timeout=120)


def git_commit(*, message: str, add_all: bool = True, paths: list[str] | None = None) -> dict[str, Any]:
  msg = (message or "").strip()
  if not msg or len(msg) > 500:
    return {"ok": False, "error": "commit message required (max 500 chars)"}
  if add_all and not paths:
    stage = _git(["add", "-A"], timeout=60)
    if not stage.get("ok"):
      return stage
  elif paths:
    clean = [p.strip() for p in paths if p.strip() and ".." not in p and not p.startswith("-")]
    if not clean:
      return {"ok": False, "error": "no valid paths to stage"}
    stage = _git(["add", "--"] + clean[:50], timeout=60)
    if not stage.get("ok"):
      return stage
  diff = _git(["diff", "--cached", "--stat"], timeout=30)
  if not (diff.get("stdout") or "").strip():
    return {"ok": False, "error": "nothing staged to commit"}
  res = _git(["commit", "-m", msg], timeout=60)
  res["staged_stat"] = diff.get("stdout")
  return res


def git_push(
  *,
  remote: str = "origin",
  branch: str = "",
  set_upstream: bool = False,
) -> dict[str, Any]:
  """Git push (requires credentials configured on device/PC)."""
  remote = (remote or "origin").strip()
  if not remote or " " in remote:
    return {"ok": False, "error": "invalid remote"}
  args = ["push", remote]
  b = _valid_branch_name(branch) if branch else None
  if b:
    args.append(b)
  if set_upstream and b:
    args = ["push", "-u", remote, b]
  return _git(args, timeout=300)
