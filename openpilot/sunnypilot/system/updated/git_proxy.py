"""
Copyright (c) 2026-, sunnypilot.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

Git source selection for the OTA updater.

GitHub is unreachable from some networks, so the updater measures the official
origin against a list of read-through proxies and uses whichever answers
fastest. The probe is a real `git ls-remote`, not an HTTP HEAD: a proxy can
answer HEAD with a redirect while its TLS handshake with git still fails, so a
HEAD probe picks a source that cannot actually be fetched from.

Every source is sampled more than once and judged on its median, because a
single sample on a flaky link misreports a dead source as healthy.
"""
import os
import shutil
import subprocess
import time
from dataclasses import dataclass

from openpilot.common.swaglog import cloudlog

# Read-through proxies: <prefix><the original github url>. The prefix is
# prepended to the upstream url, so a proxy that only forwards github.com
# cannot serve these forks.
PROXY_PREFIXES = (
  "https://gh-proxy.com/",
  "https://cdn.gh-proxy.org/",
  "https://ghfast.top/",
  "https://ghproxy.net/",
  "https://gh-proxy.net/",
  "https://ghproxy.cc/",
)

# A source slower than this is treated as unusable rather than merely slow.
MAX_ACCEPTABLE_MS = 15000

# Samples per source. The median of these decides the winner.
PROBE_SAMPLES = 3

# A probe that has not answered in this long is a dead source.
PROBE_TIMEOUT_S = 20


@dataclass
class ProbeResult:
  """The outcome of measuring one source."""
  url: str
  ok: bool
  median_ms: int
  samples: list[int]
  error: str = ""

  @property
  def label(self) -> str:
    return self.url


def build_candidates(upstream_url: str, use_proxies: bool = True) -> list[str]:
  """The official source first, then each proxy wrapping it.

  The official source stays first so it wins ties: when github answers in
  the same time as a proxy, the origin is the one that keeps working when
  the proxy is taken down.
  """
  candidates = [upstream_url]
  if use_proxies:
    for prefix in PROXY_PREFIXES:
      candidates.append(f"{prefix}{upstream_url}")
  return candidates


def proxy_url_for(upstream_url: str, prefix: str) -> str:
  """Wrap an upstream url in a proxy prefix."""
  return f"{prefix}{upstream_url}"


def probe_once(url: str, cwd: str | None = None, timeout_s: int = PROBE_TIMEOUT_S) -> tuple[bool, int, str]:
  """Measure one source with a real git ls-remote.

  Returns (ok, elapsed_ms, error). The probe is read-only: it lists the
  remote's refs without fetching any objects.
  """
  start = time.monotonic()
  try:
    proc = subprocess.run(
      ["git", "ls-remote", "--heads", url],
      cwd=cwd,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      encoding="utf-8",
      errors="replace",
      timeout=timeout_s,
      env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"},
    )
  except subprocess.TimeoutExpired:
    return False, int((time.monotonic() - start) * 1000), "timeout"
  except Exception as e:
    return False, int((time.monotonic() - start) * 1000), str(e)

  elapsed_ms = int((time.monotonic() - start) * 1000)
  if proc.returncode != 0:
    detail = (proc.stdout or "").strip().splitlines()
    return False, elapsed_ms, detail[-1] if detail else f"exit {proc.returncode}"

  # ls-remote on an empty or unreachable repo prints nothing but exits 0;
  # require a ref so a captive portal returning 200 is not counted as up.
  if not (proc.stdout or "").strip():
    return False, elapsed_ms, "no refs"

  return True, elapsed_ms, ""


def probe_source(url: str, cwd: str | None = None, samples: int = PROBE_SAMPLES) -> ProbeResult:
  """Sample a source several times and judge it on its median.

  A source counts as healthy only when every sample it ran came back ok: a
  link that answers one request in three is not usable for a fetch.
  """
  timings: list[int] = []
  outcomes: list[bool] = []
  last_error = ""

  for _ in range(samples):
    ok, ms, err = probe_once(url, cwd=cwd)
    timings.append(ms)
    outcomes.append(ok)
    if not ok:
      last_error = err
    # A source that answered cleanly does not need the remaining samples; a
    # source that failed once gets the rest of them to be sure.
    if ok and len(outcomes) >= 2:
      break

  ordered = sorted(timings)
  median_ms = ordered[len(ordered) // 2] if ordered else 0

  if not timings:
    return ProbeResult(url=url, ok=False, median_ms=0, samples=[], error="no samples")

  if not all(outcomes):
    return ProbeResult(url=url, ok=False, median_ms=median_ms, samples=timings, error=last_error or "failed")

  return ProbeResult(url=url, ok=True, median_ms=median_ms, samples=timings, error="")


def select_best(results: list[ProbeResult], max_ms: int = MAX_ACCEPTABLE_MS) -> ProbeResult | None:
  """Pick the fastest healthy source, or None when none answered.

  Ties keep the earlier candidate, and the official origin is the first
  candidate, so an equal-time proxy never displaces a working github.
  """
  healthy = [r for r in results if r.ok and r.median_ms <= max_ms]
  if not healthy:
    return None
  return min(healthy, key=lambda r: r.median_ms)


def _git(args: list[str], cwd: str | None = None) -> tuple[int, str]:
  """Run a git command, returning (exit code, combined output)."""
  try:
    proc = subprocess.run(
      ["git"] + args,
      cwd=cwd,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      encoding="utf-8",
      errors="replace",
      timeout=300,
      env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"},
    )
  except Exception as e:
    return 1, str(e)
  return proc.returncode, (proc.stdout or "").strip()


def rewrite_remote(url: str, cwd: str | None = None) -> bool:
  """Point origin at url. Returns whether the remote was changed."""
  code, _ = _git(["remote", "set-url", "origin", url], cwd=cwd)
  return code == 0


def submodule_paths(root: str) -> list[str]:
  """Every submodule path in the tree, nested ones included.

  The .gitmodules file is the source of truth here: `git submodule foreach`
  only visits submodules that are already registered and cloned, so a
  submodule that has not been fetched yet would be missed.
  """
  paths = list(upstream_urls_from_gitmodules(root).keys())

  # Also pick up any registered submodule that is not in .gitmodules.
  code, out = _git(["submodule", "foreach", "--recursive", "--quiet", "echo $sm_path"], cwd=root)
  if code == 0:
    for line in out.splitlines():
      p = line.strip()
      if p and p not in paths:
        paths.append(p)
  return paths


def read_gitmodules(root: str) -> list[tuple[str, str, str]]:
  """Every submodule in .gitmodules as (section, path, url).

  The section name and the path are independent: opendbc's section is
  "opendbc" while its path is "opendbc_repo". The section is the key git
  uses for submodule.<name>.url, so both are needed.
  """
  entries: list[tuple[str, str, str]] = []
  path = os.path.join(root, ".gitmodules")
  if not os.path.exists(path):
    return entries

  section = ""
  sub_path = ""
  sub_url = ""

  def flush():
    if sub_path and sub_url:
      entries.append((section, sub_path, sub_url))

  with open(path, encoding="utf-8") as f:
    for raw in f:
      line = raw.strip()
      if line.startswith("[submodule"):
        flush()
        section = ""
        sub_path = ""
        sub_url = ""
        # [submodule "name"]
        name = line.split('"')[1] if '"' in line else ""
        section = name
      elif line.startswith("path"):
        sub_path = line.split("=", 1)[1].strip()
      elif line.startswith("url"):
        sub_url = line.split("=", 1)[1].strip()
  flush()
  return entries


def upstream_urls_from_gitmodules(root: str) -> dict[str, str]:
  """Map each submodule path to its upstream url, read from .gitmodules.

  Reading the file rather than hardcoding the list keeps this correct when
  a submodule is added, removed or pointed elsewhere.
  """
  return {path: url for _, path, url in read_gitmodules(root)}


def set_submodule_config_url(root: str, section: str, url: str) -> bool:
  """Set submodule.<name>.url in the parent's .git/config.

  `git submodule sync` copies the .gitmodules url into this key, so the
  proxy has to be written after a sync or the sync puts github back.
  `git submodule update --init` reads this key when it clones a submodule
  that is not there yet.

  The name is the .gitmodules section name, not the path: opendbc's
  section is "opendbc" even though its path is "opendbc_repo".
  """
  if not section:
    return False
  code, _ = _git(["config", f"submodule.{section}.url", url], cwd=root)
  return code == 0


def apply_source(root: str, upstream_url: str, prefix: str) -> int:
  """Point the main repo and every submodule at the chosen source.

  The main repo's non-origin remotes (the fork's own cnb/sunnypilot/zp
  mirrors) are left alone: they are the developer's remotes, and rewriting
  them would silently redirect pushes.
  """
  prefix_url = proxy_url_for(upstream_url, prefix)
  changed = 0

  if rewrite_remote(prefix_url, cwd=root):
    changed += 1
    cloudlog.info(f"git_proxy: main repo origin -> {prefix_url}")

  changed += apply_submodules(root, prefix)
  return changed


def apply_submodules(root: str, prefix: str) -> int:
  """Point every submodule at the proxy, in both places git looks.

  Two places matter: the submodule's own remote.origin.url, which the fetch
  inside the submodule uses, and the parent's submodule.<name>.url, which
  decides where a not-yet-cloned submodule is fetched from.
  """
  changed = 0
  entries = read_gitmodules(root)

  # A submodule registered in .git/config but missing from .gitmodules still
  # needs its own origin switched over.
  known = {path for _, path, _ in entries}
  for sm_path in submodule_paths(root):
    if sm_path in known:
      continue
    sub_root = os.path.join(root, sm_path)
    code, out = _git(["config", "--get", "remote.origin.url"], cwd=sub_root)
    upstream = out.strip() if code == 0 else ""
    if not upstream:
      continue
    if rewrite_remote(proxy_url_for(upstream, prefix), cwd=sub_root):
      changed += 1

  for section, sm_path, upstream in entries:
    sub_root = os.path.join(root, sm_path)
    proxy_sub_url = proxy_url_for(upstream, prefix)

    if os.path.isdir(os.path.join(sub_root, ".git")) or os.path.isfile(os.path.join(sub_root, ".git")):
      if rewrite_remote(proxy_sub_url, cwd=sub_root):
        changed += 1
    if set_submodule_config_url(root, section, proxy_sub_url):
      changed += 1
  return changed


def restore_source(root: str, upstream_url: str) -> None:
  """Put the main repo and every submodule back on the real upstream.

  Used when github answers again: leaving a proxy in place would keep the
  repo dependent on a third party that can disappear at any time.
  """
  rewrite_remote(upstream_url, cwd=root)

  for section, sm_path, upstream in read_gitmodules(root):
    rewrite_remote(upstream, cwd=os.path.join(root, sm_path))
    set_submodule_config_url(root, section, upstream)


def measure_and_select(root: str, upstream_url: str, use_proxies: bool = True) -> tuple[ProbeResult | None, str]:
  """Probe every candidate and return the winner plus the prefix to use.

  The prefix is empty for the official source, so the caller can tell an
  origin that needs no rewriting apart from one that does.
  """
  candidates = build_candidates(upstream_url, use_proxies=use_proxies)
  results: list[ProbeResult] = []

  for url in candidates:
    result = probe_source(url, cwd=root)
    results.append(result)
    cloudlog.info(
      f"git_proxy: probe {'OK ' if result.ok else 'FAIL'} {result.median_ms:>6}ms {url}"
      + (f" ({result.error})" if result.error else "")
    )

  best = select_best(results)
  if best is None:
    return None, ""

  if best.url == upstream_url:
    return best, ""
  prefix = best.url[: len(best.url) - len(upstream_url)]
  return best, prefix


def which_git() -> str | None:
  """The git binary, or None when git is missing."""
  return shutil.which("git")
