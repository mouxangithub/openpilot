from __future__ import annotations

import asyncio
import os
import shutil
import time
from typing import Any

from openpilot.common.async_process import run_process
from openpilot.common.repo_update import RepoBusyError, repo_lock


REPO_DIR = "/data/openpilot"
GIT_STATUS_TTL = 600.0
GIT_STATUS_POLL_INTERVAL = 60.0
FETCH_TIMEOUT = 25.0
GIT_TIMEOUT = 8.0
# Bare git dir that absorbs every write of the periodic status fetch
# (FETCH_HEAD, remote-tracking refs, fetched packs). Its objects/info/alternates
# points at the real checkout's object store, so rev-list sees all local objects.
STATUS_GIT_DIR = "/data/.git_status"

_cache: dict[str, Any] | None = None
_lock: asyncio.Lock | None = None


def _now() -> float:
  return time.time()


def _lock_for_loop() -> asyncio.Lock:
  global _lock
  if _lock is None:
    _lock = asyncio.Lock()
  return _lock


def _error_state(message: str, **extra: Any) -> dict[str, Any]:
  return {
    "available": False,
    "state": "error",
    "behind": 0,
    "ahead": 0,
    "branch": "",
    "upstream": "",
    "checked_at": int(_now()),
    "error": message,
    **extra,
  }


async def _git(args: list[str], timeout: float = GIT_TIMEOUT) -> tuple[int, str]:
  try:
    return await run_process(["git", *args], cwd=REPO_DIR, timeout=timeout)
  except TimeoutError:
    return 124, "timeout"
  except Exception as exc:
    return 1, str(exc)


async def _git_text(args: list[str], timeout: float = GIT_TIMEOUT) -> str:
  rc, out = await _git(args, timeout=timeout)
  return out if rc == 0 else ""


async def _mirror_git(args: list[str], timeout: float = GIT_TIMEOUT) -> tuple[int, str]:
  # "--git-dir=" must use the = form: git.c handles this global option by
  # prefix match, not parse-options, so the space-separated form is not accepted.
  return await run_process(["git", f"--git-dir={STATUS_GIT_DIR}", *args], timeout=timeout)


async def _mirror_git_text(args: list[str], timeout: float = GIT_TIMEOUT) -> str:
  rc, out = await _mirror_git(args, timeout=timeout)
  return out if rc == 0 else ""


async def _ensure_status_mirror() -> bool:
  """Create the status mirror once.

  The launcher (launch_chffrplus.sh) installs a downloaded overlay update at
  boot only when nothing under /data/openpilot/.git is newer than
  .overlay_init. Fetching into the real repo writes FETCH_HEAD, remote-tracking
  refs and packs - with a 60 s poll that guard could never pass, so downloaded
  updates were silently skipped on every reboot. All status writes go to the
  mirror instead; the real checkout stays byte-for-byte untouched.
  """
  alternates = os.path.join(STATUS_GIT_DIR, "objects", "info", "alternates")
  if await asyncio.to_thread(os.path.isfile, alternates):
    return True
  rc, out = await run_process(["git", "init", "--bare", STATUS_GIT_DIR], timeout=GIT_TIMEOUT)
  if rc != 0:
    print(f"[git_status] cannot create status mirror {STATUS_GIT_DIR}: {out}")
    return False
  rc, git_dir = await _git(["rev-parse", "--absolute-git-dir"])
  # Forward slashes only: run_process merges stderr into stdout, and git warns
  # on a malformed alternates entry - that warning would corrupt the rev-list
  # output parsed by the caller.
  objects = git_dir.rstrip("/\\") + "/objects" if rc == 0 and git_dir else \
    os.path.join(REPO_DIR, ".git", "objects").replace("\\", "/")

  def _write_alternates() -> None:
    os.makedirs(os.path.dirname(alternates), exist_ok=True)
    # newline="": text mode would otherwise translate \n to \r\n on Windows
    # and git would read the object directory path with a trailing \r.
    with open(alternates, "w", encoding="utf-8", newline="") as f:
      f.write(objects + "\n")

  await asyncio.to_thread(_write_alternates)
  return True


async def _fetch_status_mirror(url: str, refspec: str) -> tuple[int, str]:
  """Fetch into the mirror; rebuild it once if a fetch fails on a damaged one."""
  if not await _ensure_status_mirror():
    return 1, "status mirror unavailable"
  rc, out = await _mirror_git(["fetch", "--quiet", url, refspec], timeout=FETCH_TIMEOUT)
  if rc == 0:
    return 0, ""
  shutil.rmtree(STATUS_GIT_DIR, ignore_errors=True)
  if not await _ensure_status_mirror():
    return 1, "status mirror rebuild failed"
  rc, out = await _mirror_git(["fetch", "--quiet", url, refspec], timeout=FETCH_TIMEOUT)
  return rc, "" if rc == 0 else out


async def _resolve_tracking(branch: str) -> dict[str, str]:
  remote = ""
  remote_branch = ""
  upstream = ""

  if branch:
    remote = await _git_text(["config", "--get", f"branch.{branch}.remote"])
    merge_refs = (await _git_text(["config", "--get-all", f"branch.{branch}.merge"])).splitlines()
    # The repair path reconnects duplicate entries to this selected branch.
    merge_ref = f"refs/heads/{branch}" if len(set(merge_refs)) > 1 else next(iter(merge_refs), "")
    if remote and merge_ref.startswith("refs/heads/"):
      remote_branch = merge_ref[len("refs/heads/"):]
      upstream = f"{remote}/{remote_branch}"

  if not upstream:
    upstream = await _git_text(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if upstream and "/" in upstream:
      remote, remote_branch = upstream.split("/", 1)

  if not remote:
    remotes = (await _git_text(["remote"])).split()
    remote = "origin" if "origin" in remotes else (remotes[0] if remotes else "")

  if remote and not remote_branch and branch:
    remote_branch = branch
    upstream = upstream or f"{remote}/{remote_branch}"

  return {
    "remote": remote,
    "remote_branch": remote_branch,
    "upstream": upstream,
  }


async def _read_status() -> dict[str, Any]:
  rc, inside = await _git(["rev-parse", "--is-inside-work-tree"])
  if rc != 0 or inside.lower() != "true":
    return _error_state("not a git repository")

  head = await _git_text(["rev-parse", "HEAD"])
  branch = await _git_text(["branch", "--show-current"])
  if not branch:
    branch = await _git_text(["rev-parse", "--short", "HEAD"])

  tracking = await _resolve_tracking(branch)
  remote = tracking["remote"]
  remote_branch = tracking["remote_branch"]
  upstream = tracking["upstream"]

  fetch_rc = 0
  fetch_out = ""
  if remote and remote_branch:
    refspec = f"+refs/heads/{remote_branch}:refs/remotes/{remote}/{remote_branch}"
    url = await _git_text(["config", "--get", f"remote.{remote}.url"])
    if url:
      fetch_rc, fetch_out = await _fetch_status_mirror(url, refspec)
    else:
      fetch_rc, fetch_out = 1, f"no url configured for remote {remote}"

  if not upstream:
    return {
      "available": False,
      "state": "no_upstream",
      "behind": 0,
      "ahead": 0,
      "branch": branch,
      "head": head,
      "target_head": "",
      "upstream": "",
      "remote": remote,
      "remote_branch": remote_branch,
      "checked_at": int(_now()),
      "error": "no upstream branch",
      "fetch_error": fetch_out if fetch_rc != 0 else "",
    }

  upstream_ref = f"refs/remotes/{remote}/{remote_branch}"
  # Compare inside the mirror: the real checkout's tracking ref is not
  # refreshed anymore, and rev-list sees every local object via alternates.
  rc, counts = await _mirror_git(["rev-list", "--left-right", "--count", f"{head}...{upstream_ref}"])
  if rc != 0:
    # First-ever fetch failure: the mirror has no tracking ref yet. Fall back
    # to the real checkout's (possibly stale) one - rev-list is read-only, so
    # this keeps the old semantics without writing anything.
    rc, counts = await _git(["rev-list", "--left-right", "--count", f"HEAD...{upstream}"])
  if rc != 0:
    return _error_state(counts or "failed to compare git refs", branch=branch, upstream=upstream)

  parts = counts.split()
  ahead = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
  behind = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
  target_head = await _mirror_git_text(["rev-parse", upstream_ref])

  return {
    "available": fetch_rc == 0,
    "state": "ok" if fetch_rc == 0 else "fetch_error",
    "behind": behind,
    "ahead": ahead,
    "branch": branch,
    "head": head,
    "target_head": target_head,
    "upstream": upstream,
    "remote": remote,
    "remote_branch": remote_branch,
    "checked_at": int(_now()),
    "error": fetch_out if fetch_rc != 0 else "",
  }


async def get_git_status(force: bool = False) -> dict[str, Any]:
  global _cache
  if _cache and not force and (_now() - float(_cache.get("checked_at", 0))) < GIT_STATUS_TTL:
    return dict(_cache)

  async with _lock_for_loop():
    if _cache and not force and (_now() - float(_cache.get("checked_at", 0))) < GIT_STATUS_TTL:
      return dict(_cache)
    try:
      with repo_lock():
        _cache = await _read_status()
    except RepoBusyError:
      return {**_error_state("Build or another Git operation is running"), "state": "busy"}
    return dict(_cache)


def clear_git_status_cache() -> None:
  global _cache
  _cache = None


async def git_status_loop(interval: float = GIT_STATUS_POLL_INTERVAL, initial_delay: float = 8.0) -> None:
  if initial_delay > 0:
    await asyncio.sleep(initial_delay)

  while True:
    try:
      await get_git_status(force=True)
    except asyncio.CancelledError:
      raise
    except Exception as exc:
      print(f"[git_status] periodic check failed: {exc}")
    await asyncio.sleep(interval)
