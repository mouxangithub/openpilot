"""Daily memory journals — workspace/memory/YYYY-MM-DD.md (Hermes / OpenClaw style)."""

from __future__ import annotations

import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from ai.core.wspace.store import workspace_dir

_MEMORY_SUBDIR = "memory"
_INDEX_NAME = "INDEX.md"
_MAX_DAILY_CHARS = 12000
_MAX_ENTRY_CHARS = 2000
_DEFAULT_PROMPT_DAYS = 7
_DEFAULT_PROMPT_CHARS = 4200


def daily_memory_dir() -> Path:
  path = workspace_dir() / _MEMORY_SUBDIR
  path.mkdir(parents=True, exist_ok=True)
  return path


def _date_key(day: date | None = None) -> str:
  d = day or date.today()
  return d.strftime("%Y-%m-%d")


def daily_memory_path(day: date | None = None) -> Path:
  return daily_memory_dir() / f"{_date_key(day)}.md"


def _default_header(day: date | None = None) -> str:
  key = _date_key(day)
  return f"# Daily memory — {key}\n\n> 当日对话摘要（自动 + 工具写入）。长期事实请沉淀到 MEMORY.md。\n"


def read_daily_memory(day: date | None = None) -> str:
  path = daily_memory_path(day)
  if not path.is_file():
    return ""
  try:
    return path.read_text(encoding="utf-8")
  except OSError:
    return ""


def append_daily_memory(
  *,
  bullets: list[str] | str,
  session_id: str = "",
  title: str = "",
) -> dict[str, Any]:
  """Append a timestamped section to today's daily log."""
  if isinstance(bullets, str):
    items = [bullets.strip()] if bullets.strip() else []
  else:
    items = [str(b).strip() for b in bullets if str(b).strip()]
  if not items:
    return {"ok": False, "error": "empty bullets"}

  path = daily_memory_path()
  now = datetime.now()
  stamp = now.strftime("%H:%M")
  header = _default_header()
  prev = read_daily_memory() if path.is_file() else ""
  if not prev.strip():
    body = header
  else:
    body = prev.rstrip() + "\n"

  label = title.strip() or "会话"
  if session_id:
    label = f"{label} ({session_id[:8]})"
  section = f"\n## {stamp} — {label}\n"
  for item in items[:12]:
    line = item[:_MAX_ENTRY_CHARS]
    section += f"- {line}\n"

  body = (body + section).strip() + "\n"
  if len(body) > _MAX_DAILY_CHARS:
    body = body[-_MAX_DAILY_CHARS:]
    body = _default_header() + "\n[... earlier entries truncated ...]\n\n" + body.split("\n", 4)[-1]

  try:
    path.write_text(body, encoding="utf-8")
  except OSError as exc:
    return {"ok": False, "error": str(exc)}
  refresh_daily_index()
  return {"ok": True, "path": str(path), "date": _date_key(), "added": len(items)}


def list_daily_memory_files(*, days: int = 14) -> list[dict[str, Any]]:
  base = daily_memory_dir()
  if not base.is_dir():
    return []
  out: list[dict[str, Any]] = []
  for path in sorted(base.glob("*.md"), reverse=True):
    m = re.match(r"^(\d{4}-\d{2}-\d{2})\.md$", path.name)
    if not m:
      continue
    try:
      text = path.read_text(encoding="utf-8")
    except OSError:
      text = ""
    out.append({
      "date": m.group(1),
      "path": str(path),
      "chars": len(text),
    })
    if len(out) >= days:
      break
  return out


def _last_bullet_preview(text: str, *, max_len: int = 72) -> str:
  for line in reversed(text.splitlines()):
    s = line.strip()
    if s.startswith("- "):
      return s[2:][:max_len]
    if s.startswith("## "):
      continue
  return ""


def refresh_daily_index(*, list_days: int = 14) -> dict[str, Any]:
  """Maintain memory/INDEX.md — wiki-style table of daily pages (for AI self-read)."""
  files = list_daily_memory_files(days=list_days)
  lines = [
    "# Daily Memory Index",
    "",
    "> Hermes 风格「一日一页」：`workspace/memory/YYYY-MM-DD.md`。",
    "> 本索引自动更新；长期事实请写入 ../MEMORY.md。",
    "",
    "| 日期 | 文件 | 最近一条 |",
    "|------|------|----------|",
  ]
  for item in files:
    date_key = item["date"]
    try:
      body = read_daily_memory(date.fromisoformat(date_key))
    except ValueError:
      body = ""
    preview = _last_bullet_preview(body) or "（空）"
    lines.append(f"| {date_key} | [{date_key}.md]({date_key}.md) | {preview} |")

  index_path = daily_memory_dir() / _INDEX_NAME
  try:
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
  except OSError as exc:
    return {"ok": False, "error": str(exc)}
  return {"ok": True, "path": str(index_path), "days": len(files)}


def read_daily_index() -> str:
  path = daily_memory_dir() / _INDEX_NAME
  if not path.is_file():
    refresh_daily_index()
  try:
    return path.read_text(encoding="utf-8")
  except OSError:
    return ""


def read_recent_daily_memories(*, days: int = 3, max_chars: int = 2200) -> str:
  """Concatenate recent daily logs (legacy helper). Prefer build_daily_memory_prompt_block()."""
  block = build_daily_memory_prompt_block(days=days, max_chars=max_chars, include_index=False)
  if block.startswith("# Daily memory"):
    return block.split("\n", 1)[-1].strip()
  return block


def build_daily_memory_prompt_block(
  *,
  days: int = _DEFAULT_PROMPT_DAYS,
  max_chars: int = _DEFAULT_PROMPT_CHARS,
  include_index: bool = True,
) -> str:
  """Inject into system prompt so the agent reads its own daily wiki pages."""
  parts: list[str] = []
  budget = max_chars

  if include_index:
    index = read_daily_index().strip()
    if index:
      chunk = index[: min(900, budget // 3)]
      parts.append(chunk)
      budget -= len(chunk)

  today = date.today()
  # Today gets the largest share; older days get less.
  day_budgets: list[tuple[date, int]] = []
  for i in range(days):
    d = today - timedelta(days=i)
    if i == 0:
      day_budgets.append((d, min(2000, budget // 2)))
    elif i < 3:
      day_budgets.append((d, min(600, budget // 8)))
    else:
      day_budgets.append((d, min(350, budget // 12)))

  body_parts: list[str] = []
  for d, cap in day_budgets:
    if budget <= 0 or cap <= 0:
      break
    text = read_daily_memory(d).strip()
    header = _default_header(d).strip()
    if not text or text == header:
      continue
    use = min(cap, budget, len(text))
    excerpt = text if use >= len(text) else text[:use] + "\n[...truncated...]"
    body_parts.append(f"### {_date_key(d)} (`memory/{_date_key(d)}.md`)\n{excerpt}")
    budget -= use

  if not parts and not body_parts:
    return ""

  out = [
    "# Daily memory (read your own journal — Hermes wiki pages)",
    "",
    "You wrote these logs. Use them for continuity; call `read_daily_memory` / `list_daily_memory` if you need a full day.",
    "",
  ]
  if parts:
    out.append(parts[0])
    out.append("")
  if body_parts:
    out.append("## Recent pages\n")
    out.extend(body_parts)
  return "\n".join(out).strip()


def prune_old_daily_files(*, keep_days: int = 30) -> dict[str, Any]:
  if keep_days < 7:
    keep_days = 7
  cutoff = date.today() - timedelta(days=keep_days)
  removed: list[str] = []
  for path in daily_memory_dir().glob("*.md"):
    m = re.match(r"^(\d{4}-\d{2}-\d{2})\.md$", path.name)
    if not m:
      continue
    try:
      file_date = date.fromisoformat(m.group(1))
    except ValueError:
      continue
    if file_date < cutoff:
      try:
        path.unlink()
        removed.append(path.name)
      except OSError:
        pass
  return {"ok": True, "removed": removed, "keepDays": keep_days}
