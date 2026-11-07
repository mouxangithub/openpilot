"""GitHub repo targets for op助手 PR automation (openpilot vs assistant ai repo)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ai.system.paths import openpilot_root

OPENPILOT_REPO_URL = "https://github.com/mouxangithub/openpilot"
ASSISTANT_REPO_URL = "https://github.com/mouxangithub/ai"

LABEL_AUTO_REVIEW = "ai-auto-review"
LABEL_AUTO_FIX = "ai-auto-fix"
LABEL_SAFE_MERGE = "ai-safe-merge"

MAX_AUTO_MERGE_LINES = 500

# openpilot / master-c3: only ai subtree auto-merge eligible
OPENPILOT_PROTECTED_BASES = frozenset({"master-c3", "master", "main"})
OPENPILOT_MERGE_HEAD_PREFIXES = ("ai/",)
OPENPILOT_MERGE_PATH_ALLOW = ("ai/", "docs/", ".github/")
OPENPILOT_MERGE_PATH_BLOCK = (
  "selfdrive/",
  "openpilot/selfdrive/",
  "panda/",
  "opendbc/safety/",
  "opendbc/car/",
  "opendbc_repo/",
  "cereal/",
  "common/params_keys.h",
  "openpilot/common/params_keys.h",
)

# standalone ai repo: broader allow
ASSISTANT_MERGE_HEAD_PREFIXES = ("ai/", "fix/", "web/")
ASSISTANT_MERGE_PATH_ALLOW = tuple()  # empty = no extra allow filter
ASSISTANT_MERGE_PATH_BLOCK = tuple()
ASSISTANT_DEFAULT_BASE = "main"


def _read_config_str(key: str, default: str = "") -> str:
  try:
    from ai.common.config_store import get_config_store
    return str(get_config_store().get(key, default) or default).strip()
  except Exception:
    return default


def assistant_repo_path() -> Path:
  env = (os.environ.get("AI_ASSISTANT_REPO_PATH") or os.environ.get("OP_ASSISTANT_REPO") or "").strip()
  if env:
    return Path(env).expanduser().resolve()
  cfg = _read_config_str("ai_assistant_repo_path")
  if cfg:
    return Path(cfg).expanduser().resolve()
  standalone = openpilot_root().parent / "ai"
  if (standalone / ".git").is_dir() and (standalone / "aid.py").is_file():
    return standalone.resolve()
  nested = openpilot_root() / "ai"
  if (nested / "aid.py").is_file():
    return nested.resolve()
  return nested.resolve()


def resolve_repo_root(repo_target: str = "openpilot") -> Path:
  t = (repo_target or "openpilot").strip().lower()
  if t in ("ai", "assistant", "op-assistant", "op助手"):
    return assistant_repo_path()
  return openpilot_root()


def resolve_repo_url(repo_target: str = "openpilot") -> str:
  t = (repo_target or "openpilot").strip().lower()
  if t in ("ai", "assistant", "op-assistant", "op助手"):
    return _read_config_str("ai_assistant_repo_url", ASSISTANT_REPO_URL) or ASSISTANT_REPO_URL
  return _read_config_str("ai_openpilot_repo_url", OPENPILOT_REPO_URL) or OPENPILOT_REPO_URL


def default_base_branch(repo_target: str = "openpilot") -> str:
  t = (repo_target or "openpilot").strip().lower()
  if t in ("ai", "assistant", "op-assistant", "op助手"):
    return _read_config_str("ai_assistant_default_branch", ASSISTANT_DEFAULT_BASE) or ASSISTANT_DEFAULT_BASE
  return _read_config_str("ai_openpilot_default_branch", "master-c3") or "master-c3"


def repo_target_meta(repo_target: str = "openpilot") -> dict[str, Any]:
  t = (repo_target or "openpilot").strip().lower()
  is_ai = t in ("ai", "assistant", "op-assistant", "op助手")
  return {
    "repo_target": "assistant" if is_ai else "openpilot",
    "repo_url": resolve_repo_url(repo_target),
    "repo_root": str(resolve_repo_root(repo_target)),
    "default_base": default_base_branch(repo_target),
    "pulls_url": f"{resolve_repo_url(repo_target).rstrip('/')}/pulls",
  }


def _path_allowed(filename: str, allow: tuple[str, ...], block: tuple[str, ...]) -> bool:
  fn = (filename or "").replace("\\", "/")
  for b in block:
    if fn.startswith(b) or f"/{b}" in fn:
      return False
  if not allow:
    return True
  return any(fn.startswith(p) for p in allow)


def analyze_pr_files(
  files: list[dict[str, Any]],
  *,
  repo_target: str = "openpilot",
) -> dict[str, Any]:
  t = (repo_target or "openpilot").strip().lower()
  is_ai = t in ("ai", "assistant", "op-assistant", "op助手")
  allow = ASSISTANT_MERGE_PATH_ALLOW if is_ai else OPENPILOT_MERGE_PATH_ALLOW
  block = ASSISTANT_MERGE_PATH_BLOCK if is_ai else OPENPILOT_MERGE_PATH_BLOCK
  head_allow = ASSISTANT_MERGE_HEAD_PREFIXES if is_ai else OPENPILOT_MERGE_HEAD_PREFIXES

  names = [str(f.get("filename") or "") for f in files]
  additions = sum(int(f.get("additions") or 0) for f in files)
  deletions = sum(int(f.get("deletions") or 0) for f in files)
  total_lines = additions + deletions
  blocked = [n for n in names if not _path_allowed(n, allow, block)]
  allowed = [n for n in names if _path_allowed(n, allow, block)]

  auto_merge_ok = (
    not blocked
    and total_lines <= MAX_AUTO_MERGE_LINES
    and len(names) > 0
  )
  if is_ai:
    auto_merge_ok = auto_merge_ok and total_lines <= MAX_AUTO_MERGE_LINES * 2

  return {
    "files": names,
    "files_count": len(names),
    "additions": additions,
    "deletions": deletions,
    "total_lines": total_lines,
    "blocked_paths": blocked,
    "allowed_paths": allowed,
    "auto_merge_eligible": auto_merge_ok,
    "head_prefixes_ok": head_allow,
    "max_lines": MAX_AUTO_MERGE_LINES,
  }


def suggest_pr_labels(
  *,
  repo_target: str = "openpilot",
  files: list[dict[str, Any]] | None = None,
  severity: str = "",
  request_auto_fix: bool = False,
) -> list[str]:
  t = (repo_target or "openpilot").strip().lower()
  is_ai = t in ("ai", "assistant", "op-assistant", "op助手")
  labels = [LABEL_AUTO_REVIEW]
  analysis = analyze_pr_files(files or [], repo_target=repo_target)
  sev = (severity or "").strip().lower()
  if sev in ("ui", "typo", "docs", "web"):
    if analysis.get("auto_merge_eligible") or (is_ai and not files):
      labels.append(LABEL_SAFE_MERGE)
  if request_auto_fix and analysis.get("auto_merge_eligible"):
    labels.append(LABEL_AUTO_FIX)
  return labels


def merge_allowed(
  *,
  repo_target: str,
  head: str,
  base: str,
  files: list[dict[str, Any]],
  labels: list[str] | None = None,
) -> tuple[bool, str]:
  label_set = {str(x) for x in (labels or [])}
  if LABEL_SAFE_MERGE not in label_set:
    return False, f"missing label {LABEL_SAFE_MERGE}"

  t = (repo_target or "openpilot").strip().lower()
  is_ai = t in ("ai", "assistant", "op-assistant", "op助手")
  head_allow = ASSISTANT_MERGE_HEAD_PREFIXES if is_ai else OPENPILOT_MERGE_HEAD_PREFIXES
  if not any(str(head or "").startswith(p) for p in head_allow):
    return False, f"head branch must start with one of {head_allow}"

  if not is_ai and base in OPENPILOT_PROTECTED_BASES:
    analysis = analyze_pr_files(files, repo_target=repo_target)
    if not analysis.get("auto_merge_eligible"):
      reason = "paths or diff size not eligible for auto-merge on openpilot"
      if analysis.get("blocked_paths"):
        reason += f"; blocked: {analysis['blocked_paths'][:5]}"
      return False, reason

  return True, "ok"
