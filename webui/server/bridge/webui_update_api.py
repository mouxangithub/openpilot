"""Web UI self-update via git (separate from openpilot system updater)."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

from webui.server.deps import webui_root

_DISMISS_FILE = ".webui_update_dismissed"
_cache: dict[str, Any] = {"ts": 0.0, "payload": None}
_CACHE_TTL = 60.0


def _run_git(args: list[str], cwd: Path, *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
  return subprocess.run(
    ["git", *args],
    cwd=str(cwd),
    capture_output=True,
    text=True,
    timeout=timeout,
    check=False,
  )


def _is_git_repo(root: Path) -> bool:
  return (root / ".git").is_dir()


def _current_branch(root: Path) -> str:
  r = _run_git(["symbolic-ref", "--short", "HEAD"], root, timeout=15)
  if r.returncode == 0 and r.stdout.strip():
    return r.stdout.strip()
  return "main"


def current_commit_short(root: Path | None = None) -> str:
  root = root or webui_root()
  if not _is_git_repo(root):
    return ""
  r = _run_git(["rev-parse", "--short", "HEAD"], root, timeout=15)
  return r.stdout.strip() if r.returncode == 0 else ""


def _dismiss_path(root: Path) -> Path:
  return root / _DISMISS_FILE


def _read_dismissed(root: Path) -> str:
  path = _dismiss_path(root)
  try:
    return path.read_text(encoding="utf-8").strip()
  except OSError:
    return ""


def _write_dismissed(root: Path, commit: str) -> None:
  try:
    _dismiss_path(root).write_text(commit.strip(), encoding="utf-8")
  except OSError:
    pass


def _commit_lines(root: Path, local: str, remote: str, limit: int = 10) -> list[dict[str, str]]:
  if not local or not remote or local == remote:
    return []
  r = _run_git(["log", "--oneline", f"{local}..{remote}", f"-n{limit}"], root, timeout=30)
  if r.returncode != 0:
    return []
  out: list[dict[str, str]] = []
  for line in r.stdout.splitlines():
    line = line.strip()
    if not line:
      continue
    parts = line.split(" ", 1)
    out.append({
      "hash": parts[0],
      "title": parts[1] if len(parts) > 1 else parts[0],
    })
  return out


def _mock_status() -> dict[str, Any]:
  from webui.dev.mock_runtime import SIM

  available = bool(SIM.get("webui_update_available", False))
  remote = str(SIM.get("webui_remote_commit", "mock-remote")[:12])
  local = str(SIM.get("webui_local_commit", "mock-local")[:12])
  dismissed = str(SIM.get("webui_update_dismissed", ""))
  commits = SIM.get("webui_update_commits") or [
    {"hash": "abc1234", "title": "feat: GUI alignment v54"},
    {"hash": "def5678", "title": "fix: model overlay calibration"},
  ]
  show_prompt = available and dismissed != remote
  return {
    "ok": True,
    "dev_pc": True,
    "git": True,
    "branch": "main",
    "local_commit": local,
    "local_short": local[:12],
    "remote_commit": remote,
    "remote_short": remote[:12],
    "available": available,
    "show_prompt": show_prompt,
    "commits": commits if available else [],
    "dismissed_commit": dismissed,
    "checked_at": int(time.time()),
  }


def snapshot_webui_update(*, fetch: bool = False, use_cache: bool = True) -> dict[str, Any]:
  if os.environ.get("WEBUI_DEV_PC") == "1":
    return _mock_status()

  now = time.time()
  if use_cache and not fetch and _cache["payload"] and now - float(_cache["ts"]) < _CACHE_TTL:
    return dict(_cache["payload"])

  root = webui_root()
  if not _is_git_repo(root):
    payload = {
      "ok": True,
      "git": False,
      "available": False,
      "show_prompt": False,
      "local_short": current_commit_short(root) or "unknown",
      "commits": [],
      "checked_at": int(now),
      "message": "Web UI is not a git checkout",
    }
    _cache.update(ts=now, payload=payload)
    return payload

  branch = _current_branch(root)
  local_r = _run_git(["rev-parse", "HEAD"], root, timeout=15)
  local = local_r.stdout.strip() if local_r.returncode == 0 else ""
  local_short = local[:12] if local else ""

  remote = local
  fetch_error = ""
  if fetch:
    fr = _run_git(["fetch", "origin", branch], root, timeout=120)
    if fr.returncode != 0:
      fetch_error = (fr.stderr or fr.stdout or "git fetch failed").strip().splitlines()[-1][:200]

  remote_ref = f"origin/{branch}"
  remote_r = _run_git(["rev-parse", remote_ref], root, timeout=15)
  if remote_r.returncode == 0:
    remote = remote_r.stdout.strip()
  elif fetch_error:
    remote = local

  available = bool(local and remote and local != remote)
  dismissed = _read_dismissed(root)
  show_prompt = available and dismissed != remote
  commits = _commit_lines(root, local, remote) if available else []

  payload = {
    "ok": True,
    "git": True,
    "branch": branch,
    "local_commit": local,
    "local_short": local_short or current_commit_short(root),
    "remote_commit": remote,
    "remote_short": remote[:12] if remote else "",
    "available": available,
    "show_prompt": show_prompt,
    "commits": commits,
    "dismissed_commit": dismissed,
    "fetch_error": fetch_error,
    "checked_at": int(now),
  }
  _cache.update(ts=now, payload=payload)
  return payload


def dismiss_webui_update(commit: str | None = None) -> dict[str, Any]:
  if os.environ.get("WEBUI_DEV_PC") == "1":
    from webui.dev.mock_runtime import SIM
    target = commit or str(SIM.get("webui_remote_commit", "mock-remote"))
    SIM["webui_update_dismissed"] = target
    return {"ok": True, "dismissed_commit": target}

  root = webui_root()
  st = snapshot_webui_update(fetch=False, use_cache=False)
  target = (commit or st.get("remote_commit") or "").strip()
  if not target:
    return {"ok": False, "error": "no remote commit to dismiss"}
  _write_dismissed(root, target)
  st["show_prompt"] = False
  st["dismissed_commit"] = target
  _cache.update(ts=time.time(), payload=st)
  return {"ok": True, "dismissed_commit": target}


def apply_webui_update() -> dict[str, Any]:
  if os.environ.get("WEBUI_DEV_PC") == "1":
    from webui.dev.mock_runtime import SIM
    remote = str(SIM.get("webui_remote_commit", "mock-remote"))
    SIM["webui_local_commit"] = remote
    SIM["webui_update_available"] = False
    SIM["webui_update_dismissed"] = ""
    return {
      "ok": True,
      "local_short": remote[:12],
      "remote_short": remote[:12],
      "restarted": False,
      "message": "PC mock update applied — reload the page.",
    }

  root = webui_root()
  if not _is_git_repo(root):
    return {"ok": False, "error": "not a git repository"}

  branch = _current_branch(root)
  fetch_r = _run_git(["fetch", "origin", branch], root, timeout=120)
  if fetch_r.returncode != 0:
    err = (fetch_r.stderr or fetch_r.stdout or "git fetch failed").strip()
    return {"ok": False, "error": err}

  pull_r = _run_git(["pull", "--ff-only", "origin", branch], root, timeout=180)
  if pull_r.returncode != 0:
    err = (pull_r.stderr or pull_r.stdout or "git pull failed").strip()
    return {"ok": False, "error": err}

  local_short = current_commit_short(root)
  _write_dismissed(root, "")
  try:
    _dismiss_path(root).unlink()
  except OSError:
    pass

  _cache["ts"] = 0.0
  payload = snapshot_webui_update(fetch=False, use_cache=False)
  return {
    "ok": True,
    "local_short": local_short,
    "remote_short": payload.get("remote_short", local_short),
    "output": (pull_r.stdout or "").strip(),
    "restarted": False,
    "message": "Web UI updated. Reload this page. Restart webui service if server code changed.",
  }
