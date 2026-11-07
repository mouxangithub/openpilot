"""
Copyright (c) 2026-, mouxan.

LFS endpoint auto-selection tests. The network is mocked (urllib), so these
run on both a PC and the device's unittest runner.
"""
import json
import sys
import types
import unittest
from unittest import mock

try:
  import openpilot.common.swaglog  # noqa: F401
except Exception:
  stub = types.ModuleType("openpilot.common.swaglog")
  stub.cloudlog = types.SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None,
                                        exception=lambda *a, **k: None)
  sys.modules["openpilot.common.swaglog"] = stub

from openpilot.sunnypilot.system.updated import lfs_source as ls

DIRECT = "https://huggingface.co/sunnypilot/sunnypilot-lfs.git/info/lfs"
MIRROR = "https://hf-mirror.net/sunnypilot/sunnypilot-lfs.git/info/lfs"


def _batch_body(oid=ls._PROBE_OID, *, with_error=True):
  obj = {"oid": oid, "size": 1}
  if with_error:
    obj["error"] = {"code": 404, "message": "Object does not exist"}
  return json.dumps({"transfer": "basic", "objects": [obj]}).encode("utf-8")


class _FakeResponse:
  def __init__(self, body, status=200):
    self._body = body
    self.status = status

  def __enter__(self):
    return self

  def __exit__(self, *args):
    return False

  def read(self, n=-1):
    return self._body[:n] if n and n > 0 else self._body


def _urlopen_stub(latencies, *, body=None, fail=()):
  """urlopen(request, timeout=...) stand-in keyed by host.

  latencies maps host -> ms (records, sleeps nothing); hosts in fail raise.
  """
  calls = []

  def fake_urlopen(request, timeout=None):
    host = request.full_url.split("/")[2]
    calls.append(host)
    if host in fail:
      raise OSError(f"{host} unreachable")
    return _FakeResponse(body if body is not None else _batch_body())

  return fake_urlopen, calls


class TestCandidates(unittest.TestCase):
  def test_direct_first_then_mirror(self):
    self.assertEqual(ls.lfs_endpoint_candidates(DIRECT), [DIRECT, MIRROR])

  def test_non_hf_url_has_no_mirror(self):
    url = "https://gitea.example.com/repo.git/info/lfs"
    self.assertEqual(ls.lfs_endpoint_candidates(url), [url])

  def test_empty(self):
    self.assertEqual(ls.lfs_endpoint_candidates(""), [])
    self.assertEqual(ls.lfs_endpoint_candidates("   "), [])

  def test_trailing_slash_normalised_in_batch_url(self):
    # a trailing slash must not become a double slash before objects/batch
    candidates = ls.lfs_endpoint_candidates(DIRECT)
    self.assertTrue(all(not c.endswith("/") for c in candidates))


class TestSpeaksLfs(unittest.TestCase):
  def test_structured_404_is_healthy(self):
    self.assertTrue(ls._speaks_lfs(_batch_body()))

  def test_wrong_oid_is_not(self):
    self.assertFalse(ls._speaks_lfs(_batch_body(oid="a" * 64)))

  def test_html_page_is_not(self):
    self.assertFalse(ls._speaks_lfs(b"<html>captive portal</html>"))

  def test_empty_is_not(self):
    self.assertFalse(ls._speaks_lfs(b""))


class TestProbeAndRank(unittest.TestCase):
  def test_probe_endpoint_healthy(self):
    with mock.patch.object(ls.urllib.request, "urlopen",
                           lambda request, timeout=None: _FakeResponse(_batch_body())):
      result = ls.probe_endpoint(DIRECT, samples=1)
    self.assertTrue(result.ok)
    self.assertGreaterEqual(result.median_ms, 0)

  def test_probe_endpoint_dead(self):
    def boom(request, timeout=None):
      raise OSError("unreachable")
    with mock.patch.object(ls.urllib.request, "urlopen", boom):
      result = ls.probe_endpoint(DIRECT, samples=1)
    self.assertFalse(result.ok)
    self.assertEqual(result.median_ms, 0)

  def test_captive_portal_200_ranks_dead(self):
    # a 200 that is not the LFS batch shape must not count as healthy
    with mock.patch.object(ls.urllib.request, "urlopen",
                           lambda request, timeout=None: _FakeResponse(b"<html>login</html>")):
      result = ls.probe_endpoint(DIRECT, samples=1)
    self.assertFalse(result.ok)

  def test_mirror_faster_wins_but_direct_ties(self):
    # both answer; ordering is by measured latency. Patch probe_endpoint to
    # return deterministic timings regardless of the real network.
    timings = {
      "huggingface.co": 700,
      "hf-mirror.net": 200,
    }

    def fake_probe(base_url, timeout_s=None, samples=1):
      host = base_url.split("/")[2]
      return ls.EndpointResult(base_url, True, timings[host], [timings[host]])

    with mock.patch.object(ls, "probe_endpoint", fake_probe):
      ranked = ls.measure_and_rank(DIRECT)
    self.assertEqual([r.base_url for r in ranked], [MIRROR, DIRECT])

  def test_direct_wins_a_tie(self):
    def fake_probe(base_url, timeout_s=None, samples=1):
      return ls.EndpointResult(base_url, True, 400, [400])
    with mock.patch.object(ls, "probe_endpoint", fake_probe):
      ranked = ls.measure_and_rank(DIRECT)
    # stable sort keeps the configured (first) endpoint ahead on equal ms
    self.assertEqual(ranked[0].base_url, DIRECT)

  def test_dead_endpoint_dropped(self):
    def fake_probe(base_url, timeout_s=None, samples=1):
      host = base_url.split("/")[2]
      if host == "huggingface.co":
        return ls.EndpointResult(base_url, False, 0, [], "timeout")
      return ls.EndpointResult(base_url, True, 300, [300])
    with mock.patch.object(ls, "probe_endpoint", fake_probe):
      ranked = ls.measure_and_rank(DIRECT)
    self.assertEqual([r.base_url for r in ranked], [MIRROR])

  def test_nothing_answers_selects_none(self):
    def fake_probe(base_url, timeout_s=None, samples=1):
      return ls.EndpointResult(base_url, False, 0, [], "timeout")
    with mock.patch.object(ls, "probe_endpoint", fake_probe):
      self.assertIsNone(ls.select_endpoint(DIRECT))

  def test_select_returns_direct_when_it_wins(self):
    def fake_probe(base_url, timeout_s=None, samples=1):
      host = base_url.split("/")[2]
      ms = 200 if host == "huggingface.co" else 900
      return ls.EndpointResult(base_url, True, ms, [ms])
    with mock.patch.object(ls, "probe_endpoint", fake_probe):
      self.assertEqual(ls.select_endpoint(DIRECT), DIRECT)


if __name__ == "__main__":
  unittest.main()
