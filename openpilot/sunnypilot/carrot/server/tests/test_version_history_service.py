import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openpilot.sunnypilot.carrot.server.services import version_history as vh


class _TempDirTestCase(unittest.TestCase):
  def setUp(self):
    self._tmp = tempfile.TemporaryDirectory()
    self.tmp = self._tmp.name
    self.addCleanup(self._tmp.cleanup)


def make_runner(commands: dict[tuple, tuple[int, str, str]]):
  """A git runner stub keyed by the first args."""
  def runner(args, cwd="/data/openpilot", timeout=30.0):
    return commands.get(tuple(args), (1, "", "unexpected command"))
  return runner


class TestRepoParsing(_TempDirTestCase):
  def test_parse_github_repo(self):
    self.assertEqual("owner/repo", vh.parse_github_repo("git@github.com:owner/repo.git"))
    self.assertEqual("owner/repo", vh.parse_github_repo("https://github.com/owner/repo"))
    self.assertEqual("owner/repo", vh.parse_github_repo("https://github.com/owner/repo/"))
    self.assertIsNone(vh.parse_github_repo("https://gitlab.com/owner/repo"))
    self.assertIsNone(vh.parse_github_repo(""))

  def test_default_repo_uses_origin(self):
    runner = make_runner({("git", "remote", "get-url", "origin"): (0, "git@github.com:me/mine.git\n", "")})
    self.assertEqual("me/mine", vh.default_repo(runner=runner))
    self.assertIsNone(vh.default_repo(runner=make_runner({})))


class TestReleases(_TempDirTestCase):
  def test_fetches_normalizes_and_caches(self):
    path = f"{self.tmp}/releases.json"
    raw = [{"tag_name": "v1.2.3", "name": "One Two Three", "published_at": "2026-10-01T00:00:00Z", "prerelease": False},
           {"tag_name": "", "name": "broken"},
           "not-a-dict"]
    calls = []
    def fetcher(url):
      calls.append(url)
      return raw
    first = vh.fetch_releases("me/mine", fetcher=fetcher, cache_path=path, now=1000.0)
    self.assertTrue(first["ok"])
    self.assertFalse(first["cached"])
    self.assertEqual(1, len(first["releases"]))
    self.assertEqual("v1.2.3", first["releases"][0]["tag"])
    self.assertEqual(1, len(calls))

    second = vh.fetch_releases("me/mine", fetcher=fetcher, cache_path=path, now=1100.0)  # within TTL
    self.assertTrue(second["cached"])
    self.assertEqual(1, len(calls))  # no second network call

    third = vh.fetch_releases("me/mine", fetcher=fetcher, cache_path=path, now=1000.0 + vh.RELEASES_TTL + 1)
    self.assertFalse(third["cached"])
    self.assertEqual(2, len(calls))

  def test_stale_cache_served_on_fetch_error(self):
    path = f"{self.tmp}/releases.json"
    good = vh.fetch_releases("me/mine", fetcher=lambda url: [{"tag_name": "v1"}], cache_path=path, now=1000.0)
    self.assertTrue(good["ok"])
    def boom(url):
      raise OSError("network down")
    stale = vh.fetch_releases("me/mine", fetcher=boom, cache_path=path, now=1000.0 + vh.RELEASES_TTL + 1)
    self.assertTrue(stale["ok"])
    self.assertTrue(stale["stale"])
    self.assertEqual("v1", stale["releases"][0]["tag"])

  def test_total_failure_reports_error(self):
    def boom(url):
      raise OSError("no network")
    result = vh.fetch_releases("me/mine", fetcher=boom, cache_path=f"{self.tmp}/x.json", now=1000.0)
    self.assertFalse(result["ok"])
    self.assertEqual([], result["releases"])


class TestRollbackTarget(_TempDirTestCase):
  def test_set_get_clear(self):
    path = f"{self.tmp}/rb.json"
    target = vh.set_rollback_target("v1.2.3", note="after bad lane keeps", path=path, now=123.0)
    self.assertEqual("v1.2.3", target["ref"])
    self.assertEqual(123.0, target["set_at"])
    self.assertEqual("v1.2.3", vh.get_rollback_target(path)["ref"])
    self.assertTrue(vh.clear_rollback_target(path))
    self.assertIsNone(vh.get_rollback_target(path))
    self.assertFalse(vh.clear_rollback_target(path))

  def test_rejects_bad_refs(self):
    path = f"{self.tmp}/rb.json"
    for bad in ("", "  ", "a b", "-flag", None):
      with self.assertRaises(ValueError):
        vh.set_rollback_target(bad, path=path)
    self.assertIsNone(vh.get_rollback_target(path))


class TestPreflight(_TempDirTestCase):
  def test_ok_rollback(self):
    runner = make_runner({
      ("git", "rev-parse", "--verify", "v1.0.0^{commit}"): (0, "abc123", ""),
      ("git", "rev-parse", "--abbrev-ref", "HEAD"): (0, "test", ""),
      ("git", "status", "--porcelain"): (0, "", ""),
      ("git", "merge-base", "--is-ancestor", "v1.0.0", "HEAD"): (0, "", ""),
    })
    result = vh.preflight("/data/openpilot", "v1.0.0", runner=runner)
    self.assertTrue(result["ok"])
    self.assertEqual([], result["blockers"])
    self.assertTrue(result["is_rollback"])
    self.assertEqual("abc123", result["commit"])

  def test_missing_ref_blocked(self):
    runner = make_runner({})
    result = vh.preflight("/data/openpilot", "nope", runner=runner)
    self.assertFalse(result["ok"])
    self.assertTrue(any("does not exist" in b for b in result["blockers"]))

  def test_dirty_worktree_blocked(self):
    runner = make_runner({
      ("git", "rev-parse", "--verify", "v1.0.0^{commit}"): (0, "abc123", ""),
      ("git", "status", "--porcelain"): (0, " M some/file.py\n", ""),
      ("git", "merge-base", "--is-ancestor", "v1.0.0", "HEAD"): (0, "", ""),
    })
    result = vh.preflight("/data/openpilot", "v1.0.0", runner=runner)
    self.assertFalse(result["ok"])
    self.assertTrue(any("uncommitted" in b for b in result["blockers"]))


class TestInstallHistory(_TempDirTestCase):
  def test_record_capped_and_ordered(self):
    path = f"{self.tmp}/hist.json"
    for i in range(vh.HISTORY_MAX + 5):
      vh.record_install({"ref": f"v{i}"}, path=path, now=float(i))
    history = vh.install_history(path)
    self.assertEqual(vh.HISTORY_MAX, len(history))
    self.assertEqual(f"v{vh.HISTORY_MAX + 4}", history[0]["ref"])  # newest first
    self.assertEqual(f"v5", history[-1]["ref"])  # oldest surviving after the cap

  def test_corrupt_history_is_empty(self):
    path = Path(self.tmp) / "hist.json"
    path.write_text("not json", encoding="utf-8")
    self.assertEqual([], vh.install_history(str(path)))


if __name__ == "__main__":
  unittest.main()
