"""
Copyright (c) 2026-, mouxan.

Model download mirror support.

The model catalogs live on raw.githubusercontent.com and every model file the
catalogs point at is served by huggingface.co. Both hosts are routinely
unreachable from networks in China, which leaves the model manager unable to
list or download anything at all. Two user-configurable Params keys redirect
those fetches:

- ``ModelManager_MirrorUrl``: the base URL that replaces ``https://huggingface.co``
  in artifact download URIs. Empty selects the built-in default
  (https://hf-mirror.com); the special value ``off`` disables rewriting and
  downloads directly; any other value is used as the replacement base.
- ``ModelManager_GithubProxy``: how catalog URLs are fetched. Empty means
  automatic: try the URL directly, then fall back to the same file mapped onto
  the jsDelivr CDN. ``direct`` disables the fallback. Any other value is
  normalized into a prefix and tried first (``prefix + full URL``).

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


def github_raw_to_jsdelivr(url: str) -> str | None:
  """Maps a raw.githubusercontent.com URL onto the jsDelivr CDN, or None when not a raw URL.

  Supports the current /<owner>/<repo>/refs/heads/<branch>/<path> form and the
  legacy /<owner>/<repo>/<branch>/<path> form.
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
      return f"{JSDELIVR_HOST}/gh/{parts[0]}/{parts[1]}@{branch_rest[:slash]}/{branch_rest[slash + 1:]}"
    return f"{JSDELIVR_HOST}/gh/{parts[0]}/{parts[1]}@{parts[2]}/{parts[3]}"
  return None


def get_github_proxy(params) -> str:
  """'' = automatic (direct first, jsDelivr fallback); PROXY_DIRECT_VALUE = no fallback; else a proxy prefix."""
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
  """Ordered catalog URLs to try; the first one that serves a verifiable catalog wins."""
  proxy = get_github_proxy(params)
  if proxy == PROXY_DIRECT_VALUE:
    return [url]
  candidates = [proxy + url] if proxy else [url]
  fallback = github_raw_to_jsdelivr(url)
  if fallback and fallback not in candidates:
    candidates.append(fallback)
  return candidates


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
