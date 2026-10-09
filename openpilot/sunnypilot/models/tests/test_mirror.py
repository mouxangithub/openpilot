"""
Copyright (c) 2026-, mouxan.

Unit tests for the model download mirror helpers (openpilot.sunnypilot.models.mirror).
"""
import unittest

from openpilot.sunnypilot.models.mirror import (DEFAULT_HF_MIRROR, apply_hf_mirror, catalog_fetch_candidates,
                                                describe_github_proxy, describe_hf_mirror, get_github_proxy,
                                                get_hf_mirror_base, github_raw_to_jsdelivr, normalize_base_url)

# short aliases keep the param dicts below readable
HF = "ModelManager_MirrorUrl"
GH = "ModelManager_GithubProxy"

HF_FILE_URL = "https://huggingface.co/datasets/sunnypilot/sunnypilot_models_v1/resolve/main/models/x/driving_x.pkl"
CATALOG_URL = "https://raw.githubusercontent.com/sunnypilot/sunnypilot-models/refs/heads/gh-pages/docs/driving_models_v22.json"
LEGACY_RAW_URL = "https://raw.githubusercontent.com/sunnypilot/sunnypilot-models/gh-pages/docs/driving_models_v22.json"


class FakeParams:
  def __init__(self, values=None):
    self.values = dict(values or {})

  def get(self, key, **kwargs):
    return self.values.get(key)


class TestNormalizeBaseUrl(unittest.TestCase):
  def test_strips_trailing_slashes(self):
    self.assertEqual(normalize_base_url("https://hf-mirror.com///"), "https://hf-mirror.com")

  def test_rejects_non_http(self):
    self.assertIsNone(normalize_base_url("hf-mirror.com"))
    self.assertIsNone(normalize_base_url("ftp://hf-mirror.com"))

  def test_rejects_spaces_and_empty(self):
    self.assertIsNone(normalize_base_url("https://hf mirror.com"))
    self.assertIsNone(normalize_base_url("  "))
    self.assertIsNone(normalize_base_url(None))
    self.assertIsNone(normalize_base_url("https://"))

  def test_accepts_valid(self):
    self.assertEqual(normalize_base_url(" https://my.mirror.cn/ "), "https://my.mirror.cn")


class TestHfMirror(unittest.TestCase):
  def test_unset_uses_default_mirror(self):
    self.assertEqual(get_hf_mirror_base(FakeParams()), DEFAULT_HF_MIRROR)
    self.assertEqual(get_hf_mirror_base(FakeParams({HF: ""})), DEFAULT_HF_MIRROR)

  def test_off_disables_mirror(self):
    self.assertEqual(get_hf_mirror_base(FakeParams({HF: "off"})), "")
    self.assertEqual(get_hf_mirror_base(FakeParams({HF: "OFF"})), "")

  def test_custom_base_normalized(self):
    self.assertEqual(get_hf_mirror_base(FakeParams({HF: "https://my.mirror.cn/"})), "https://my.mirror.cn")

  def test_invalid_falls_back_to_default(self):
    self.assertEqual(get_hf_mirror_base(FakeParams({HF: "not a url"})), DEFAULT_HF_MIRROR)

  def test_apply_rewrites_hf_urls(self):
    mirrored = apply_hf_mirror(HF_FILE_URL, "https://hf-mirror.com")
    self.assertTrue(mirrored.startswith("https://hf-mirror.com/datasets/sunnypilot/"))
    self.assertIn("driving_x.pkl", mirrored)

  def test_apply_leaves_other_hosts_alone(self):
    url = "https://example.com/models/x.pkl"
    self.assertEqual(apply_hf_mirror(url, "https://hf-mirror.com"), url)

  def test_apply_without_base_is_noop(self):
    self.assertEqual(apply_hf_mirror(HF_FILE_URL, ""), HF_FILE_URL)

  def test_chunk_urls_inherit_the_rewrite(self):
    from openpilot.common.file_chunker import get_chunk_name
    base = apply_hf_mirror(HF_FILE_URL, "https://hf-mirror.com")
    self.assertEqual(get_chunk_name(base, 0, 2), base + ".chunk01of02")

  def test_describe(self):
    self.assertEqual(describe_hf_mirror(FakeParams()), DEFAULT_HF_MIRROR)
    self.assertEqual(describe_hf_mirror(FakeParams({HF: "off"})), "huggingface.co")


class TestGithubProxy(unittest.TestCase):
  def test_unset_is_auto(self):
    self.assertEqual(get_github_proxy(FakeParams()), "")

  def test_direct_disables_fallback(self):
    self.assertEqual(get_github_proxy(FakeParams({GH: "direct"})), "direct")
    self.assertEqual(get_github_proxy(FakeParams({GH: "Direct"})), "direct")

  def test_prefix_gets_trailing_slash(self):
    self.assertEqual(get_github_proxy(FakeParams({GH: "https://gh-proxy.com"})), "https://gh-proxy.com/")

  def test_invalid_prefix_ignored(self):
    self.assertEqual(get_github_proxy(FakeParams({GH: "no scheme here"})), "")

  def test_jsdelivr_mapping_current_form(self):
    self.assertEqual(
      github_raw_to_jsdelivr(CATALOG_URL),
      "https://cdn.jsdelivr.net/gh/sunnypilot/sunnypilot-models@gh-pages/docs/driving_models_v22.json")

  def test_jsdelivr_mapping_legacy_form(self):
    self.assertEqual(
      github_raw_to_jsdelivr(LEGACY_RAW_URL),
      "https://cdn.jsdelivr.net/gh/sunnypilot/sunnypilot-models@gh-pages/docs/driving_models_v22.json")

  def test_jsdelivr_mapping_rejects_other_hosts(self):
    self.assertIsNone(github_raw_to_jsdelivr("https://example.com/a/b/c/d"))
    self.assertIsNone(github_raw_to_jsdelivr("https://raw.githubusercontent.com/owner/repo"))

  def test_candidates_auto_direct_then_fallback(self):
    self.assertEqual(catalog_fetch_candidates(CATALOG_URL, FakeParams()), [CATALOG_URL, github_raw_to_jsdelivr(CATALOG_URL)])

  def test_candidates_proxy_first_then_fallback(self):
    proxy = FakeParams({GH: "https://gh-proxy.com"})
    self.assertEqual(catalog_fetch_candidates(CATALOG_URL, proxy),
                     ["https://gh-proxy.com/" + CATALOG_URL, github_raw_to_jsdelivr(CATALOG_URL)])

  def test_candidates_direct_only(self):
    self.assertEqual(catalog_fetch_candidates(CATALOG_URL, FakeParams({GH: "direct"})), [CATALOG_URL])

  def test_candidates_non_raw_url_gets_no_fallback(self):
    url = "https://example.com/catalog.json"
    self.assertEqual(catalog_fetch_candidates(url, FakeParams()), [url])

  def test_describe(self):
    self.assertEqual(describe_github_proxy(FakeParams()), "auto")
    self.assertEqual(describe_github_proxy(FakeParams({GH: "direct"})), "raw.githubusercontent.com")
    self.assertEqual(describe_github_proxy(FakeParams({GH: "https://gh-proxy.com"})), "https://gh-proxy.com/")


if __name__ == "__main__":
  unittest.main()
