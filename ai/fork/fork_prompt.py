"""Build compact fork/host context for chat system prompts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai.system.paths import openpilot_root, workspace_path


def _load_install_snapshot() -> dict[str, Any] | None:
  path = workspace_path("ai_install_snapshot.json")
  if not path.is_file():
    return None
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None
  except (OSError, json.JSONDecodeError):
    return None


def fork_context_prompt_block(root: Path | None = None) -> str | None:
  """Inject current fork + device knowledge without naming a single community brand by default."""
  root = root or openpilot_root()
  parts: list[str] = []

  snapshot = _load_install_snapshot()
  if snapshot:
    host = snapshot.get("host_device") or {}
    if host.get("device_label") or host.get("device_class"):
      parts.append(
        f"当前主机: {host.get('device_label') or host.get('device_class')} "
        f"({host.get('platform') or 'unknown'})"
      )
    comm = snapshot.get("community_match") or {}
    if comm.get("name"):
      parts.append(f"检测到的 openpilot 发行版: {comm['name']} ({comm.get('id', '')})")
    scan = snapshot.get("scan") or {}
    if scan.get("git_branch"):
      parts.append(f"git 分支: {scan['git_branch']} @ {scan.get('git_commit', '?')}")
    if scan.get("repo_layout"):
      parts.append(f"目录布局: {scan['repo_layout']}")
    analysis = snapshot.get("analysis")
    if isinstance(analysis, dict) and analysis.get("summary"):
      parts.append(f"仓库分析摘要: {analysis['summary'][:600]}")

  fork_md = ""
  try:
    from ai.core.wspace.store import read_workspace_file

    fork_md = read_workspace_file("fork").strip()
  except Exception:
    pass
  if fork_md and len(fork_md) > 20:
    parts.append(fork_md[:2000])

  if not parts:
    try:
      from ai.fork.detect_fork import detect_fork

      detect = detect_fork(root, use_cached_analysis=True)
      if detect.get("fork_label"):
        parts.append(f"当前安装树: {detect.get('fork_label')} (置信度 {detect.get('confidence')})")
      if detect.get("git_branch"):
        parts.append(f"分支: {detect['git_branch']}")
      cm = detect.get("community_match") or {}
      if cm.get("wiki_repos"):
        parts.append("可参考社区 Wiki（用户询问文档时再引用，勿主动推销某一 fork）。")
    except Exception:
      return None

  if not parts:
    return None

  return (
    "## 当前 openpilot 环境（自动检测）\n"
    + "\n".join(f"- {p}" for p in parts)
    + "\n\n你是**通用型 op助手**：根据上述**实际安装树**回答，不要臆测未检测到的 fork 特性。"
    "架构或目录因版本更新可能变化，以工具扫描与 read_file 结果为准。"
  )
