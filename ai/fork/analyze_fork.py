"""AI-driven fork analysis — reads the actual openpilot tree, no fixed profile list."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai.fork.fork_emit import EmitFn, emit_event, emit_phase, stream_llm_completion
from ai.fork.repo_scan import compact_scan_for_api, derive_fork_identity, scan_openpilot_repo

AI_DIR = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = AI_DIR / "data" / "fork_analysis"
ANALYSIS_FILE = ANALYSIS_DIR / "latest.json"

EXTRA_READ_LIMIT = 6000


def _read_extra_files(root: Path, scan: dict[str, Any]) -> list[dict[str, str]]:
  """Pull a few high-signal files for the model to read."""
  candidates: list[str] = []
  if scan.get("readme_path"):
    candidates.append(scan["readme_path"])
  candidates.extend(scan.get("launch_scripts") or [])
  candidates.extend(scan.get("root_files") or [])
  for mod in (scan.get("settings_modules") or [])[:6]:
    candidates.append(mod["path"])

  out: list[dict[str, str]] = []
  seen: set[str] = set()
  for rel in candidates:
    if rel in seen:
      continue
    seen.add(rel)
    path = root / rel
    if not path.is_file():
      continue
    try:
      if path.stat().st_size > 250_000:
        continue
      text = path.read_text(encoding="utf-8", errors="replace")[:EXTRA_READ_LIMIT]
    except OSError:
      continue
    out.append({"path": rel, "content": text})
    if len(out) >= 10:
      break
  return out


def load_cached_analysis(*, git_commit: str | None = None) -> dict[str, Any] | None:
  if not ANALYSIS_FILE.is_file():
    return None
  try:
    data = json.loads(ANALYSIS_FILE.read_text(encoding="utf-8"))
  except (OSError, json.JSONDecodeError):
    return None
  if git_commit and data.get("git_commit") != git_commit:
    return None
  return data


def save_analysis(payload: dict[str, Any]) -> None:
  ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
  ANALYSIS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_analysis_json(text: str) -> dict[str, Any] | None:
  text = text.strip()
  fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
  if fence:
    text = fence.group(1)
  else:
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
      text = text[start : end + 1]
  try:
    return json.loads(text)
  except json.JSONDecodeError:
    return None


async def analyze_fork_with_ai(
  params: Any,
  root: Path,
  *,
  force: bool = False,
  emit: EmitFn = None,
) -> dict[str, Any]:
  """Let configured model read scan + file excerpts and infer fork characteristics."""
  from ai.client import load_config_from_params

  await emit_phase(emit, "scan", "active")
  scan = scan_openpilot_repo(root)
  commit = scan.get("git_commit") or "unknown"
  identity = derive_fork_identity(scan)
  compact = compact_scan_for_api(scan)
  await emit_phase(emit, "scan", "done", detail={"git_commit": commit, "fork_id": identity.get("fork_id")})
  await emit_event(emit, {"type": "scan", "data": compact})

  await emit_phase(emit, "cache", "active")
  if not force:
    cached = load_cached_analysis(git_commit=commit)
    if cached and cached.get("analysis"):
      await emit_phase(emit, "cache", "done", message="命中缓存，跳过 LLM 分析")
      await emit_event(emit, {"type": "analysis", "cached": True, "data": cached["analysis"]})
      return {
        "ok": True,
        "cached": True,
        "git_commit": commit,
        "identity": identity,
        "scan": compact,
        "analysis": cached["analysis"],
      }
  await emit_phase(emit, "cache", "done", message="需要运行 AI 分析" if not force else "已强制重新分析")

  config = load_config_from_params(params)
  if not config.is_configured:
    err = config.configuration_error or "请先配置模型 API（设置 → 模型）"
    await emit_event(emit, {"type": "error", "error": err})
    return {
      "ok": False,
      "error": err,
      "identity": identity,
      "scan": compact,
    }

  await emit_phase(emit, "read_files", "active")
  file_reads = _read_extra_files(root, scan)
  await emit_phase(
    emit,
    "read_files",
    "done",
    message=f"已读取 {len(file_reads)} 个文件",
    detail=[f["path"] for f in file_reads],
  )
  prompt_scan = compact_scan_for_api(scan)
  settings_excerpts = [
    {"path": m["path"], "excerpt": m.get("excerpt", "")[:1500]}
    for m in (scan.get("settings_modules") or [])[:8]
  ]

  system = (
    "你是 openpilot 社区 fork 分析助手。根据仓库扫描结果与文件摘录，"
    "推断这是哪个社区分支、有哪些调参体系与集成要点。"
    "不要假设只有某几个固定 fork；根据证据命名。"
    "禁止建议直接控车或绕过安全机制。输出必须是合法 JSON。"
  )
  user = f"""请分析下列 openpilot 安装树，返回 JSON（不要 markdown 包裹以外的说明）：

```json
{{
  "fork_name": "人类可读名称",
  "fork_identity": "短 slug，如 owner/repo 或社区名",
  "community": "社区/作者描述",
  "confidence": "high|medium|low",
  "summary": "2-4 句概述",
  "distinctive_features": ["..."],
  "param_prefixes": ["调参相关前缀，从 params_keys 推断"],
  "settings_sources": ["相对路径"],
  "recommended_skills": ["建议 op助手 启用的技能 id，若未知可留空数组"],
  "integration_notes": ["与 op助手 集成注意事项"],
  "evidence": ["判断依据，引用具体路径或 remote"]
}}
```

## 仓库扫描
```json
{json.dumps(prompt_scan, ensure_ascii=False, indent=2)[:10000]}
```

## settings ITEMS 摘录
```json
{json.dumps(settings_excerpts, ensure_ascii=False)[:8000]}
```

## 其他文件摘录
```json
{json.dumps(file_reads, ensure_ascii=False)[:12000]}
```
"""

  messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
  text, _reasoning, err = await stream_llm_completion(
    config,
    messages,
    emit=emit,
    phase_id="llm_analyze",
    timeout_total=240,
  )
  if err:
    return {"ok": False, "error": err, "identity": identity, "scan": compact}

  await emit_phase(emit, "parse", "active")
  analysis = _parse_analysis_json(text)
  if not analysis:
    parse_err = "模型返回无法解析为 JSON"
    await emit_phase(emit, "parse", "error", message=parse_err)
    await emit_event(emit, {"type": "error", "error": parse_err, "raw_preview": text[:2000]})
    return {
      "ok": False,
      "error": parse_err,
      "raw_preview": text[:2000],
      "identity": identity,
      "scan": compact,
    }
  await emit_phase(emit, "parse", "done")
  await emit_event(emit, {"type": "analysis", "cached": False, "data": analysis})

  payload = {
    "git_commit": commit,
    "analyzed_at": datetime.now(timezone.utc).isoformat(),
    "model": config.model,
    "provider": config.provider,
    "identity": identity,
    "scan_summary": prompt_scan,
    "analysis": analysis,
  }
  await emit_phase(emit, "save_analysis", "active")
  save_analysis(payload)
  await emit_phase(emit, "save_analysis", "done")

  return {
    "ok": True,
    "cached": False,
    "git_commit": commit,
    "identity": identity,
    "scan": compact,
    "analysis": analysis,
  }
