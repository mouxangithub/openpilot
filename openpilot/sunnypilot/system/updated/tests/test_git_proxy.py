"""
Copyright (c) 2026-, sunnypilot.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import os
import sys
import tempfile
import types
import unittest

# cloudlog pulls in the hardware stack, which needs opendbc; that is a device
# dependency. Stub it so these pure-logic tests run on a PC — but only when
# the real module cannot be imported: other suites in the same process (the
# branch migration tests) need the real swaglog, and a stub installed here
# would shadow it for them.
try:
  import openpilot.common.swaglog  # noqa: F401
except Exception:
  stub = types.ModuleType("openpilot.common.swaglog")
  stub.cloudlog = types.SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None,
                                        exception=lambda *a, **k: None)
  sys.modules["openpilot.common.swaglog"] = stub

from openpilot.sunnypilot.system.updated.git_proxy import (
  MAX_ACCEPTABLE_MS,
  PROBE_TIMEOUT_S,
  ProbeResult,
  build_candidates,
  probe_once,
  probe_source,
  proxy_url_for,
  read_gitmodules,
  select_best,
  upstream_urls_from_gitmodules,
)


class TestBuildCandidates(unittest.TestCase):
  def test_official_source_is_first(self):
    candidates = build_candidates("https://github.com/x/y.git")
    self.assertEqual(candidates[0], "https://github.com/x/y.git")

  def test_proxies_wrap_the_upstream_url(self):
    candidates = build_candidates("https://github.com/x/y.git")
    self.assertIn("https://gh-proxy.com/https://github.com/x/y.git", candidates)
    self.assertIn("https://cdn.gh-proxy.org/https://github.com/x/y.git", candidates)

  def test_proxies_can_be_disabled(self):
    candidates = build_candidates("https://github.com/x/y.git", use_proxies=False)
    self.assertEqual(candidates, ["https://github.com/x/y.git"])

  def test_proxy_url_for(self):
    self.assertEqual(
      proxy_url_for("https://github.com/x/y.git", "https://gh-proxy.com/"),
      "https://gh-proxy.com/https://github.com/x/y.git",
    )


class TestSelectBest(unittest.TestCase):
  def test_picks_the_fastest_healthy_source(self):
    results = [
      ProbeResult("https://github.com/x.git", True, 900, [900]),
      ProbeResult("https://gh-proxy.com/https://github.com/x.git", True, 300, [300]),
    ]
    best = select_best(results)
    self.assertIsNotNone(best)
    self.assertEqual(best.median_ms, 300)

  def test_official_source_wins_a_tie(self):
    results = [
      ProbeResult("https://github.com/x.git", True, 500, [500]),
      ProbeResult("https://gh-proxy.com/https://github.com/x.git", True, 500, [500]),
    ]
    best = select_best(results)
    self.assertIsNotNone(best)
    self.assertEqual(best.url, "https://github.com/x.git")

  def test_a_failing_source_is_never_chosen(self):
    results = [
      ProbeResult("https://github.com/x.git", False, 100, [100], "timeout"),
      ProbeResult("https://gh-proxy.com/https://github.com/x.git", True, 3000, [3000]),
    ]
    best = select_best(results)
    self.assertIsNotNone(best)
    self.assertEqual(best.url, "https://gh-proxy.com/https://github.com/x.git")

  def test_no_healthy_source_returns_none(self):
    results = [ProbeResult("https://github.com/x.git", False, 100, [100], "timeout")]
    self.assertIsNone(select_best(results))

  def test_a_slow_source_is_rejected(self):
    results = [ProbeResult("https://github.com/x.git", True, MAX_ACCEPTABLE_MS + 1, [MAX_ACCEPTABLE_MS + 1])]
    self.assertIsNone(select_best(results))

  def test_empty_results_return_none(self):
    self.assertIsNone(select_best([]))


class TestProbe(unittest.TestCase):
  def test_probe_of_an_unreachable_source_fails(self):
    ok, ms, err = probe_once("https://127.0.0.1:1/x.git", timeout_s=5)
    self.assertFalse(ok)
    self.assertGreaterEqual(ms, 0)
    self.assertTrue(err)

  def test_probe_source_reports_a_failure(self):
    result = probe_source("https://127.0.0.1:1/x.git", samples=2)
    self.assertFalse(result.ok)
    self.assertTrue(result.error)

  def test_probe_stops_at_the_deadline(self):
    """A slow source must not hold up the whole probe.

    The updater answers a user-initiated check, so the probe has to stay
    inside its budget even when several sources hang.
    """
    import time

    deadline = time.monotonic() + 0.01
    result = probe_source("https://127.0.0.1:1/x.git", samples=3, deadline=deadline)
    self.assertFalse(result.ok)
    self.assertLessEqual(len(result.samples), 3)

  def test_an_expired_deadline_takes_no_samples(self):
    import time

    result = probe_source("https://127.0.0.1:1/x.git", samples=3,
                           deadline=time.monotonic() - 1)
    self.assertFalse(result.ok)
    self.assertEqual(result.samples, [])

  def test_one_flaky_sample_does_not_condemn_a_working_source(self):
    """A source that answers on the retry is usable.

    These links time out intermittently; condemning a source on its first
    timeout would throw away a working mirror.
    """
    calls = []

    def fake_probe(url, cwd=None, timeout_s=PROBE_TIMEOUT_S):
      calls.append(url)
      if len(calls) == 1:
        return False, 12000, "timeout"
      return True, 1800, ""

    import openpilot.sunnypilot.system.updated.git_proxy as mod
    original = mod.probe_once
    mod.probe_once = fake_probe
    try:
      result = mod.probe_source("https://example.test/x.git", samples=3)
    finally:
      mod.probe_once = original

    self.assertTrue(result.ok)
    # the median is taken over the answers that came back
    self.assertEqual(result.median_ms, 1800)

  def test_a_source_that_never_answers_is_failed(self):
    calls = []

    def fake_probe(url, cwd=None, timeout_s=PROBE_TIMEOUT_S):
      calls.append(url)
      return False, 900, "timeout"

    import openpilot.sunnypilot.system.updated.git_proxy as mod
    original = mod.probe_once
    mod.probe_once = fake_probe
    try:
      result = mod.probe_source("https://example.test/x.git", samples=3)
    finally:
      mod.probe_once = original

    self.assertFalse(result.ok)
    self.assertEqual(result.error, "timeout")


class TestMeasureAndSelect(unittest.TestCase):
  """The selection runs the probes concurrently, so it needs its own cover."""

  def test_official_source_wins_when_it_is_fastest(self):
    import openpilot.sunnypilot.system.updated.git_proxy as mod

    def fake_probe(url, cwd=None, timeout_s=PROBE_TIMEOUT_S):
      if "github.com/" in url and "gh-" not in url and "cdn" not in url and "fast" not in url and "proxy.net" not in url:
        return True, 900, ""
      return True, 3000, ""

    original = mod.probe_once
    mod.probe_once = fake_probe
    try:
      best, prefix = mod.measure_and_select(".", "https://github.com/x/y.git", budget_s=5)
    finally:
      mod.probe_once = original

    self.assertIsNotNone(best)
    self.assertEqual(best.url, "https://github.com/x/y.git")
    self.assertEqual(prefix, "")

  def test_a_proxy_wins_when_the_official_source_is_down(self):
    import openpilot.sunnypilot.system.updated.git_proxy as mod

    official = "https://github.com/x/y.git"

    def fake_probe(url, cwd=None, timeout_s=PROBE_TIMEOUT_S):
      if url == official:
        return False, 30, "timeout"
      return True, 1200, ""

    original = mod.probe_once
    mod.probe_once = fake_probe
    try:
      best, prefix = mod.measure_and_select(".", official, budget_s=5)
    finally:
      mod.probe_once = original

    self.assertIsNotNone(best)
    self.assertNotEqual(best.url, official)
    self.assertTrue(prefix)
    self.assertEqual(best.url, prefix + official)

  def test_no_usable_source_returns_none(self):
    import openpilot.sunnypilot.system.updated.git_proxy as mod

    def fake_probe(url, cwd=None, timeout_s=PROBE_TIMEOUT_S):
      return False, 30, "timeout"

    original = mod.probe_once
    mod.probe_once = fake_probe
    try:
      best, prefix = mod.measure_and_select(".", "https://github.com/x/y.git", budget_s=5)
    finally:
      mod.probe_once = original

    self.assertIsNone(best)
    self.assertEqual(prefix, "")


class TestRankedSources(unittest.TestCase):
  """The fetch walks the ranked list, so the order itself needs cover."""

  OFFICIAL = "https://github.com/x/y.git"

  def _rank_with(self, fake_probe):
    import openpilot.sunnypilot.system.updated.git_proxy as mod
    original = mod.probe_once
    mod.probe_once = fake_probe
    try:
      return mod.measure_and_rank(".", self.OFFICIAL, budget_s=5)
    finally:
      mod.probe_once = original

  def test_ranked_list_is_quickest_first(self):
    def fake_probe(url, cwd=None, timeout_s=PROBE_TIMEOUT_S):
      # ghfast.top is quickest, official slowest but alive.
      if "ghfast.top" in url:
        return True, 500, ""
      if url == self.OFFICIAL:
        return True, 4000, ""
      return True, 2000, ""

    ranked = self._rank_with(fake_probe)
    self.assertTrue(ranked)
    self.assertEqual(ranked[0][1], "https://ghfast.top/")
    prefixes = [prefix for _, prefix in ranked]
    self.assertIn("", prefixes)

  def test_ties_keep_the_official_first(self):
    def fake_probe(url, cwd=None, timeout_s=PROBE_TIMEOUT_S):
      return True, 1000, ""

    ranked = self._rank_with(fake_probe)
    self.assertEqual(ranked[0], (ranked[0][0], ""))
    self.assertEqual(ranked[0][0].url, self.OFFICIAL)

  def test_dead_sources_are_not_ranked(self):
    def fake_probe(url, cwd=None, timeout_s=PROBE_TIMEOUT_S):
      return False, 30, "timeout"

    self.assertEqual(self._rank_with(fake_probe), [])

  def test_user_prefixes_are_probed_before_the_builtins(self):
    import openpilot.sunnypilot.system.updated.git_proxy as mod

    candidates = build_candidates(self.OFFICIAL, extra_prefixes=("https://my-proxy.example/",))
    self.assertEqual(candidates[0], self.OFFICIAL)
    self.assertEqual(candidates[1], "https://my-proxy.example/" + self.OFFICIAL)
    # The builtin list still follows, so nothing is lost.
    self.assertIn("https://gh-proxy.com/" + self.OFFICIAL, candidates)

  def test_user_prefix_matching_a_builtin_is_not_duplicated(self):
    candidates = build_candidates(self.OFFICIAL, extra_prefixes=("https://gh-proxy.com",))
    self.assertEqual(candidates.count("https://gh-proxy.com/" + self.OFFICIAL), 1)

  def test_prefix_for(self):
    import openpilot.sunnypilot.system.updated.git_proxy as mod

    self.assertEqual(mod.prefix_for(self.OFFICIAL, self.OFFICIAL), "")
    self.assertEqual(
      mod.prefix_for("https://gh-proxy.com/" + self.OFFICIAL, self.OFFICIAL),
      "https://gh-proxy.com/",
    )


class TestGitmodulesParsing(unittest.TestCase):
  def test_reads_paths_and_urls(self):
    content = (
      '[submodule "panda"]\n'
      "\tpath = panda\n"
      "\turl = https://github.com/mouxangithub/panda.git\n"
      '[submodule "webui"]\n'
      "\tpath = webui\n"
      "\turl = https://github.com/mouxangithub/webui.git\n"
    )
    with tempfile.TemporaryDirectory() as d:
      with open(os.path.join(d, ".gitmodules"), "w", encoding="utf-8") as f:
        f.write(content)
      urls = upstream_urls_from_gitmodules(d)

    self.assertEqual(urls["panda"], "https://github.com/mouxangithub/panda.git")
    self.assertEqual(urls["webui"], "https://github.com/mouxangithub/webui.git")

  def test_section_name_is_kept_apart_from_the_path(self):
    """git keys submodule.<name>.url by section, not by path.

    opendbc's section is "opendbc" while its path is "opendbc_repo", so
    deriving the config key from the path would write a key git ignores.
    """
    content = (
      '[submodule "opendbc"]\n'
      "\tpath = opendbc_repo\n"
      "\turl = https://github.com/mouxangithub/opendbc.git\n"
      '[submodule "jetlink"]\n'
      "\tpath = jetlink_repo\n"
      "\turl = https://github.com/mouxangithub/jetlink.git\n"
    )
    with tempfile.TemporaryDirectory() as d:
      with open(os.path.join(d, ".gitmodules"), "w", encoding="utf-8") as f:
        f.write(content)
      entries = read_gitmodules(d)

    by_section = {section: (path, url) for section, path, url in entries}
    self.assertEqual(by_section["opendbc"][0], "opendbc_repo")
    self.assertEqual(by_section["opendbc"][1], "https://github.com/mouxangithub/opendbc.git")
    self.assertEqual(by_section["jetlink"][0], "jetlink_repo")

  def test_missing_gitmodules_is_empty(self):
    with tempfile.TemporaryDirectory() as d:
      self.assertEqual(upstream_urls_from_gitmodules(d), {})


if __name__ == "__main__":
  unittest.main()
