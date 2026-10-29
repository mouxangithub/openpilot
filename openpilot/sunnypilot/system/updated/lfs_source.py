"""
Copyright (c) 2026-, mouxan.

LFS endpoint auto-selection.

Git metadata (commits, trees, the LFS pointers themselves) comes from github
and is accelerated by git_proxy.py. The LFS *objects* those pointers name are
a separate link: the repo's .lfsconfig points lfs.url at huggingface.co, and
git-lfs resolves every object through that endpoint's batch API before
downloading it from a signed, US CloudFront CDN url. From networks in China
that link is slow or down, and none of the github proxies touch it.

huggingface has a reachable mirror that speaks the whole LFS protocol: the
batch API rewrites the signed CDN url onto the mirror's own /_cdn/ path, so
both legs of the transfer go through it. Which one answers fastest is a
property of the network the device sits on, so it is measured rather than
configured: a dummy-object batch request costs a few hundred bytes and every
speaking endpoint answers it (with a structured 404 for the unknown oid),
which is enough to rank reachability without downloading anything.

The fastest endpoint is written to the repo's *local* git config
(lfs.url/lfs.pushurl), which overrides .lfsconfig without editing the tracked
file - so a fetch on a healthy direct link is byte-identical to today's
behaviour, and a mirror is only selected when it measured better. The local
override is a plain `git config`, so it never enters a commit or a merge.
"""
from __future__ import annotations

import concurrent.futures
import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from openpilot.common.swaglog import cloudlog

# Hosts that serve the same LFS repository and speak the batch protocol.
# The official host stays first so it wins a latency tie: a working direct
# link must not be displaced by a third-party mirror that merely ties it.
#
# hf-mirror.com is deliberately absent: its batch API 308-redirects back to
# huggingface, so git-lfs cannot use it. hf-mirror.net answers the batch API
# itself and rewrites the signed CDN url onto its own /_cdn/ path.
HF_HOST = "huggingface.co"
MIRROR_HOSTS = ("hf-mirror.net",)

# A zero sha256 names no real object; every speaking endpoint replies with a
# structured 404 instead of making us name - or download - a real one.
_PROBE_OID = "0" * 64
_PROBE_BODY = json.dumps({
  "operation": "download",
  "transfers": ["basic"],
  "objects": [{"oid": _PROBE_OID, "size": 1}],
}).encode("utf-8")
_PROBE_HEADERS = {
  "Content-Type": "application/vnd.git-lfs+json",
  "Accept": "application/vnd.git-lfs+json",
  "User-Agent": "git-lfs/3.0 (openpilot-updater)",
}

# A probe that has not answered in this long is a dead endpoint.
PROBE_TIMEOUT_S = 8

# One success is proof enough for a small JSON API. Probing twice on a flaky
# link buys little against a budget that runs on every update.
PROBE_SAMPLES = 1
MAX_PROBE_WORKERS = 4


@dataclass
class EndpointResult:
  """The outcome of measuring one LFS endpoint base url."""
  base_url: str
  ok: bool
  median_ms: int
  samples: list[int]
  error: str = ""


def lfs_endpoint_candidates(configured_url: str) -> list[str]:
  """The configured endpoint, then each mirror that serves the same repo.

  The lfs url is `https://huggingface.co/<owner>/<repo>.git/info/lfs`.
  Mirrors are reached by swapping only the host, so any future move of the
  repository follows the configured url instead of being pinned here. A url
  that is not huggingface is returned alone (a self-hosted LFS server has no
  known mirror).
  """
  url = (configured_url or "").strip()
  if not url:
    return []
  candidates = [url]
  if f"://{HF_HOST}/" in url:
    for host in MIRROR_HOSTS:
      mirrored = url.replace(f"://{HF_HOST}/", f"://{host}/", 1)
      if mirrored not in candidates:
        candidates.append(mirrored)
  return candidates


def _speaks_lfs(body: bytes) -> bool:
  """A speaking endpoint answers 200 with our dummy oid echoed back.

  Every real LFS server reports the unknown oid as a structured 404 object.
  A captive portal or an HTML error page answers 200 without that shape and
  must not rank as a healthy endpoint.
  """
  try:
    data = json.loads(body.decode("utf-8", "replace"))
  except (ValueError, UnicodeDecodeError):
    return False
  obj = (data.get("objects") or [{}])[0]
  return obj.get("oid") == _PROBE_OID


def probe_endpoint(base_url: str, timeout_s: float = PROBE_TIMEOUT_S,
                   samples: int = PROBE_SAMPLES) -> EndpointResult:
  """Measure batch-API round trips. A speaking endpoint answers HTTP 200 with
  a JSON body whose object carries a structured 404 for the unknown oid; that
  is a healthy LFS server and is all the probe needs to know."""
  import time
  batch_url = base_url.rstrip("/") + "/objects/batch"
  latencies: list[int] = []
  error = ""
  for _ in range(samples):
    request = urllib.request.Request(batch_url, data=_PROBE_BODY, headers=_PROBE_HEADERS, method="POST")
    t0 = time.monotonic()
    try:
      with urllib.request.urlopen(request, timeout=timeout_s) as response:
        body = response.read(4096)
        status = response.status
      elapsed = int((time.monotonic() - t0) * 1000)
      if status == 200 and _speaks_lfs(body):
        latencies.append(elapsed)
      else:
        error = "not an lfs endpoint"
    except urllib.error.HTTPError as e:
      error = f"http {e.code}"
    except Exception as e:
      error = type(e).__name__
  if not latencies:
    return EndpointResult(base_url, False, 0, [], error)
  return EndpointResult(base_url, True, sorted(latencies)[len(latencies) // 2], latencies)


def measure_and_rank(configured_url: str) -> list[EndpointResult]:
  """Probe every candidate concurrently, healthy first by median latency.

  The configured endpoint wins a tie (stable sort, it is listed first). When
  nothing answers an empty list is returned and the caller leaves whatever
  endpoint was already configured untouched - the real fetch learns the truth
  better than a failed probe does.
  """
  candidates = lfs_endpoint_candidates(configured_url)
  if len(candidates) <= 1:
    return ([probe_endpoint(candidates[0])] if candidates else [])

  results: list[EndpointResult] = []
  with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(candidates), MAX_PROBE_WORKERS)) as pool:
    results.extend(pool.map(probe_endpoint, candidates))

  healthy = [r for r in results if r.ok]
  healthy.sort(key=lambda r: r.median_ms)
  return healthy


def select_endpoint(configured_url: str) -> str | None:
  """The fastest healthy endpoint base url, or None when nothing answered.

  The configured endpoint is returned unchanged when it wins, so callers can
  compare against the current lfs.url and skip a redundant git config write.
  """
  ranked = measure_and_rank(configured_url)
  if not ranked:
    return None
  return ranked[0].base_url
