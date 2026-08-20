"""Workspace markdown under <ai>/workspace/ — USER, MEMORY, SOUL, daily logs."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ai.common.repo_targets import assistant_repo_path
from ai.system.paths import assistant_workspace_dir, openpilot_root

_FILE_MAP: dict[str, str] = {
  "user": "USER.md",
  "memory": "MEMORY.md",
  "soul": "SOUL.md",
  "agents": "AGENTS.md",
  "tools": "TOOLS.md",
  "heartbeat": "HEARTBEAT.md",
  "fork": "FORK_PROFILE.md",
}

_DEFAULTS: dict[str, str] = {
  "USER.md": """# USER — 用户画像

## 称呼与语言
- 称呼：（待 AI 从对话补充）
- 语言：简体中文

## 常用场景
- openpilot / sunnypilot 调试与适配
- 路线回放、Cabana 信号分析
- 参数调优与 A/B 对比

## 沟通风格
- 直接、可执行步骤优先
- 技术细节适中，避免空泛建议

## 车辆与设备（非敏感）
- 品牌 / 车型：（从 CarParams 或对话补充）
- 设备：comma / PC 开发环境

## 工作流偏好
- 先诊断再修改；写文件后可走 publish_changes
- 长期偏好写入本文件，会话摘要写入 MEMORY.md
""",
  "MEMORY.md": """# MEMORY — 工作区记忆

## 长期事实
（跨会话稳定信息：已验证的配置、路径、约定）

## 已解决问题
（问题 → 根因 → 修复要点，便于复用）

## 待跟进
（未完成事项与下次对话入口）

## 每日日志
（按天见 `ai/workspace/memory/YYYY-MM-DD.md`；此处只放跨日仍重要的结论）

## 禁忌与边界
（不要重复的错误、用户明确拒绝的方案）
""",
  "SOUL.md": """# SOUL — 助手人格

## 语气
专业、冷静、主动执行；车载场景简洁优先。

## 价值观
安全第一：绝不输出转向/制动/油门等执行器指令。

## 主动性
有工具则先用工具验证，再汇报结论；可提议 learned skill 与工作区更新。

## 安全边界
行驶中限制危险写操作；开放模式仍遵守执行器硬规则。
""",
  "AGENTS.md": """# AGENTS — 专员编排

## 专员分工
- 诊断 / 调参 / 开发 / 发布 等域由 orchestrator 路由

## 何时并行
多域独立问题可并行专员，结果由主会话汇总

## 汇总规则
去重、按优先级排序；冲突时以安全与 user 意图为准
""",
  "TOOLS.md": """# TOOLS — 工具习惯

## 常用工具
read_file / write_file / run_shell_command / search_past_conversations

## 调用顺序
先读状态与日志 → 再小范围修改 → 必要时 propose_learned_skill

## 失败回退
工具失败时换路径或缩小范围；记录到 MEMORY.md
""",
  "HEARTBEAT.md": """# HEARTBEAT — 巡检清单

## 巡检项
- 设备连接与 pandad 状态
- 待处理 Issue / 发布任务

## 静默条件
无异常且用户未 @ 助手

## 告警阈值
连续工具失败或关键服务 not running
""",
  "FORK_PROFILE.md": "# Fork profile\n\n（安装后由 op助手 自动写入当前 openpilot 分支摘要；也可手动编辑。）\n",
}


def workspace_dir() -> Path:
  return assistant_workspace_dir(mkdir=True)


def _resolve_key(key: str) -> str | None:
  key = (key or "").strip().lower()
  if not key:
    return None
  if key.endswith(".md"):
    return key
  return _FILE_MAP.get(key)


def list_workspace_files() -> list[dict[str, str]]:
  base = workspace_dir()
  out: list[dict[str, str]] = []
  for logical, filename in _FILE_MAP.items():
    path = base / filename
    out.append({
      "key": logical,
      "filename": filename,
      "exists": path.is_file(),
      "path": str(path),
    })
  return out


def read_workspace_file(key: str) -> str:
  filename = _resolve_key(key)
  if not filename:
    return ""
  path = workspace_dir() / filename
  if not path.is_file():
    return ""
  try:
    return path.read_text(encoding="utf-8")
  except OSError:
    return ""


def write_workspace_file(key: str, content: str) -> dict[str, Any]:
  filename = _resolve_key(key)
  if not filename:
    return {"ok": False, "error": "unknown workspace key"}
  base = workspace_dir()
  path = base / filename
  try:
    path.write_text(content or "", encoding="utf-8")
  except OSError as exc:
    return {"ok": False, "error": str(exc)}
  return {"ok": True, "key": key, "filename": filename, "path": str(path)}


def _copy_tree_files(src_dir: Path, dst_dir: Path) -> None:
  if not src_dir.is_dir():
    return
  dst_dir.mkdir(parents=True, exist_ok=True)
  for item in src_dir.iterdir():
    if not item.is_file():
      continue
    dst = dst_dir / item.name
    if not dst.is_file():
      shutil.copy2(item, dst)


def _migrate_legacy_workspace_dirs() -> None:
  """One-time: pull data from old mistaken or openpilot-root paths."""
  target = workspace_dir()
  ai_root = assistant_repo_path()
  sources = [
    openpilot_root() / "workspace",
    ai_root / "core" / "workspace" / "workspace",
    ai_root / "_legacy_workspace_backup",
  ]
  for src_root in sources:
    if not src_root.is_dir() or src_root.resolve() == target.resolve():
      continue
    for filename in _FILE_MAP.values():
      src = src_root / filename
      dst = target / filename
      if src.is_file() and not dst.is_file():
        shutil.copy2(src, dst)
    _copy_tree_files(src_root / "memory", target / "memory")


def ensure_default_workspace_files() -> None:
  _migrate_legacy_workspace_dirs()
  base = workspace_dir()
  (base / "memory").mkdir(parents=True, exist_ok=True)
  for filename, default in _DEFAULTS.items():
    path = base / filename
    if not path.is_file():
      path.write_text(default, encoding="utf-8")


def heartbeat_checklist() -> str:
  ensure_default_workspace_files()
  return read_workspace_file("heartbeat").strip()


def workspace_prompt_blocks(*, max_chars: int = 2500) -> list[str]:
  blocks: list[str] = []
  for logical in ("user", "memory", "soul", "fork"):
    text = read_workspace_file(logical).strip()
    if not text or len(text) < 8:
      continue
    label = logical.upper() if logical != "fork" else "FORK_PROFILE"
    blocks.append(f"## Workspace {label}\n{text[:max_chars]}")
  return blocks
