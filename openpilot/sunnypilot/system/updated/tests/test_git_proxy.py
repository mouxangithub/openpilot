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
# dependency. Stub it so these pure-logic tests run on a PC.
if "openpilot.common.swaglog" not in sys.modules:
  stub = types.ModuleType("openpilot.common.swaglog")
  stub.cloudlog = types.SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None,
                                        exception=lambda *a, **k: None)
  sys.modules["openpilot.common.swaglog"] = stub

from openpilot.sunnypilot.system.updated.git_proxy import (
  MAX_ACCEPTABLE_MS,
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
