from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path

from cluster_models import GitBranchStatus


GIT_STATUS_REFRESH_SECONDS = 60.0
GIT_COMMAND_TIMEOUT_SECONDS = 4.0
# Bare git dir that absorbs the periodic behind-count fetch (FETCH_HEAD, remote
# tracking refs, packs), with alternates pointing at the real checkout's object
# store. The launcher installs a downloaded overlay update at boot only when
# nothing under /data/openpilot/.git is newer than .overlay_init; fetching into
# the real repo would keep that guard permanently tripped and silently skip
# every update (same root cause as services/git_status.py).
GIT_STATUS_MIRROR_DIR = Path("/data/.git_status_cluster")


def drop_git_worker_realtime_priority() -> None:
  """Keep periodic network/storage checks out of the render thread's FIFO class."""
  try:
    os.sched_setscheduler(0, os.SCHED_OTHER, os.sched_param(0))
  except (AttributeError, OSError, ValueError):
    pass


def find_git_root(start: Path) -> Path | None:
  path = start.resolve()
  candidates = (path, *path.parents)
  for candidate in candidates:
    if (candidate / ".git").exists():
      return candidate
  return None


def resolve_git_dir(repo_path: Path) -> Path | None:
  git_path = repo_path / ".git"
  if git_path.is_dir():
    return git_path
  if not git_path.is_file():
    return None
  try:
    text = git_path.read_text(encoding="utf-8", errors="replace").strip()
  except OSError:
    return None
  prefix = "gitdir:"
  if not text.lower().startswith(prefix):
    return None
  target = Path(text[len(prefix) :].strip())
  if not target.is_absolute():
    target = repo_path / target
  return target


def read_head_branch(repo_path: Path) -> str | None:
  git_dir = resolve_git_dir(repo_path)
  if git_dir is None:
    return None
  try:
    head = (git_dir / "HEAD").read_text(encoding="utf-8", errors="replace").strip()
  except OSError:
    return None
  ref_prefix = "ref: refs/heads/"
  if head.startswith(ref_prefix):
    return head[len(ref_prefix) :]
  return head[:12] if head else None


class GitBranchStatusProvider:
  def __init__(
    self,
    start_path: Path,
    refresh_interval_s: float = GIT_STATUS_REFRESH_SECONDS,
    command_timeout_s: float = GIT_COMMAND_TIMEOUT_SECONDS,
    remote_enabled: bool = True,
  ) -> None:
    self.repo_path = find_git_root(start_path)
    self.refresh_interval_s = max(5.0, float(refresh_interval_s))
    self.command_timeout_s = max(0.5, float(command_timeout_s))
    self.remote_enabled = bool(remote_enabled)
    initial_branch = read_head_branch(self.repo_path) if self.repo_path is not None else None
    initial_detail = "확인 중" if self.repo_path is not None and self.remote_enabled else ""
    if self.repo_path is None:
      initial_detail = "저장소 없음"
    self._status = GitBranchStatus(initial_branch or "git", "unknown", initial_detail)
    self._next_refresh = 0.0
    self._lock = threading.Lock()
    self._worker: threading.Thread | None = None

  def status(self) -> GitBranchStatus:
    if not self.remote_enabled:
      return self._status
    now = time.monotonic()
    with self._lock:
      worker_alive = self._worker is not None and self._worker.is_alive()
      if self.repo_path is not None and now >= self._next_refresh and not worker_alive:
        self._next_refresh = now + self.refresh_interval_s
        self._worker = threading.Thread(target=self._refresh, name="cluster-git-status", daemon=True)
        self._worker.start()
      return self._status

  def _refresh(self) -> None:
    drop_git_worker_realtime_priority()
    status = self._read_status()
    with self._lock:
      self._status = status

  def _read_status(self) -> GitBranchStatus:
    if self.repo_path is None:
      return GitBranchStatus("git", "unknown", "저장소 없음")

    branch = self._current_branch()
    if branch is None:
      return GitBranchStatus(read_head_branch(self.repo_path) or "HEAD", "unknown", "브렌치 아님")

    remote_name, remote_branch = self._tracking_branch(branch)
    if remote_name is None or remote_branch is None:
      return GitBranchStatus(branch, "missing", "원격 설정 없음")

    remote_exists = self._remote_branch_exists(remote_name, remote_branch)
    if remote_exists is False:
      return GitBranchStatus(branch, "missing", "원격에서 삭제됨")
    if remote_exists is None:
      return GitBranchStatus(branch, "unknown", "원격 확인 실패")

    behind_count = self._behind_count(remote_name, remote_branch)
    if behind_count is None:
      return GitBranchStatus(branch, "unknown", "pull 확인 실패")
    if behind_count > 0:
      return GitBranchStatus(branch, "pull", f"git pull 가능 +{behind_count}")
    return GitBranchStatus(branch, "ok")

  def _current_branch(self) -> str | None:
    result = self._git("branch", "--show-current", timeout_s=1.0)
    if result.returncode == 0:
      branch = result.stdout.strip()
      if branch:
        return branch
    return None

  def _tracking_branch(self, branch: str) -> tuple[str | None, str | None]:
    remotes = self._remote_names()
    if not remotes:
      return None, None

    upstream_result = self._git("for-each-ref", "--format=%(upstream:short)", f"refs/heads/{branch}", timeout_s=1.0)
    upstream = upstream_result.stdout.strip() if upstream_result.returncode == 0 else ""
    if upstream:
      for remote_name in sorted(remotes, key=len, reverse=True):
        prefix = f"{remote_name}/"
        if upstream.startswith(prefix):
          remote_branch = upstream[len(prefix) :]
          if remote_branch:
            return remote_name, remote_branch

    remote_name = "origin" if "origin" in remotes else remotes[0]
    return remote_name, branch

  def _remote_names(self) -> list[str]:
    remotes_result = self._git("remote", timeout_s=1.0)
    if remotes_result.returncode != 0:
      return []
    return [line.strip() for line in remotes_result.stdout.splitlines() if line.strip()]

  def _remote_branch_exists(self, remote_name: str, remote_branch: str) -> bool | None:
    result = self._git(
      "ls-remote",
      "--exit-code",
      "--heads",
      remote_name,
      remote_branch,
      timeout_s=self.command_timeout_s,
    )
    if result.returncode == 0:
      return True
    if result.returncode == 2:
      return False
    return None

  def _behind_count(self, remote_name: str, remote_branch: str) -> int | None:
    url_result = self._git("config", "--get", f"remote.{remote_name}.url", timeout_s=1.0)
    if url_result.returncode != 0 or not url_result.stdout.strip():
      return None
    if not self._ensure_mirror():
      return None

    tracking_ref = f"refs/remotes/{remote_name}/{remote_branch}"
    fetch_result = self._git_mirror(
      "fetch",
      "--quiet",
      url_result.stdout.strip(),
      f"+refs/heads/{remote_branch}:{tracking_ref}",
      timeout_s=self.command_timeout_s,
    )
    if fetch_result.returncode != 0:
      return None

    # The mirror has no HEAD of its own; compare the real checkout's HEAD sha.
    head_result = self._git("rev-parse", "HEAD", timeout_s=1.0)
    if head_result.returncode != 0:
      return None
    result = self._git_mirror("rev-list", "--count", f"{head_result.stdout.strip()}..{tracking_ref}", timeout_s=1.0)
    if result.returncode != 0:
      return None
    try:
      return max(0, int(result.stdout.strip()))
    except ValueError:
      return None

  def _ensure_mirror(self) -> bool:
    """Create the fetch mirror once; it only fails on systems without /data."""
    alternates = GIT_STATUS_MIRROR_DIR / "objects" / "info" / "alternates"
    if alternates.is_file():
      return True
    try:
      GIT_STATUS_MIRROR_DIR.mkdir(parents=True, exist_ok=True)
      # No --git-dir here: init is special-cased by git and must not inherit one.
      init = subprocess.run(
        ("git", "init", "--bare", str(GIT_STATUS_MIRROR_DIR)),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
        timeout=self.command_timeout_s,
      )
      if init.returncode != 0:
        return False
      git_dir = self._git("rev-parse", "--absolute-git-dir", timeout_s=1.0)
      # Forward slashes only: git rejects a malformed alternates entry and
      # warns on stderr, which some callers merge into stdout.
      objects = f"{git_dir.stdout.strip().rstrip('/\\')}/objects" if git_dir.returncode == 0 and git_dir.stdout.strip() \
        else str(self.repo_path / ".git" / "objects").replace("\\", "/")
      alternates.parent.mkdir(parents=True, exist_ok=True)
      # newline="": text mode would translate \n to \r\n on Windows and git
      # would read the object directory path with a trailing carriage return.
      alternates.write_text(objects + "\n", encoding="utf-8", newline="")
      return True
    except OSError:
      return False

  def _git_mirror(self, *args: str, timeout_s: float) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
      return subprocess.run(
        ("git", f"--git-dir={GIT_STATUS_MIRROR_DIR}", *args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=timeout_s,
        check=False,
      )
    except (OSError, subprocess.TimeoutExpired) as exc:
      return subprocess.CompletedProcess(args, returncode=124, stdout="", stderr=str(exc))

  def _git(self, *args: str, timeout_s: float) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
      return subprocess.run(
        ("git", "-C", str(self.repo_path), *args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=timeout_s,
        check=False,
      )
    except (OSError, subprocess.TimeoutExpired) as exc:
      return subprocess.CompletedProcess(args, returncode=124, stdout="", stderr=str(exc))
