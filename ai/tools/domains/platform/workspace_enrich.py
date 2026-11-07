"""Workspace health checks and AI-driven enrichment hints."""

from __future__ import annotations

from typing import Any

from ai.tools.domains.core.memory_store import get_memory
from ai.core.wspace.store import _FILE_MAP, read_workspace_file, write_workspace_file

# Minimum useful content length (excluding boilerplate headers).
_MIN_CHARS = {
  "user": 120,
  "memory": 80,
  "soul": 60,
  "agents": 80,
  "tools": 60,
  "heartbeat": 40,
}

_SECTION_HINTS: dict[str, list[str]] = {
  "user": [
    "## 称呼与语言",
    "## 常用场景",
    "## 沟通风格",
    "## 车辆与设备（非敏感）",
    "## 工作流偏好",
  ],
  "memory": [
    "## 长期事实",
    "## 已解决问题",
    "## 待跟进",
    "## 禁忌与边界",
  ],
  "soul": [
    "## 语气",
    "## 价值观",
    "## 主动性",
    "## 安全边界",
  ],
  "agents": [
    "## 专员分工",
    "## 何时并行",
    "## 汇总规则",
  ],
  "tools": [
    "## 常用工具",
    "## 调用顺序",
    "## 失败回退",
  ],
  "heartbeat": [
    "## 巡检项",
    "## 静默条件",
    "## 告警阈值",
  ],
}


def _is_sparse(key: str, content: str) -> bool:
  text = (content or "").strip()
  if not text:
    return True
  # Strip markdown headers and placeholder parentheses lines.
  stripped = text
  for line in text.splitlines():
    if "（在此" in line or "(在此" in line or "optional" in line.lower():
      stripped = stripped.replace(line, "")
  stripped = stripped.strip()
  min_len = _MIN_CHARS.get(key, 60)
  return len(stripped) < min_len


def workspace_health() -> dict[str, Any]:
  sparse: list[dict[str, Any]] = []
  ok: list[str] = []
  for key in _FILE_MAP:
    content = read_workspace_file(key)
    if _is_sparse(key, content):
      sparse.append({
        "key": key,
        "filename": _FILE_MAP[key],
        "chars": len((content or "").strip()),
        "minChars": _MIN_CHARS.get(key, 60),
        "suggestedSections": _SECTION_HINTS.get(key, []),
      })
    else:
      ok.append(key)
  return {
    "ok": True,
    "sparse": sparse,
    "complete": ok,
    "needsEnrichment": len(sparse) > 0,
  }


def enrichment_prompt_block(params: Any = None) -> str:
  """System prompt nudge when workspace files are sparse."""
  health = workspace_health()
  if not health.get("needsEnrichment"):
    return ""
  lines = [
    "Workspace enrichment: the following files are sparse — use update_workspace_file to expand them from conversation context:",
  ]
  for item in health.get("sparse") or []:
    lines.append(f"- {item['filename']}: add {', '.join(item.get('suggestedSections') or [])}")
  if params is not None:
    mem = get_memory(params)
    if mem.get("vehicle_profile"):
      lines.append("- Incorporate vehicle_profile facts into USER.md or MEMORY.md where relevant.")
  return "\n".join(lines)


def update_workspace_file(
  params: Any,
  *,
  key: str,
  content: str,
  append: bool = False,
  merge_section: str = "",
) -> dict[str, Any]:
  """Write or append workspace markdown (AI self-maintenance)."""
  _ = params
  key = (key or "").strip().lower()
  content = (content or "").strip()
  if not key or not content:
    return {"ok": False, "error": "key and content required"}
  if key not in _FILE_MAP and not key.endswith(".md"):
    return {"ok": False, "error": f"unknown key; use one of: {', '.join(_FILE_MAP)}"}

  if append or merge_section:
    prev = read_workspace_file(key)
    if merge_section:
      section = merge_section if merge_section.startswith("##") else f"## {merge_section}"
      if section in prev:
        return {"ok": False, "error": f"section already exists: {section}"}
      content = (prev + "\n\n" + section + "\n" + content).strip() if prev else f"{section}\n{content}"
    else:
      content = (prev + "\n\n" + content).strip() if prev else content

  return write_workspace_file(key, content)


def bootstrap_workspace_templates(*, force: bool = False) -> dict[str, Any]:
  """Write structured templates for empty/sparse files."""
  from ai.core.wspace.store import _DEFAULTS, workspace_dir

  written: list[str] = []
  base = workspace_dir()
  for logical, filename in _FILE_MAP.items():
    path = base / filename
    default = _DEFAULTS.get(filename, "")
    if not default:
      continue
    current = read_workspace_file(logical)
    if force or _is_sparse(logical, current):
      path.write_text(default, encoding="utf-8")
      written.append(filename)
  return {"ok": True, "written": written}
