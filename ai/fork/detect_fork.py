"""Fork detection via repository scan + optional AI analysis (no fixed fork list)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai.fork.analyze_fork import load_cached_analysis
from ai.fork.repo_scan import compact_scan_for_api, derive_fork_identity, scan_openpilot_repo


def detect_fork(root: Path | None = None, *, use_cached_analysis: bool = True) -> dict[str, Any]:
  """
  Quick detect: scan filesystem + git remotes.
  If use_cached_analysis and a prior AI run matches git commit, attach analysis.
  """
  if root is None:
    from ai.system.paths import openpilot_root

    root = openpilot_root()
  root = root.resolve()
  scan = scan_openpilot_repo(root)
  identity = derive_fork_identity(scan)
  commit = scan.get("git_commit")

  analysis = None
  mode = "repository_scan"
  if use_cached_analysis and commit:
    cached = load_cached_analysis(git_commit=commit)
    if cached and cached.get("analysis"):
      analysis = cached["analysis"]
      mode = "ai_cached"
      # Prefer AI naming when available
      if analysis.get("fork_identity"):
        identity = {
          **identity,
          "fork_id": analysis.get("fork_identity", identity["fork_id"]),
          "fork_label": analysis.get("fork_name", identity["fork_label"]),
          "confidence": analysis.get("confidence", identity["confidence"]),
        }

  return {
    "ok": True,
    "mode": mode,
    "openpilot_root": str(root),
    "fork_id": identity["fork_id"],
    "fork_label": identity["fork_label"],
    "confidence": identity["confidence"],
    "reasons": identity["reasons"],
    "git_branch": scan.get("git_branch"),
    "git_commit": commit,
    "git_remotes": scan.get("git_remotes", [])[:6],
    "scan": compact_scan_for_api(scan),
    "analysis": analysis,
    "analysis_available": analysis is not None,
    "hint": (
      "调用 POST /api/ai/fork/analyze 让 AI 阅读整个 openpilot 项目并生成分析报告"
      if not analysis
      else "分析结果已缓存，git commit 变化后需重新分析"
    ),
  }
