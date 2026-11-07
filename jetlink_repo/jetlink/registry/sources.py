"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of jetlink and is licensed under the MIT license.
See the LICENSE file in the root directory for more details.

Which network source a file is fetched from, and which one answers fastest.

The comma reaches three hosts for a large model: raw.githubusercontent.com for
the git-lfs pointer and the catalogs, github.com for a commit's patch, and
huggingface.co for the model repo's tree and the LFS batch API. All three are
unreachable or slow from networks in China, which is why the registry asks a
CDN and a handful of read-through proxies as well.

Which of them answers fastest is a property of the network the device sits on,
so it is measured rather than configured: a probe reads the first few
kilobytes of the real URL and sorts the candidates by how long that took. A
source that did not answer is dropped and the next one is tried.

This module is stdlib only, like the rest of the registry: the comma runs it
and the server's Swift registry is held to the same behaviour by the
conformance fixture (docs/conformance.md).

Two URL shapes, and mixing them fails:
- path form (``https://cdn.jsdelivr.net/gh/<owner>/<repo>@<branch>/<path>``):
  the jsDelivr CDN family only serves this shape;
- prefix form (``<prefix>https://raw.githubusercontent.com/...``): the
  read-through proxies only serve this shape.
"""
from __future__ import annotations

import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# Read-through proxies: the prefix is prepended to the full original URL.
# These are third-party services that come and go, which is why the list is
# measured at runtime instead of trusted.
PROXY_PREFIXES = (
  'https://gh-proxy.com/',
  'https://cdn.gh-proxy.org/',
  'https://ghfast.top/',
  'https://ghproxy.net/',
  'https://gh-proxy.net/',
  'https://ghproxy.cc/',
  'https://ghproxy.felicity.land/',
  'https://github.chenc.dev/',
  'https://ghm.078465.xyz/',
  'https://xsadwsd.kdns.fr/',
  'https://git.yylx.win/',
  'https://githubproxy.cc/',
  'https://cors.isteed.cc/',
  'https://mirror.houlang.cloud/',
)

# The jsDelivr CDN family, all serving the same path form. They are separate
# anycast edges of one CDN: a network that cannot reach one of them can
# usually reach another.
JSDELIVR_HOSTS = (
  'https://cdn.jsdelivr.net',
  'https://fastly.jsdelivr.net',
  'https://testingcf.jsdelivr.net',
  'https://gcore.jsdelivr.net',
)

# HuggingFace mirrors, as replacement bases: the huggingface.co prefix is
# swapped for the base. They serve the API as well as the files.
HF_MIRROR_BASES = (
  'https://hf-mirror.com',
  'https://hf-mirror.net',
)

RAW_GITHUB_HOSTS = ('https://raw.githubusercontent.com/', 'http://raw.githubusercontent.com/')

# How much of the body a probe reads. A pointer is 134 bytes, a catalog a few
# hundred KB: the first few KB answer every question asked here.
PROBE_RANGE = 'bytes=0-4095'

# A source that has not answered in this long is a dead source.
PROBE_TIMEOUT = 6.0

# The whole probe runs under this budget.
PROBE_BUDGET = 14.0

# How many sources are probed at once.
MAX_WORKERS = 8

# How many distinct sources are measured at most. The rest keep their order
# behind the measured ones, as the fallback tier.
MAX_PROBE = 6

# How long a measured latency stays trusted, per host.
CACHE_TTL = 3600.0

_lock = threading.Lock()
# host -> (monotonic stamp, ok, median_ms)
_cache: dict[str, tuple[float, bool, int]] = {}


def raw_to_jsdelivr(url: str, host: str = JSDELIVR_HOSTS[0]) -> str | None:
  """The jsDelivr URL for a raw.githubusercontent.com URL, or None.

  Supports the current /<owner>/<repo>/refs/heads/<branch>/<path> form and
  the legacy /<owner>/<repo>/<branch>/<path> form.
  """
  for prefix in RAW_GITHUB_HOSTS:
    if not url.startswith(prefix):
      continue
    parts = url[len(prefix):].split('/', 3)
    if len(parts) != 4 or not all(parts[:2]) or not parts[3]:
      return None
    owner, repo, ref, path = parts
    if ref == 'refs':
      if not path.startswith('heads/'):
        return None
      branch_rest = path[len('heads/'):]
      slash = branch_rest.find('/')
      if slash <= 0:
        return None
      return f'{host}/gh/{owner}/{repo}@{branch_rest[:slash]}/{branch_rest[slash + 1:]}'
    return f'{host}/gh/{owner}/{repo}@{ref}/{path}'
  return None


def raw_to_hf_mirror(url: str, base: str) -> str | None:
  """The HuggingFace mirror URL for a huggingface.co URL, or None."""
  if not url.startswith('https://huggingface.co/'):
    return None
  return base + '/' + url[len('https://huggingface.co/'):]


def proxy_candidates(url: str, prefixes=PROXY_PREFIXES) -> list[str]:
  """The read-through proxies' URLs for one URL."""
  return [prefix + url for prefix in prefixes]


def jsdelivr_candidates(url: str, hosts=JSDELIVR_HOSTS) -> list[str]:
  """The CDN family's URLs for one URL."""
  return [mapped for host in hosts if (mapped := raw_to_jsdelivr(url, host))]


def hf_mirror_candidates(url: str, bases=HF_MIRROR_BASES) -> list[str]:
  """The HuggingFace mirrors' URLs for one URL."""
  return [mapped for base in bases if (mapped := raw_to_hf_mirror(url, base))]


def probe_once(url: str, timeout: float = PROBE_TIMEOUT, opener=None) -> tuple[bool, int, str]:
  """Measure one source with a partial GET. Returns (ok, elapsed_ms, error).

  The probe is read-only: at most a few KB leave the server before the
  connection is closed. A captive portal answering 200 with an empty body
  does not count as up - real sources always serve bytes.
  """
  opener = opener or urllib.request.urlopen
  start = time.monotonic()
  try:
    request = urllib.request.Request(url, headers={'Range': PROBE_RANGE})
    with opener(request, timeout=timeout) as response:
      if getattr(response, 'status', 200) >= 400:
        return False, _elapsed(start), f'HTTP {response.status}'
      for chunk in iter(lambda: response.read(4096), b''):
        if chunk:
          return True, _elapsed(start), ''
      return False, _elapsed(start), 'empty body'
  except urllib.error.HTTPError as e:
    return False, _elapsed(start), f'HTTP {e.code}'
  except Exception as e:
    return False, _elapsed(start), str(e)[:120]


def _elapsed(start: float) -> int:
  return int((time.monotonic() - start) * 1000)


def _measure(url: str, timeout: float = PROBE_TIMEOUT, opener=None) -> tuple[bool, int]:
  """Measure one source once. One failure ends it: a source that did not
  answer within its timeout is not going to answer on the second try, and
  waiting for that doubles the cost of every dead source in the list. The
  retry that matters is the caller's - it moves to the next candidate."""
  ok, ms, _ = probe_once(url, timeout, opener)
  return ok, ms


def _host(url: str) -> str:
  parsed = urllib.parse.urlsplit(url)
  return f'{parsed.scheme}://{parsed.netloc}'


def probe_sorted(urls: list[str], timeout: float = PROBE_TIMEOUT, budget: float = PROBE_BUDGET,
                 max_probe: int = MAX_PROBE, cache_ttl: float = CACHE_TTL, opener=None,
                 keep_first: bool = False) -> list[str]:
  """Return `urls` reordered fastest-first, the ones that did not answer last.

  At most `max_probe` distinct hosts are measured; the rest keep their
  original relative order behind the measured ones, as the fallback tier. A
  host measured inside the TTL is not measured again.

  `keep_first` leaves the first candidate where it is and sorts only the
  rest. The registry's own contract needs that: a 404 from the official
  source means the file is not there, which the catalog's version probe
  relies on, so the official source must be asked first whatever the
  measurement says.

  The probe uses its own opener, not the caller's: the caller's opener is
  often a test fixture that records every URL it is asked for, and a
  measurement is not a request the caller made.

  When nothing answers the original order is returned unchanged: it is
  already a sane fallback, and the first real fetch learns the truth better
  than a failed probe does.
  """
  if len(urls) <= 1:
    return list(urls)

  now = time.monotonic()
  measured: dict[int, tuple[bool, int]] = {}
  to_probe: list[int] = []
  for index, url in enumerate(urls):
    with _lock:
      cached = _cache.get(_host(url))
    if cached and now - cached[0] < cache_ttl:
      measured[index] = (cached[1], cached[2])
    else:
      to_probe.append(index)

  if to_probe:
    # one measurement per host; the URLs sharing it inherit the result
    first_by_host: dict[str, int] = {}
    for index in to_probe:
      first_by_host.setdefault(_host(urls[index]), index)

    limited: list[int] = []
    counted: set[str] = set()
    for index in to_probe:
      host = _host(urls[index])
      if host in counted:
        limited.append(index)
        continue
      if len(counted) >= max_probe:
        break
      counted.add(host)
      limited.append(index)
    to_probe = limited

    def run(index: int) -> None:
      host = _host(urls[index])
      ok, ms = _measure(urls[index], timeout)
      with _lock:
        _cache[host] = (time.monotonic(), ok, ms)
      for other in to_probe:
        if _host(urls[other]) == host:
          measured[other] = (ok, ms)

    targets = [i for i in to_probe if first_by_host.get(_host(urls[i])) == i]
    with ThreadPoolExecutor(max_workers=min(len(targets), MAX_WORKERS)) as pool:
      list(pool.map(run, targets))

  def sort_key(item: tuple[int, str]) -> tuple[int, int]:
    index, _ = item
    ok, ms = measured.get(index, (False, 0))
    return (0 if ok else 1, ms if ok else 0)

  ordered = [url for _, url in sorted(enumerate(urls), key=sort_key)]
  if keep_first and urls:
    first = urls[0]
    ordered = [first, *[u for u in ordered if u != first]]
  return ordered


def clear_cache() -> None:
  """Drop every measured latency (tests, and a manual re-probe)."""
  with _lock:
    _cache.clear()
