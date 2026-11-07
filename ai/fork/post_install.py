"""Post-install / post-integrate learning — snapshot current openpilot tree for the AI."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai.fork.analyze_fork import load_cached_analysis
from ai.fork.community_profiles import enrich_fork_detection, match_community_profile
from ai.fork.detect_fork import detect_fork
from ai.fork.repo_scan import compact_scan_for_api, scan_openpilot_repo
from ai.system.paths import openpilot_root, workspace_path


def _repo_layout_label(root: Path) -> str:
  from ai.system.paths import repo_layout

  return repo_layout()


def _render_fork_profile_md(payload: dict[str, Any]) -> str:
  host = payload.get("host_device") or {}
  comm = payload.get("community_match") or {}
  scan = payload.get("scan") or {}
  analysis = payload.get("analysis") or {}

  lines = [
    "# Fork profile",
    "",
    f"- 更新时间 (UTC): {payload.get('learned_at', '')}",
    f"- openpilot 根: `{payload.get('openpilot_root', '')}`",
    f"- 设备: **{host.get('device_label') or host.get('device_class') or '?'}** ({host.get('platform')})",
    f"- Git: `{scan.get('git_branch')}` @ `{scan.get('git_commit')}`",
    f"- Remote: {(scan.get('remote_identity') or {}).get('slug') or '—'}",
    f"- 目录布局: `{payload.get('repo_layout')}`",
    f"- 识别发行版: **{comm.get('name') or payload.get('fork_label') or '未知'}**",
  ]
  if comm.get("reasons"):
    lines.append(f"- 匹配依据: {', '.join(comm['reasons'][:6])}")
  if analysis.get("summary"):
    lines.append("")
    lines.append("## AI 分析摘要")
    lines.append(str(analysis["summary"]))
  if analysis.get("distinctive_features"):
    lines.append("")
    lines.append("## 特性")
    for feat in analysis["distinctive_features"][:12]:
      lines.append(f"- {feat}")
  if comm.get("wiki_repos"):
    lines.append("")
    lines.append("## 社区文档")
    for wiki in comm["wiki_repos"][:4]:
      url = wiki.get("url") if isinstance(wiki, dict) else wiki
      if url:
        lines.append(f"- {url}")
  lines.append("")
  lines.append(
    "> 由 `install/integrate` 自动生成。openpilot 更新后请重新运行 integrate 或在 Web「Fork 分析」触发 AI 深度分析。"
  )
  lines.append("")
  return "\n".join(lines)


def run_post_install_learn(root: Path | None = None, *, write_workspace: bool = True) -> dict[str, Any]:
  """
  Non-LLM snapshot after install/integrate.
  Saves `ai_install_snapshot.json` + updates workspace/FORK_PROFILE.md.
  """
  root = (root or openpilot_root()).resolve()
  scan = scan_openpilot_repo(root)
  compact = compact_scan_for_api(scan)
  compact["repo_layout"] = _repo_layout_label(root)

  detect = detect_fork(root, use_cached_analysis=True)
  enriched = enrich_fork_detection(detect, scan)
  profile = match_community_profile(scan)

  commit = scan.get("git_commit")
  cached = load_cached_analysis(git_commit=commit) if commit else None
  analysis = (cached or {}).get("analysis") if cached else enriched.get("analysis")

  payload: dict[str, Any] = {
    "ok": True,
    "learned_at": datetime.now(timezone.utc).isoformat(),
    "openpilot_root": str(root),
    "repo_layout": compact.get("repo_layout"),
    "fork_id": enriched.get("fork_id"),
    "fork_label": enriched.get("fork_label"),
    "confidence": enriched.get("confidence"),
    "host_device": enriched.get("host_device"),
    "device_class": enriched.get("device_class"),
    "community_match": enriched.get("community_match"),
    "community_profile_id": (profile or {}).get("id"),
    "scan": compact,
    "analysis": analysis,
    "analysis_available": analysis is not None,
    "next_steps": [
      "配置模型 API 后可在 Web「设置 → 开发 → Fork 分析」运行 AI 深度分析",
      "git commit 变化后分析缓存失效，需重新 analyze",
    ],
  }

  snap_path = workspace_path("ai_install_snapshot.json", mkdir=True)
  snap_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

  wiki_result: dict[str, Any] | None = None
  try:
    from openpilot.common.params import Params
    from ai.fork.wiki_ingest import ingest_wikis_for_profile

    profile = match_community_profile(scan)
    if profile and (profile.get("wiki_repos") or []):
      wiki_result = ingest_wikis_for_profile(
        Params(),
        profile,
        max_files_per_repo=0,
        force=False,
      )
      payload["wiki_ingest"] = wiki_result
  except Exception as exc:
    payload["wiki_ingest"] = {"ok": False, "error": str(exc)}

  if write_workspace:
    try:
      from ai.core.wspace.store import ensure_default_workspace_files, write_workspace_file

      ensure_default_workspace_files()
      write_workspace_file("fork", _render_fork_profile_md(payload))
    except Exception:
      pass

  return payload
