"""op助手独立包版本与 GitHub 更新检测（P1）。"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

AI_DIR = Path(__file__).resolve().parent
VERSION_FILE = AI_DIR / "VERSION"
INSTALL_DIR = AI_DIR / "install"
UPDATE_SCRIPT = INSTALL_DIR / "update.sh"

DEFAULT_UPSTREAM_SSH = "git@github.com:mouxangithub/ai.git"
DEFAULT_UPSTREAM_HTTPS = "https://github.com/mouxangithub/ai.git"
DEFAULT_BRANCH = "main"
RAW_VERSION_URL = f"https://raw.githubusercontent.com/mouxangithub/ai/{DEFAULT_BRANCH}/VERSION"


def read_version() -> str:
  try:
    return VERSION_FILE.read_text(encoding="utf-8").strip()
  except OSError:
    return "0.0.0"


def _parse_version(ver: str) -> tuple[int, ...]:
  parts = re.findall(r"\d+", ver or "")
  if not parts:
    return (0,)
  return tuple(int(p) for p in parts)


def version_lt(a: str, b: str) -> bool:
  return _parse_version(a) < _parse_version(b)


def _run_git(args: list[str], *, cwd: Path, timeout: int = 45) -> tuple[bool, str]:
  try:
    proc = subprocess.run(
      ["git", *args],
      cwd=str(cwd),
      capture_output=True,
      text=True,
      timeout=timeout,
    )
  except (OSError, subprocess.TimeoutExpired) as exc:
    return False, str(exc)
  out = ((proc.stdout or "") + (proc.stderr or "")).strip()
  return proc.returncode == 0, out


def _git_install_meta() -> dict[str, Any]:
  meta: dict[str, Any] = {
    "is_git_install": (AI_DIR / ".git").is_dir(),
    "git_commit": None,
    "git_branch": None,
    "git_dirty": None,
    "remote_commit": None,
  }
  if not meta["is_git_install"]:
    return meta
  ok, commit = _run_git(["rev-parse", "--short", "HEAD"], cwd=AI_DIR)
  if ok:
    meta["git_commit"] = commit.splitlines()[-1][:12]
  ok, branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=AI_DIR)
  if ok:
    meta["git_branch"] = branch.splitlines()[-1]
  ok, status = _run_git(["status", "--porcelain"], cwd=AI_DIR)
  if ok:
    meta["git_dirty"] = bool(status.strip())
  return meta


def _fetch_remote_version_http() -> str | None:
  try:
    req = urllib.request.Request(RAW_VERSION_URL, headers={"User-Agent": "op-ai-aid"})
    with urllib.request.urlopen(req, timeout=12) as resp:
      return resp.read().decode("utf-8", errors="replace").strip()
  except (urllib.error.URLError, OSError, TimeoutError):
    return None


def _fetch_remote_version_git() -> dict[str, str | None]:
  out: dict[str, str | None] = {"remote_version": None, "remote_commit": None}
  if not (AI_DIR / ".git").is_dir():
    return out
  ok, _ = _run_git(["fetch", "origin", DEFAULT_BRANCH, "--quiet"], cwd=AI_DIR, timeout=60)
  if not ok:
    return out
  ok, ver = _run_git(["show", f"origin/{DEFAULT_BRANCH}:VERSION"], cwd=AI_DIR)
  if ok:
    out["remote_version"] = ver.splitlines()[-1].strip()
  ok, sha = _run_git(["rev-parse", "--short", f"origin/{DEFAULT_BRANCH}"], cwd=AI_DIR)
  if ok:
    out["remote_commit"] = sha.splitlines()[-1][:12]
  return out


def package_info() -> dict[str, Any]:
  return {
    "ok": True,
    "name": "op助手",
    "package": "ai",
    "version": read_version(),
    "install_path": str(AI_DIR),
    "upstream_ssh": DEFAULT_UPSTREAM_SSH,
    "upstream_https": DEFAULT_UPSTREAM_HTTPS,
    "branch": DEFAULT_BRANCH,
    "install_script": str(INSTALL_DIR / "install.sh"),
    "update_script": str(UPDATE_SCRIPT),
    **_git_install_meta(),
  }


def check_update(*, fetch_remote: bool = True) -> dict[str, Any]:
  info = package_info()
  local_version = info["version"]
  remote_version: str | None = None
  remote_commit: str | None = None
  fetch_error: str | None = None

  if fetch_remote:
    git_remote = _fetch_remote_version_git()
    remote_version = git_remote.get("remote_version")
    remote_commit = git_remote.get("remote_commit")
    if not remote_version:
      remote_version = _fetch_remote_version_http()
    if not remote_version and not remote_commit:
      fetch_error = "无法获取远程版本（请检查网络或 GitHub 可达性）"

  update_available = False
  if remote_version and version_lt(local_version, remote_version):
    update_available = True
  elif (
    info.get("is_git_install")
    and remote_commit
    and info.get("git_commit")
    and remote_commit != info.get("git_commit")
    and (not remote_version or remote_version == local_version)
  ):
    update_available = True

  return {
    **info,
    "remote_version": remote_version,
    "remote_commit": remote_commit,
    "update_available": update_available,
    "fetch_error": fetch_error,
    "raw_version_url": RAW_VERSION_URL,
  }


def run_package_update(*, openpilot_root: str | None = None) -> dict[str, Any]:
  """Run install/update.sh (git pull) in the ai package directory."""
  script = UPDATE_SCRIPT if UPDATE_SCRIPT.is_file() else INSTALL_DIR / "install.sh"
  if not script.is_file():
    return {"ok": False, "error": f"更新脚本不存在: {script}"}

  env = os.environ.copy()
  root = openpilot_root or str(AI_DIR.parent)
  env["OPENPILOT_ROOT"] = root
  try:
    proc = subprocess.run(
      ["bash", str(script), "--update"],
      cwd=str(AI_DIR),
      capture_output=True,
      text=True,
      timeout=120,
      env=env,
    )
  except (OSError, subprocess.TimeoutExpired) as exc:
    return {"ok": False, "error": str(exc)}

  stdout = (proc.stdout or "").strip()[-4000:]
  stderr = (proc.stderr or "").strip()[-2000:]
  result = {
    "ok": proc.returncode == 0,
    "exit_code": proc.returncode,
    "stdout": stdout,
    "stderr": stderr,
    "version": read_version(),
    **package_info(),
  }
  if proc.returncode != 0:
    result["error"] = stderr or stdout or "git pull 失败"
    return result

  integrate_py = INSTALL_DIR / "integrate_openpilot.py"
  if integrate_py.is_file():
    try:
      integ = subprocess.run(
        [sys.executable, str(integrate_py), "--root", root],
        capture_output=True,
        text=True,
        timeout=1800,
        env={**env, "PYTHONPATH": root},
      )
      result["integrate_exit_code"] = integ.returncode
      result["integrate_output"] = ((integ.stdout or "") + (integ.stderr or "")).strip()[-4000:]
      if integ.returncode != 0:
        result["integrate_warning"] = "git 更新成功，但 openpilot 集成未完全成功"
    except (OSError, subprocess.TimeoutExpired) as exc:
      result["integrate_warning"] = str(exc)

  result["version"] = read_version()
  return result
