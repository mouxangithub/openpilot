"""
Copyright (c) 2021-, Haibin Wen, sunnypilot and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""

"""Version history browsing + rollback target (strategy layer only).

Borrowed from StarPilot's ``the_galaxy/version_history.py`` idea, deliberately
NOT its execution layer: StarPilot's installer runs ``git checkout --force``
and deletes ``.overlay_consistent`` to bypass the overlay update mechanism.
Here the strategy layer only *browses*, *persists a rollback target* and
*preflights*; the actual install delegates to the existing tools dispatcher
(``git_checkout``), which runs inside the repo lock with the normal guards.

Pure stdlib, fully injectable (fetcher / runner / clock / paths) so the whole
module unit-tests on a PC without git or network.
"""

import json
import re
import subprocess
import time
import urllib.request
from typing import Any, Callable

RELEASES_TTL = 300.0        # s; GitHub release cache lifetime
RELEASES_MAX = 25           # keep the payload small for the PWA
HISTORY_MAX = 50            # install-history ring size
HTTP_TIMEOUT = 10.0

RUNNER = Callable[..., tuple[int, str, str]]

_REPO_RE = re.compile(r"github\.com[/:]([\w.-]+/[\w.-]+?)(?:\.git)?/?$")


def _state_root() -> str:
  # Same layout as wheel_controls/store.py: /data/carrot/state on device,
  # CARROT_DATA_DIR override, temp-dir fallback on a development host.
  import os
  override = os.getenv("CARROT_DATA_DIR")
  if override:
    return override.rstrip("/\\") + "/state"
  if os.path.isdir("/data"):
    return "/data/carrot/state"
  return os.path.join(os.path.dirname(os.path.abspath(__file__)), ".state")


def _read_json(path: str, default: Any) -> Any:
  try:
    with open(path, encoding="utf-8") as f:
      return json.load(f)
  except (OSError, ValueError):
    return default


def _write_json(path: str, value: Any, mode: int = 0o600) -> None:
  import os
  import uuid
  target: str = path
  os.makedirs(os.path.dirname(target), exist_ok=True)
  temporary = f"{target}.{uuid.uuid4().hex}.tmp"
  with open(temporary, "x", encoding="utf-8") as f:
    os.chmod(temporary, mode)
    json.dump(value, f, ensure_ascii=False)
  os.replace(temporary, target)


# ------------------------------- releases ------------------------------------


def parse_github_repo(remote_url: str) -> str | None:
  """"git@github.com:owner/name.git" | "https://github.com/owner/name" -> "owner/name"."""
  match = _REPO_RE.search(str(remote_url or ""))
  return match.group(1) if match else None


def default_repo(runner: RUNNER | None = None, repo_dir: str = "/data/openpilot") -> str | None:
  """The GitHub identity of the checked-out origin, so nothing is hardcoded."""
  runner = runner or _git_runner
  rc, out, _ = runner(["git", "remote", "get-url", "origin"], cwd=repo_dir)
  return parse_github_repo(out) if rc == 0 else None


def normalize_releases(raw: Any) -> list[dict[str, Any]]:
  """Shape the GitHub API answer down to what the PWA renders."""
  if not isinstance(raw, list):
    return []
  releases = []
  for item in raw:
    if not isinstance(item, dict) or not item.get("tag_name"):
      continue
    releases.append({
      "tag": str(item["tag_name"]),
      "name": str(item.get("name") or item["tag_name"]),
      "published_at": item.get("published_at"),
      "prerelease": bool(item.get("prerelease", False)),
    })
  return releases[:RELEASES_MAX]


def _github_fetch(url: str) -> Any:
  request = urllib.request.Request(url, headers={"User-Agent": "sunnypilot-carrot", "Accept": "application/vnd.github+json"})
  with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
    return json.loads(response.read().decode("utf-8"))


def fetch_releases(repo: str, fetcher: Callable[[str], Any] | None = None,
                   cache_path: str | None = None, now: float | None = None,
                   ttl: float = RELEASES_TTL) -> dict[str, Any]:
  """Cached GitHub releases for ``repo``; stale cache is served on fetch errors."""
  fetcher = fetcher or _github_fetch
  cache_path = cache_path or _state_root() + "/version_releases.json"
  now = time.time() if now is None else now
  cached = _read_json(cache_path, {})
  if isinstance(cached.get("releases"), list) and \
          isinstance(cached.get("fetched_at"), (int, float)) and 0 <= now - cached["fetched_at"] <= ttl:
    return {"ok": True, "cached": True, "fetched_at": cached["fetched_at"], "releases": cached["releases"]}

  try:
    releases = normalize_releases(fetcher(f"https://api.github.com/repos/{repo}/releases?per_page={RELEASES_MAX}"))
  except Exception as exc:
    if isinstance(cached.get("releases"), list):
      return {"ok": True, "cached": True, "stale": True, "error": str(exc),
              "fetched_at": cached.get("fetched_at"), "releases": cached["releases"]}
    return {"ok": False, "error": str(exc), "releases": []}

  _write_json(cache_path, {"fetched_at": now, "releases": releases})
  return {"ok": True, "cached": False, "fetched_at": now, "releases": releases}


# ----------------------------- rollback target -------------------------------


def _rollback_path() -> str:
  return _state_root() + "/rollback_target.json"


def set_rollback_target(ref: str, note: str = "", path: str | None = None,
                        now: float | None = None) -> dict[str, Any]:
  ref = str(ref or "").strip()
  if not ref or any(ch.isspace() for ch in ref) or ref.startswith("-"):
    raise ValueError("invalid git ref")
  target = {"ref": ref, "note": str(note or ""), "set_at": time.time() if now is None else now}
  _write_json(path or _rollback_path(), target)
  return target


def get_rollback_target(path: str | None = None) -> dict[str, Any] | None:
  value = _read_json(path or _rollback_path(), None)
  return value if isinstance(value, dict) and value.get("ref") else None


def clear_rollback_target(path: str | None = None) -> bool:
  import os
  path = path or _rollback_path()
  try:
    os.remove(path)
    return True
  except OSError:
    return False


# -------------------------------- preflight ----------------------------------


def _git_runner(args: list[str], cwd: str = "/data/openpilot", timeout: float = 30.0) -> tuple[int, str, str]:
  proc = subprocess.run(args, cwd=cwd, timeout=timeout, capture_output=True, text=True)
  return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def preflight(repo_dir: str, ref: str, runner: RUNNER | None = None,
              cwd: str = "/data/openpilot") -> dict[str, Any]:
  """Everything the dispatcher's checkout would need, checked up front.

  Read-only: two ``git`` queries, no working-tree mutation. ``blockers`` is
  empty exactly when handing the ref to ``git_checkout`` is safe.
  """
  runner = runner or _git_runner
  ref = str(ref or "").strip()
  result: dict[str, Any] = {"ref": ref, "ok": False, "blockers": []}

  rc, out, _ = runner(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=cwd)
  result["exists"] = rc == 0
  if rc != 0:
    result["blockers"].append(f"ref does not exist: {ref}")
    return result
  result["commit"] = out

  rc, out, _ = runner(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
  result["current"] = out if rc == 0 else None

  rc, out, _ = runner(["git", "status", "--porcelain"], cwd=cwd)
  result["dirty"] = rc == 0 and bool(out.strip())
  if result["dirty"]:
    result["blockers"].append("worktree has uncommitted changes")

  rc, out, _ = runner(["git", "merge-base", "--is-ancestor", ref, "HEAD"], cwd=cwd)
  result["is_rollback"] = rc == 0  # ref is behind HEAD: a true rollback

  result["ok"] = not result["blockers"]
  return result


# ----------------------------- install history -------------------------------


def _history_path() -> str:
  return _state_root() + "/version_install_history.json"


def record_install(entry: dict[str, Any], path: str | None = None,
                   now: float | None = None) -> list[dict[str, Any]]:
  history = _read_json(path or _history_path(), [])
  if not isinstance(history, list):
    history = []
  entry = dict(entry)
  entry.setdefault("at", time.time() if now is None else now)
  history.insert(0, entry)
  history = history[:HISTORY_MAX]
  _write_json(path or _history_path(), history)
  return history


def install_history(path: str | None = None) -> list[dict[str, Any]]:
  history = _read_json(path or _history_path(), [])
  return history if isinstance(history, list) else []
