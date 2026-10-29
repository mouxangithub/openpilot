"""
Copyright (c) 2026-, mouxan.

Latency probe for the model manager's HTTP sources.

The model catalogs live on raw.githubusercontent.com (direct, jsDelivr CDN,
gh-proxy style prefixes) and the artifacts on huggingface.co (direct,
hf-mirror.com). Which of those answers fastest is a property of the network
the device sits on, so it is measured, not configured - the same philosophy
as system/updated/git_proxy, but over plain HTTP instead of git.

The probe is a Range GET of the first few kilobytes, not a HEAD: mirrors have
been seen answering HEAD with a redirect (or ignoring Range and streaming the
whole body), and a real GET exercises the same path the download will use.
The response body is dropped after the first chunk, so even a source that
ignores the Range header only costs a few kilobytes.

Every source is sampled more than once and judged on its median of the
successful samples, because a single sample on a flaky link misreports a
dead source as healthy - and a single timeout misreports a healthy source
as dead. Results are cached per key (usually the host) for an hour: probing
is worth a few seconds before a multi-hundred-megabyte download, not before
every artifact in a bundle.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

import requests

# Ask for the first few KB only; dropped after the first chunk either way.
PROBE_RANGE = "bytes=0-4095"

# A source that has not answered in this long is a dead source.
PROBE_TIMEOUT_S = 6

# Samples per source. The median of the successful ones decides the order.
PROBE_SAMPLES = 2

# The whole probe runs under this budget. The candidates are probed
# concurrently, so this is the wall-clock cost of the slowest one, not the
# sum - it only bites when a source ignores its own timeout.
PROBE_BUDGET_S = 14

# How many sources are probed at once.
MAX_PROBE_WORKERS = 8

# How many distinct sources are measured at most. The catalog has ~19
# candidates (the official host, the jsDelivr edges, a dozen community
# proxies) and measuring every one of them would cost more than the fetch
# it is meant to optimize: a JSON file is small, and any source that
# answers serves it equally well. Only the first few - the ones worth
# trusting - are measured; the rest stay in their original order as the
# fallback tier, tried only when the measured ones fail.
DEFAULT_MAX_PROBE = 6

# How long a measured latency stays trusted, per cache key.
CACHE_TTL_S = 3600

_NO_COMPRESSION = {"Accept-Encoding": "identity"}

# cache key -> (monotonic stamp, ok, median_ms)
_cache: dict[str, tuple[float, bool, int]] = {}
_lock = threading.Lock()


def probe_once(url: str, timeout_s: float = PROBE_TIMEOUT_S) -> tuple[bool, int, str]:
  """Measure one source with a partial GET. Returns (ok, elapsed_ms, error).

  The probe is read-only: at most a few KB leave the server before the
  connection is closed. A captive portal answering 200 with an empty body
  does not count as up - real sources always serve bytes.
  """
  start = time.monotonic()
  try:
    with requests.get(url, headers={**_NO_COMPRESSION, "Range": PROBE_RANGE},
                      stream=True, timeout=timeout_s, allow_redirects=True) as response:
      if response.status_code >= 400:
        return False, _elapsed_ms(start), f"HTTP {response.status_code}"
      for chunk in response.iter_content(chunk_size=4096):
        if chunk:
          return True, _elapsed_ms(start), ""
      return False, _elapsed_ms(start), "empty body"
  except requests.RequestException as e:
    return False, _elapsed_ms(start), str(e)[:160]
  except Exception as e:  # a probe must never take the caller down
    return False, _elapsed_ms(start), str(e)[:160]


def _elapsed_ms(start: float) -> int:
  return int((time.monotonic() - start) * 1000)


def _median_of(url: str, samples: int, deadline: float) -> tuple[bool, int]:
  """Sample one source; judge on the median of the answers that came back.

  Two successes end the sampling early - a source that answered twice does
  not need more proof. One failure ends it as well: a model source that
  did not answer within its timeout is not going to answer on the second
  try, and waiting for that second try doubles the cost of every dead
  source in the list. The retry that matters is the download's - it moves
  on to the next candidate instead.

  The deadline is a hard stop: a source that has not answered by then is
  recorded as unmeasured rather than being sampled past the budget.
  """
  good: list[int] = []
  for _ in range(samples):
    if time.monotonic() >= deadline:
      break
    ok, ms, _ = probe_once(url)
    if not ok:
      break
    good.append(ms)
    if len(good) >= 2:
      break
  if not good:
    return False, 0
  ordered = sorted(good)
  return True, ordered[len(ordered) // 2]


def _cache_key(url: str, keys: list[str] | None, index: int) -> str:
  if keys is not None:
    return keys[index]
  return f"{urlsplit(url).scheme}://{urlsplit(url).netloc}"


def probe_sorted(urls: list[str], samples: int = PROBE_SAMPLES,
                 budget_s: float = PROBE_BUDGET_S,
                 cache_keys: list[str] | None = None,
                 cache_ttl_s: float = CACHE_TTL_S,
                 max_probe: int | None = DEFAULT_MAX_PROBE) -> list[str]:
  """Return `urls` reordered fastest-first, unhealthy ones last.

  One URL per cache key is measured; the others sharing the key inherit its
  result (the latency is a property of the host, and a bundle downloads
  several artifacts from the same mirror). A key measured inside the TTL is
  not measured again, so a five-artifact bundle probes each mirror once.

  At most `max_probe` distinct sources are measured. The unmeasured ones
  keep their original relative order behind the measured ones: they are the
  fallback tier, and a source nobody asked has no claim to be fast.

  When nothing answers, the original order is returned unchanged - the
  caller's candidate order is already a sane fallback, and the first fetch
  attempt learns the truth better than a failed probe does.
  """
  if len(urls) <= 1:
    return list(urls)
  if cache_keys is not None and len(cache_keys) != len(urls):
    cache_keys = None

  now = time.monotonic()
  measured: dict[str, tuple[bool, int]] = {}
  to_probe: list[int] = []
  for index, url in enumerate(urls):
    key = _cache_key(url, cache_keys, index)
    with _lock:
      cached = _cache.get(key)
    if cached and now - cached[0] < cache_ttl_s:
      measured[index] = (cached[1], cached[2])
    else:
      to_probe.append(index)

  if to_probe:
    deadline = time.monotonic() + budget_s
    # first URL of each distinct key does the measuring; the rest inherit
    first_by_key: dict[str, int] = {}
    for index in to_probe:
      first_by_key.setdefault(_cache_key(urls[index], cache_keys, index), index)

    if max_probe is not None:
      # the trusted tier comes first in the candidate list, so the cap keeps
      # the ones worth measuring and leaves the community proxies as backup.
      # The cap counts distinct sources: several URLs sharing one host are
      # measured by that host's single probe.
      limited: list[int] = []
      counted_keys: set[str] = set()
      for index in to_probe:
        key = _cache_key(urls[index], cache_keys, index)
        if key in counted_keys:
          limited.append(index)  # inherits the host's measurement
          continue
        if len(counted_keys) >= max_probe:
          break
        counted_keys.add(key)
        limited.append(index)
      to_probe = limited

    def run(index: int) -> None:
      key = _cache_key(urls[index], cache_keys, index)
      ok, median = _median_of(urls[index], samples, deadline)
      with _lock:
        _cache[key] = (time.monotonic(), ok, median)
      for other in to_probe:
        if _cache_key(urls[other], cache_keys, other) == key:
          measured[other] = (ok, median)

    # only the sources that survived the cap are measured
    targets = [index for index in to_probe
               if first_by_key.get(_cache_key(urls[index], cache_keys, index)) == index]
    with ThreadPoolExecutor(max_workers=min(len(targets), MAX_PROBE_WORKERS)) as pool:
      list(pool.map(run, targets))

  def sort_key(item: tuple[int, str]) -> tuple[int, int]:
    index, _ = item
    ok, median = measured.get(index, (False, 0))
    return (0 if ok else 1, median if ok else 0)

  return [url for _, url in sorted(enumerate(urls), key=sort_key)]


def clear_cache() -> None:
  """Drop every measured latency (tests, and a manual re-probe)."""
  with _lock:
    _cache.clear()
