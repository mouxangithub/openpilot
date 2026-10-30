"""git_status must never write to the real checkout.

The launcher installs a downloaded overlay update at boot only when nothing
under /data/openpilot/.git is newer than .overlay_init. The periodic status
fetch used to run against the real repo, so .git was always newer and every
downloaded update was silently skipped at reboot. These tests pin the contract:
correct behind/ahead counts, and a byte-untouched real .git.
"""
import asyncio
import subprocess
from pathlib import Path

import pytest

from openpilot.sunnypilot.carrot.server.services import git_status
from openpilot.common import repo_update


def _git(*args: str, cwd=None) -> None:
  subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _snapshot(root: Path) -> dict:
  return {str(p.relative_to(root)): p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}


@pytest.fixture()
def repo(tmp_path, monkeypatch):
  seed = tmp_path / "seed"
  seed.mkdir()
  _git("init", "-b", "master", cwd=seed)
  _git("config", "user.email", "test@test", cwd=seed)
  _git("config", "user.name", "test", cwd=seed)
  (seed / "f.txt").write_text("a\n")
  _git("add", "-A", cwd=seed)
  _git("commit", "-m", "a", cwd=seed)

  origin = tmp_path / "origin.git"
  _git("clone", "--bare", str(seed), str(origin))

  work = tmp_path / "work"
  _git("clone", str(origin), str(work))
  _git("config", "user.email", "test@test", cwd=work)
  _git("config", "user.name", "test", cwd=work)

  monkeypatch.setattr(git_status, "REPO_DIR", str(work))
  monkeypatch.setattr(git_status, "STATUS_GIT_DIR", str(tmp_path / "status_mirror"))
  monkeypatch.setattr(repo_update, "LOCK_PATH", str(tmp_path / "repo.lock"))
  return work, origin, seed


def _advance_origin(origin: Path, seed: Path, content: str) -> str:
  (seed / "f.txt").write_text(content + "\n")
  _git("add", "-A", cwd=seed)
  _git("commit", "-m", content, cwd=seed)
  _git("push", str(origin), "master", cwd=seed)
  out = subprocess.run(["git", "rev-parse", "master"], cwd=origin, check=True, capture_output=True, text=True)
  return out.stdout.strip()


def test_behind_count_detected_without_touching_real_git(repo):
  work, origin, seed = repo
  tip = _advance_origin(origin, seed, "b")

  before = _snapshot(work / ".git")
  status = asyncio.run(git_status.get_git_status(force=True))
  after = _snapshot(work / ".git")

  assert status["state"] == "ok"
  assert status["behind"] == 1
  assert status["ahead"] == 0
  assert status["target_head"] == tip
  # The whole point: not one byte of the real .git may change, or the launcher
  # skips the overlay update install at the next boot.
  assert after == before
  assert not (work / ".git" / "FETCH_HEAD").exists()


def test_ahead_and_behind_counted_together(repo):
  work, origin, seed = repo
  _advance_origin(origin, seed, "b")
  asyncio.run(git_status.get_git_status(force=True))

  (work / "local.txt").write_text("local\n")
  _git("add", "-A", cwd=work)
  _git("commit", "-m", "local", cwd=work)

  before = _snapshot(work / ".git")
  status = asyncio.run(git_status.get_git_status(force=True))

  assert status["state"] == "ok"
  assert status["behind"] == 1
  assert status["ahead"] == 1
  assert _snapshot(work / ".git") == before


def test_up_to_date_after_pull(repo):
  work, origin, seed = repo
  _advance_origin(origin, seed, "b")
  _git("pull", "--ff-only", cwd=work)

  status = asyncio.run(git_status.get_git_status(force=True))

  assert status["state"] == "ok"
  assert status["behind"] == 0
  assert status["ahead"] == 0


def test_mirror_self_heals_after_corruption(repo):
  work, origin, seed = repo
  _advance_origin(origin, seed, "b")
  assert asyncio.run(git_status.get_git_status(force=True))["state"] == "ok"

  mirror = Path(git_status.STATUS_GIT_DIR)
  (mirror / "HEAD").write_text("garbage")

  status = asyncio.run(git_status.get_git_status(force=True))
  assert status["state"] == "ok"
  assert status["behind"] == 1


def test_fetch_failure_reports_error_state(repo, monkeypatch):
  work, origin, seed = repo
  _advance_origin(origin, seed, "b")

  async def dead_fetch(url, refspec):
    return 128, "network down"

  monkeypatch.setattr(git_status, "_fetch_status_mirror", dead_fetch)
  status = asyncio.run(git_status.get_git_status(force=True))
  # A failed fetch must not report a usable upstream state.
  assert status["state"] == "fetch_error"
  assert status["available"] is False
