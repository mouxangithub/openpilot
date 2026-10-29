"""
Copyright (c) 2026-, mouxan.

Model download mirror support.

The model catalogs live on raw.githubusercontent.com and every model file the
catalogs point at is served by huggingface.co. Both hosts are routinely
unreachable from networks in China, which leaves the model manager unable to
list or download anything at all. Two user-configurable Params keys redirect
those fetches:

- ``ModelManager_MirrorUrl``: the base URL that replaces ``https://huggingface.co``
  in artifact download URIs. Empty (default) is automatic: the known mirrors
  and the direct URL are all candidates and a latency probe picks the order
  (see http_probe); ``off`` pins direct download only; any other value is
  used as the replacement base, with the direct URL kept as fallback.
- ``ModelManager_GithubProxy``: how catalog URLs are fetched. Empty means
  automatic: the direct URL and every known CDN/proxy are candidates, ordered
  by measured latency. ``direct`` pins the direct URL alone. Any other value
  is normalized into a prefix and tried first (``prefix + full URL``).

Two URL shapes are in play, and mixing them fails:
- path form (``https://cdn.jsdelivr.net/gh/<owner>/<repo>@<branch>/<path>``):
  the jsDelivr CDN family only serves this shape;
- prefix form (``<prefix>https://raw.githubusercontent.com/...``): the
  read-through proxies only serve this shape.

Mirrors cannot corrupt anything: model files carry per-chunk sha256 hashes
that are verified after download, and catalogs are verified against the
ed25519 trust root (signing.py) - a mirror that alters either is rejected.
"""
import logging

logging.getLogger(__name__).setLevel(logging.INFO)
cloudlog = logging.getLogger(__name__)

HF_MIRROR_PARAM = "ModelManager_MirrorUrl"
GITHUB_PROXY_PARAM = "ModelManager_GithubProxy"
DEFAULT_HF_MIRROR = "https://hf-mirror.com"
DIRECT_VALUE = "off"  # ModelManager_MirrorUrl value that disables rewriting
PROXY_DIRECT_VALUE = "direct"  # ModelManager_GithubProxy value that disables the CDN fallback
JSDELIVR_HOST = "https://cdn.jsdelivr.net"

HF_HOSTS = ("https://huggingface.co/", "http://huggingface.co/", "https://www.huggingface.co/")
RAW_GITHUB_HOSTS = ("https://raw.githubusercontent.com/", "http://raw.githubusercontent.com/")

# The jsDelivr CDN family, all serving the same path form. They are separate
# anycast edges of one CDN: a network that cannot reach one of them can
# usually reach another, and they are cheap to measure.
JSDELIVR_HOSTS = (
  "https://cdn.jsdelivr.net",
  "https://fastly.jsdelivr.net",
  "https://testingcf.jsdelivr.net",
  "https://gcore.jsdelivr.net",
)

# Read-through proxies for raw.githubusercontent.com, in prefix form: the
# prefix is prepended to the full original URL. These are third-party
# services that come and go, which is why the list is measured at runtime
# instead of trusted.
#
# All of them were measured serving the catalog over HTTP. Four of them
# (ghproxy.cc, git.yylx.win, cors.isteed.cc, mirror.houlang.cloud) do not
# speak git's smart-http, so they are useless to the OTA updater even
# though they serve raw files fine - see git_proxy.PROXY_PREFIXES.
GITHUB_PROXY_PREFIXES = (
  "https://gh-proxy.com/",
  "https://cdn.gh-proxy.org/",
  "https://ghfast.top/",
  "https://ghproxy.net/",
  "https://gh-proxy.net/",
  "https://ghproxy.cc/",
  "https://ghproxy.felicity.land/",
  "https://github.chenc.dev/",
  "https://ghm.078465.xyz/",
  "https://xsadwsd.kdns.fr/",
  "https://git.yylx.win/",
  "https://githubproxy.cc/",
  "https://cors.isteed.cc/",
  "https://mirror.houlang.cloud/",
)
# HuggingFace mirrors, in replacement-base form: the huggingface.co prefix
# is swapped for the base. A mirror only serves the file if it has the
# dataset, so a 404 on one mirror says nothing about the others.
HF_MIRROR_BASES = (
  "https://hf-mirror.com",
  "https://hf-mirror.net",
)


def normalize_base_url(value) -> str | None:
  """Returns value without a trailing slash, or None when it is not a usable http(s) base URL."""
  if not isinstance(value, str):
    return None
  value = value.strip()
  if not value or any(ch.isspace() for ch in value):
    return None
  value = value.rstrip("/")
  if not value.startswith(("http://", "https://")):
    return None
  if not value.split("://", 1)[1]:
    return None
  return value


def get_hf_mirror_base(params) -> str:
  """'' = download directly from huggingface.co; anything else replaces the huggingface.co prefix."""
  raw = _param_str(params, HF_MIRROR_PARAM)
  if not raw:
    return DEFAULT_HF_MIRROR
  if raw.lower() == DIRECT_VALUE:
    return ""
  base = normalize_base_url(raw)
  if base is None:
    cloudlog.warning(f"invalid {HF_MIRROR_PARAM} {raw!r}; using default mirror {DEFAULT_HF_MIRROR}")
    return DEFAULT_HF_MIRROR
  return base


def apply_hf_mirror(url: str, base: str) -> str:
  """Rewrites a huggingface.co URL onto the mirror base; other hosts pass through untouched."""
  if not base or not url:
    return url
  for prefix in HF_HOSTS:
    if url.startswith(prefix):
      return base + "/" + url[len(prefix):]
  return url


def hf_mirror_candidates(url: str, params) -> list[str]:
  """Ordered artifact URL candidates for one download.

  Automatic (empty param) offers every known HF mirror plus the direct URL,
  letting the caller's latency probe decide which goes first: on a China link
  hf-mirror measures faster, overseas the direct host usually does. A mirror
  that does not carry the dataset answers 404 and the next candidate is
  tried - the probes rank, the download decides.

  ``off`` pins the direct URL alone - the user said so. A custom base keeps
  the user's choice first with the direct URL as a plain fallback; no
  reordering, because someone who set a mirror wants that mirror.

  Every candidate serves byte-identical files (per-chunk sha256 downstream),
  so a fallback can never corrupt anything.
  """
  if not url:
    return []
  if not url.startswith(HF_HOSTS):
    return [url]  # non-huggingface hosts pass through untouched
  base = get_hf_mirror_base(params)
  candidates = []
  if base:
    # a custom base replaces the built-in list: it is the user's explicit pick
    bases = (base,) if base not in HF_MIRROR_BASES else HF_MIRROR_BASES
    for mirror_base in bases:
      candidates.append(apply_hf_mirror(url, mirror_base))
  candidates.append(url)
  return [c for i, c in enumerate(candidates) if c and c not in candidates[:i]]


def github_raw_to_jsdelivr(url: str, host: str = JSDELIVR_HOST) -> str | None:
  """Maps a raw.githubusercontent.com URL onto a jsDelivr CDN host, or None when not a raw URL.

  Supports the current /<owner>/<repo>/refs/heads/<branch>/<path> form and the
  legacy /<owner>/<repo>/<branch>/<path> form.

  The path shape is jsDelivr's own (``/gh/<owner>/<repo>@<branch>/<path>``) and
  is not the same as the read-through proxies' prefix shape - mixing the two
  gives a 404.
  """
  for prefix in RAW_GITHUB_HOSTS:
    if not url.startswith(prefix):
      continue
    parts = url[len(prefix):].split("/", 3)
    if len(parts) != 4 or not all(parts[:2]) or not parts[3]:
      return None
    if parts[2] == "refs":
      if not parts[3].startswith("heads/"):
        return None
      branch_rest = parts[3][len("heads/"):]
      slash = branch_rest.find("/")
      if slash <= 0:
        return None
      return f"{host}/gh/{parts[0]}/{parts[1]}@{branch_rest[:slash]}/{branch_rest[slash + 1:]}"
    return f"{host}/gh/{parts[0]}/{parts[1]}@{parts[2]}/{parts[3]}"
  return None


def get_github_proxy(params) -> str:
  """'' = automatic (every known source is a candidate); PROXY_DIRECT_VALUE = direct only; else a proxy prefix."""
  raw = _param_str(params, GITHUB_PROXY_PARAM)
  if not raw:
    return ""
  if raw.lower() == PROXY_DIRECT_VALUE:
    return PROXY_DIRECT_VALUE
  base = normalize_base_url(raw)
  if base is None:
    cloudlog.warning(f"invalid {GITHUB_PROXY_PARAM} {raw!r}; ignoring")
    return ""
  return base + "/"


def catalog_fetch_candidates(url: str, params) -> list[str]:
  """Ordered catalog URLs to try; the first one that serves a verifiable catalog wins.

  The order here is only the starting point - the caller latency-probes the
  candidates and reorders them by measurement (see http_probe). The order
  still decides the winner on a tie, so the official source comes first and
  keeps the win when everything measures the same.

  Three families, in the shape each one actually serves:
  1. the direct raw.githubusercontent.com URL;
  2. the jsDelivr CDN family, in its path form;
  3. the read-through proxies, in prefix form.

  A user-set proxy prefix replaces the built-in proxy family: it is the
  user's explicit pick and it goes first.
  """
  proxy = get_github_proxy(params)
  if proxy == PROXY_DIRECT_VALUE:
    return [url]

  candidates = []
  if proxy:
    # the user's prefix is their explicit pick and goes first
    candidates.append(proxy + url)
  candidates.append(url)

  # The CDN edges come before the community proxies: they are one service
  # with a stable path form and a track record, while the proxies are
  # third-party services that come and go. The order decides what gets
  # measured when there are more candidates than the probe budget allows,
  # so the trustworthy tier is the one that gets measured.
  for host in JSDELIVR_HOSTS:
    mapped = github_raw_to_jsdelivr(url, host)
    if mapped:
      candidates.append(mapped)

  if not proxy:
    # the built-in proxy family; a user prefix replaces it
    for prefix in GITHUB_PROXY_PREFIXES:
      candidates.append(prefix + url)

  return [c for i, c in enumerate(candidates) if c and c not in candidates[:i]]


def describe_hf_mirror(params) -> str:
  """The effective model-file source, for UI display."""
  base = get_hf_mirror_base(params)
  return base if base else "huggingface.co"


def describe_github_proxy(params) -> str:
  """The effective catalog source, for UI display."""
  proxy = get_github_proxy(params)
  if proxy == PROXY_DIRECT_VALUE:
    return "raw.githubusercontent.com"
  if proxy:
    return proxy
  return "auto"


def _param_str(params, key: str) -> str:
  try:
    raw = params.get(key)
  except Exception:
    return ""
  if isinstance(raw, bytes):
    raw = raw.decode("utf-8", "replace")
  return (raw or "").strip()
