"""Unit tests for community wiki ingest helpers (no network)."""

from __future__ import annotations

import unittest

from ai.fork.wiki_ingest import _chunk_text, parse_wiki_source


class TestWikiIngest(unittest.TestCase):
  def test_parse_dragonpilot_wiki_repo(self):
    src = parse_wiki_source("https://github.com/dragonpilot/dragonpilot_wiki")
    self.assertIsNotNone(src)
    assert src is not None
    self.assertEqual(src["kind"], "repo")
    self.assertEqual(src["owner"], "dragonpilot")
    self.assertEqual(src["repo"], "dragonpilot_wiki")

  def test_parse_github_wiki_url(self):
    src = parse_wiki_source("https://github.com/commaai/openpilot/wiki")
    self.assertIsNotNone(src)
    assert src is not None
    self.assertEqual(src["kind"], "github_wiki")

  def test_parse_mediawiki_url(self):
    src = parse_wiki_source("https://frogpilot.wiki.gg/")
    self.assertIsNotNone(src)
    assert src is not None
    self.assertEqual(src["kind"], "mediawiki")
    self.assertEqual(src["base_url"], "https://frogpilot.wiki.gg")

  def test_collect_wiki_sources_merges_branch(self):
    from ai.fork.wiki_ingest import collect_wiki_sources_for_profile

    profile = {
      "id": "test/sp",
      "wiki_repos": [
        {"url": "https://github.com/sunnypilot/user-docs", "branch": "master"},
      ],
    }
    sources = collect_wiki_sources_for_profile(profile)
    self.assertEqual(len(sources), 1)
    self.assertEqual(sources[0]["branch"], "master")

  def test_collect_wiki_sources_merges_branch_and_max_files(self):
    from ai.fork.wiki_ingest import collect_wiki_sources_for_profile

    profile = {
      "id": "dragonpilot/dragonpilot",
      "wiki_repos": [
        {"url": "https://github.com/dragonpilot/dragonpilot_wiki", "branch": "master", "max_files": 80},
      ],
    }
    sources = collect_wiki_sources_for_profile(profile)
    self.assertEqual(len(sources), 1)
    self.assertEqual(sources[0]["branch"], "master")
    self.assertEqual(sources[0]["max_files"], 80)

  def test_parse_discourse_category_url(self):
    src = parse_wiki_source("https://community.sunnypilot.ai/c/documentation/114")
    self.assertIsNotNone(src)
    assert src is not None
    self.assertEqual(src["kind"], "discourse")
    self.assertEqual(src["category_id"], "114")
    self.assertEqual(src["base_url"], "https://community.sunnypilot.ai")

  def test_strip_html_table(self):
    from ai.fork.wiki_ingest import _strip_html

    text = _strip_html("<h1>Title</h1><p>Hello <strong>world</strong></p>")
    self.assertIn("Title", text)
    self.assertIn("Hello world", text)

  def test_discourse_doc_filter(self):
    from ai.fork.wiki_ingest import _discourse_listing_is_doc

    doc = {"pinned": False, "posts_count": 1, "tags": []}
    qa = {"pinned": False, "posts_count": 12, "tags": []}
    tagged = {"pinned": False, "posts_count": 12, "tags": [{"slug": "docs-auto-sync"}]}
    self.assertTrue(_discourse_listing_is_doc(doc, doc_filter=True, doc_tags={"docs-auto-sync"}, max_posts=3))
    self.assertFalse(_discourse_listing_is_doc(qa, doc_filter=True, doc_tags={"docs-auto-sync"}, max_posts=3))
    self.assertTrue(_discourse_listing_is_doc(tagged, doc_filter=True, doc_tags={"docs-auto-sync"}, max_posts=3))

  def test_chunk_splits_long_text(self):
    text = "## A\n" + ("word " * 500) + "\n## B\n" + ("other " * 100)
    chunks = _chunk_text(text, doc_slug="test")
    self.assertGreater(len(chunks), 1)
    for c in chunks:
      self.assertLessEqual(len(c["text"]), 2100)


if __name__ == "__main__":
  unittest.main()
