"""
Copyright (c) 2026-, mouxan.

Unit tests for the model source latency probe (openpilot.sunnypilot.models.http_probe).
All HTTP goes through a stubbed requests.get, so these run anywhere.
"""
import time
import unittest
from unittest import mock

from openpilot.sunnypilot.models import http_probe


def _response(status=206, chunks=(b"x" * 4096,)):
  """A context-manager stub shaped like a streamed requests response."""
  class _Resp:
    def __init__(self):
      self.status_code = status

    def __enter__(self):
      return self

    def __exit__(self, *args):
      return False

    def iter_content(self, chunk_size=4096):
      yield from chunks
  return _Resp()


def _get_stub(responses, calls=None):
  """A requests.get stand-in that records (url, headers) and yields canned responses."""
  calls = calls if calls is not None else []

  def fake_get(url, headers=None, **kwargs):
    calls.append((url, headers))
    return responses[url if url in responses else "default"]()
  return fake_get


class TestProbeOnce(unittest.TestCase):
  def setUp(self):
    http_probe.clear_cache()

  def test_healthy_partial_content(self):
    calls = []
    with mock.patch.object(http_probe.requests, "get", _get_stub({"default": _response}, calls)):
      ok, ms, err = http_probe.probe_once("https://a.example/f.json")
    self.assertTrue(ok)
    self.assertEqual(err, "")
    self.assertGreaterEqual(ms, 0)
    url, headers = calls[0]
    self.assertEqual(url, "https://a.example/f.json")
    self.assertEqual(headers["Range"], http_probe.PROBE_RANGE)

  def test_http_error_is_down(self):
    with mock.patch.object(http_probe.requests, "get", _get_stub({"default": lambda: _response(status=403)})):
      ok, _, err = http_probe.probe_once("https://a.example/f.json")
    self.assertFalse(ok)
    self.assertIn("403", err)

  def test_empty_body_is_not_up(self):
    # a captive portal answering 200 with no bytes is not a working source
    with mock.patch.object(http_probe.requests, "get", _get_stub({"default": lambda: _response(chunks=())})):
      ok, _, err = http_probe.probe_once("https://a.example/f.json")
    self.assertFalse(ok)
    self.assertEqual(err, "empty body")

  def test_exception_is_down_not_fatal(self):
    def boom(url, **kwargs):
      raise http_probe.requests.ConnectionError("reset by peer")
    with mock.patch.object(http_probe.requests, "get", boom):
      ok, _, err = http_probe.probe_once("https://a.example/f.json")
    self.assertFalse(ok)
    self.assertIn("reset", err)


class TestProbeSorted(unittest.TestCase):
  def setUp(self):
    http_probe.clear_cache()

  def _patch(self, delays):
    """delays: url -> (ok, ms). Each probe_once call returns the canned result."""
    def fake_probe_once(url, timeout_s=0):
      ok, ms = delays[url]
      return ok, ms, "" if ok else "down"
    return mock.patch.object(http_probe, "probe_once", fake_probe_once)

  def test_single_url_untouched(self):
    with self._patch({"https://a/1": (True, 500)}):
      self.assertEqual(http_probe.probe_sorted(["https://a/1"]), ["https://a/1"])

  def test_fastest_first(self):
    urls = ["https://slow/x", "https://fast/x", "https://mid/x"]
    with self._patch({urls[0]: (True, 900), urls[1]: (True, 100), urls[2]: (True, 500)}):
      self.assertEqual(http_probe.probe_sorted(urls), [urls[1], urls[2], urls[0]])

  def test_dead_sources_go_last_in_original_order(self):
    urls = ["https://dead1/x", "https://ok/x", "https://dead2/x"]
    with self._patch({urls[0]: (False, 0), urls[1]: (True, 800), urls[2]: (False, 0)}):
      self.assertEqual(http_probe.probe_sorted(urls), [urls[1], urls[0], urls[2]])

  def test_all_dead_keeps_original_order(self):
    urls = ["https://a/x", "https://b/x"]
    with self._patch({urls[0]: (False, 0), urls[1]: (False, 0)}):
      self.assertEqual(http_probe.probe_sorted(urls), urls)

  def test_official_wins_ties(self):
    # equal medians keep the candidate order: direct stays before its mirror
    urls = ["https://direct/x", "https://mirror/x"]
    with self._patch({urls[0]: (True, 300), urls[1]: (True, 300)}):
      self.assertEqual(http_probe.probe_sorted(urls), urls)

  def test_cache_by_host_survives_across_urls(self):
    # two artifacts on the same host: one measurement serves both, and the
    # second download (a fresh probe_sorted call) finds the host still cached
    calls = []
    def fake_probe_once(url, timeout_s=0):
      calls.append(url)
      return True, 200, ""
    with mock.patch.object(http_probe, "probe_once", fake_probe_once):
      http_probe.probe_sorted(["https://hf.example/a.pkl", "https://direct.example/a.pkl"], samples=1)
      http_probe.probe_sorted(["https://hf.example/b.pkl", "https://direct.example/b.pkl"], samples=1)
    self.assertEqual(sorted(calls), ["https://direct.example/a.pkl", "https://hf.example/a.pkl"])

  def test_cache_key_list_groups_sharing_hosts(self):
    # cache_keys: one measurement per distinct key, every index inherits it
    calls = []
    def fake_probe_once(url, timeout_s=0):
      calls.append(url)
      return True, 200, ""
    with mock.patch.object(http_probe, "probe_once", fake_probe_once):
      out = http_probe.probe_sorted(["https://hf.example/a.pkl", "https://direct.example/a.pkl"],
                                    cache_keys=["hf", "direct"], samples=1)
      self.assertEqual(out[0], "https://hf.example/a.pkl")
      http_probe.clear_cache()
      http_probe.probe_sorted(["https://hf.example/other.pkl", "https://hf.example/third.pkl"],
                              cache_keys=["hf", "hf"], samples=1)
    self.assertEqual(len(calls), 3)  # one per distinct key, not per URL

  def test_expired_cache_probes_again(self):
    calls = []
    def fake_probe_once(url, timeout_s=0):
      calls.append(url)
      return True, 200, ""
    with mock.patch.object(http_probe, "probe_once", fake_probe_once):
      http_probe.probe_sorted(["https://hf.example/a.pkl", "https://direct.example/a.pkl"], samples=1)
      # age one entry past the TTL; only that host is measured again
      stamp, ok, ms = http_probe._cache["https://hf.example"]
      http_probe._cache["https://hf.example"] = (stamp - http_probe.CACHE_TTL_S - 1, ok, ms)
      http_probe.probe_sorted(["https://hf.example/b.pkl", "https://direct.example/b.pkl"], samples=1)
    self.assertEqual(sorted(calls), ["https://direct.example/a.pkl", "https://hf.example/a.pkl", "https://hf.example/b.pkl"])

  def test_only_the_first_few_sources_are_measured(self):
    # the catalog has ~19 candidates; measuring them all would cost more
    # than the fetch it optimizes. The rest stay in their original order as
    # the fallback tier.
    calls = []
    def fake_probe_once(url, timeout_s=0):
      calls.append(url)
      return True, 100, ""
    urls = [f"https://s{i}.example/x" for i in range(10)]
    with mock.patch.object(http_probe, "probe_once", fake_probe_once):
      out = http_probe.probe_sorted(urls, samples=1, max_probe=3)
    self.assertEqual(len(calls), 3)
    self.assertEqual(out[:3], urls[:3], "the measured ones come first")
    self.assertEqual(out[3:], urls[3:], "the unmeasured keep their original order")

  def test_an_unmeasured_source_is_not_claimed_to_be_fast(self):
    # a source nobody asked has no claim to be fast: it lands behind the
    # measured ones even if it would have answered first
    calls = []
    def fake_probe_once(url, timeout_s=0):
      calls.append(url)
      return True, 900, ""
    urls = ["https://fast.example/x", "https://slow.example/x"]
    with mock.patch.object(http_probe, "probe_once", fake_probe_once):
      out = http_probe.probe_sorted(urls, samples=1, max_probe=1)
    self.assertEqual(out, ["https://fast.example/x", "https://slow.example/x"])

  def test_a_failed_sample_ends_the_measurement(self):
    # a source that did not answer within its timeout is not going to answer
    # on the second try: waiting for it doubles the cost of every dead source
    urls = ["https://flaky/x", "https://steady/x"]
    state = {urls[0]: [(False, 0, "timeout"), (True, 2000, "")],
             urls[1]: [(True, 3000, ""), (True, 3000, "")]}
    calls = []
    def fake_probe_once(url, timeout_s=0):
      calls.append(url)
      return state[url].pop(0)
    with mock.patch.object(http_probe, "probe_once", fake_probe_once):
      self.assertEqual(http_probe.probe_sorted(urls), [urls[1], urls[0]])
    self.assertEqual(calls.count(urls[0]), 1, "a failed source is measured once, not twice")


if __name__ == "__main__":
  unittest.main()
