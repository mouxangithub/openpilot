"""Match installed openpilot trees to known community fork hints (registry + scan)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_REGISTRY_PATH = Path(__file__).resolve().parent / "community_registry.json"


@lru_cache(maxsize=1)
def load_community_registry() -> dict[str, Any]:
  try:
    data = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {"forks": []}
  except (OSError, json.JSONDecodeError):
    return {"version": 0, "forks": []}


def list_known_forks() -> list[dict[str, Any]]:
  return list(load_community_registry().get("forks") or [])


def _norm_slug(text: str) -> str:
  return re.sub(r"[^\w./-]+", "", (text or "").lower().strip())


def _remote_matches(entry: dict[str, Any], remote_identity: dict[str, Any]) -> bool:
  slug = _norm_slug(remote_identity.get("slug") or "")
  owner = _norm_slug(remote_identity.get("owner") or "")
  repo = _norm_slug(remote_identity.get("repo") or "")
  if not slug and not repo:
    return False
  for pattern in entry.get("remotes") or []:
    p = _norm_slug(str(pattern))
    if not p:
      continue
    if slug == p or slug.endswith("/" + p.split("/")[-1]):
      return True
    if repo and p.endswith("/" + repo) and (not owner or owner in p):
      return True
    if owner and repo and f"{owner}/{repo}" == p:
      return True
  return False


def _prefix_overlap(entry: dict[str, Any], param_prefixes: dict[str, int]) -> int:
  score = 0
  for prefix in entry.get("param_prefixes") or []:
    p = str(prefix)
    for key, count in (param_prefixes or {}).items():
      if key.startswith(p) or p.rstrip("_") in key:
        score += int(count)
  return score


def match_community_profile(scan: dict[str, Any]) -> dict[str, Any] | None:
  """Return best registry entry for this scan, or None."""
  remote = scan.get("remote_identity") or {}
  dirs = {d.lower() for d in (scan.get("distinctive_dirs") or [])}
  root_files = {f.lower() for f in (scan.get("root_files") or [])}
  branch = (scan.get("git_branch") or "").lower()
  readme = (scan.get("readme_excerpt") or "").lower()
  prefixes = scan.get("param_prefixes") or {}

  root_path = Path(scan.get("openpilot_root") or ".")
  has_sunnypilot_tree = (root_path / "sunnypilot").is_dir()

  best: tuple[int, dict[str, Any]] | None = None
  for entry in list_known_forks():
    score = 0
    reasons: list[str] = []

    if _remote_matches(entry, remote):
      skip_remote = False
      if entry.get("id") == "commaai/openpilot" and has_sunnypilot_tree:
        skip_remote = True
      # bp remote is often an upstream mirror; don't label sunnypilot trees as BluePilot.
      if (
        entry.get("id") == "BluePilotDev/bluepilot"
        and has_sunnypilot_tree
        and not (root_path / "bluepilot").is_dir()
      ):
        skip_remote = True
      if not skip_remote:
        score += 100
        reasons.append(f"remote→{entry.get('id')}")

    for marker in entry.get("marker_dirs") or []:
      marker_l = marker.lower()
      if marker_l in dirs or (root_path / marker).is_dir():
        score += 40
        reasons.append(f"dir:{marker}")

    for marker in entry.get("marker_files") or []:
      if marker.lower() in root_files or (scan.get("openpilot_root") and Path(scan["openpilot_root"]) / marker).is_file():
        score += 35
        reasons.append(f"file:{marker}")

    pscore = _prefix_overlap(entry, prefixes)
    if pscore:
      score += min(pscore, 30)
      reasons.append(f"param_prefix:+{pscore}")

    for br in entry.get("branches") or []:
      if br.lower() == branch:
        score += 15
        reasons.append(f"branch:{branch}")
        break

    for alias in entry.get("aliases") or []:
      if alias.lower() in readme:
        score += 10
        reasons.append(f"readme:{alias}")
        break

    if score <= 0:
      continue
    enriched = {**entry, "_match_score": score, "_match_reasons": reasons}
    if best is None or score > best[0]:
      best = (score, enriched)

  return best[1] if best else None


def enrich_fork_detection(
  detect: dict[str, Any],
  scan: dict[str, Any] | None = None,
) -> dict[str, Any]:
  """Attach community registry match + learning hints to detect_fork() output."""
  if scan is None:
    from ai.fork.repo_scan import scan_openpilot_repo
    from pathlib import Path

    root = Path(detect.get("openpilot_root") or ".")
    scan = scan_openpilot_repo(root)

  profile = match_community_profile(scan)
  host = None
  try:
    from ai.system.comma_host import detect_comma_product

    host = detect_comma_product()
  except Exception:
    host = None

  out = {**detect, "community_profile": profile, "host_device": host}
  if profile:
    out["community_match"] = {
      "id": profile.get("id"),
      "name": profile.get("name"),
      "score": profile.get("_match_score"),
      "reasons": profile.get("_match_reasons"),
      "device_targets": profile.get("device_targets"),
      "wiki_repos": profile.get("wiki_repos"),
      "notes": profile.get("notes"),
    }
    if profile.get("name") and detect.get("confidence") in ("low", "medium"):
      out["fork_label"] = profile["name"]
      out["fork_id"] = profile.get("id") or detect.get("fork_id")
  if host:
    out["device_class"] = host.get("device_class")
    out["device_label"] = host.get("device_label")
  return out
