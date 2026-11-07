#!/usr/bin/env python3
"""GitHub Actions: AI PR review + optional safe auto-merge for op助手 labeled PRs."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

LABEL_AUTO_REVIEW = "ai-auto-review"
LABEL_SAFE_MERGE = "ai-safe-merge"
LABEL_AUTO_FIX = "ai-auto-fix"
MAX_LINES_OPENPILOT = 500
MAX_LINES_ASSISTANT = 1000

OPENPILOT_MERGE_ALLOW = ("ai/", "docs/", ".github/")
OPENPILOT_MERGE_BLOCK = (
  "selfdrive/",
  "panda/",
  "opendbc/safety/",
  "opendbc/car/",
  "cereal/",
  "common/params_keys.h",
)

DEFAULT_ENDPOINTS = {
  "opencode-zen": "https://opencode.ai/zen/v1",
  "opencode-go": "https://opencode.ai/zen/go/v1",
  "deepseek": "https://api.deepseek.com",
  "bigmodel": "https://open.bigmodel.cn/api/paas/v4",
  "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "mimo": "https://api.xiaomimimo.com/v1",
  "minimax": "https://api.minimaxi.com/v1",
  "openrouter": "https://openrouter.ai/api/v1",
  "openai": "https://api.openai.com/v1",
  "kimi": "https://api.moonshot.cn/v1",
  "siliconflow": "https://api.siliconflow.cn/v1",
}

OPTIONAL_BASE_URL_PROVIDERS = frozenset({"qwen", "minimax", "mimo", "bigmodel"})


def _env(name: str, default: str = "") -> str:
  return (os.environ.get(name) or default).strip()


def _repo_kind() -> str:
  kind = _env("AI_REPO_KIND").lower()
  if kind in ("assistant", "ai"):
    return "assistant"
  repo = _env("GITHUB_REPOSITORY", "").lower()
  if repo.endswith("/ai"):
    return "assistant"
  return "openpilot"


def _github_ai_config() -> dict[str, str]:
  provider = _env("AI_PROVIDER", "opencode-zen")
  if provider == "zhipu":
    provider = "bigmodel"
  return {
    "provider": provider,
    "model": _env("AI_MODEL", "deepseek-v4-flash"),
    "api_key": _env("AI_API_KEY"),
    "base_url": _env("AI_BASE_URL"),
    "temperature": _env("AI_TEMPERATURE", "0.3"),
  }


def _chat_endpoint(cfg: dict[str, str]) -> str:
  provider = cfg["provider"]
  base_url = cfg["base_url"]
  if provider == "custom":
    return base_url.rstrip("/")
  if provider in OPTIONAL_BASE_URL_PROVIDERS and base_url:
    return base_url.rstrip("/")
  return DEFAULT_ENDPOINTS.get(provider, DEFAULT_ENDPOINTS["opencode-zen"])


def _http_json(method: str, url: str, headers: dict[str, str], body: dict | None = None, timeout: int = 90) -> Any:
  data = json.dumps(body).encode("utf-8") if body is not None else None
  if body is not None:
    headers = {**headers, "Content-Type": "application/json"}
  req = urllib.request.Request(url, data=data, headers=headers, method=method)
  try:
    with urllib.request.urlopen(req, timeout=timeout) as resp:
      raw = resp.read().decode("utf-8")
      return json.loads(raw) if raw else {}
  except urllib.error.HTTPError as e:
    try:
      err_body = e.read().decode("utf-8")
      return json.loads(err_body) if err_body else {"error": str(e)}
    except Exception:
      return {"error": str(e)}


def _diff_excerpt(files: list[dict], max_chars: int = 24000) -> str:
  chunks: list[str] = []
  used = 0
  for f in files[:25]:
    patch = (f.get("patch") or "").strip()
    if not patch:
      continue
    header = f"### {f.get('filename')} (+{f.get('additions', 0)}/-{f.get('deletions', 0)})\n"
    block = header + patch + "\n"
    if used + len(block) > max_chars:
      remain = max_chars - used
      if remain > 200:
        chunks.append(block[:remain] + "\n... (truncated)\n")
      break
    chunks.append(block)
    used += len(block)
  return "\n".join(chunks)


def _build_rules_review_body(
  pull: dict,
  files: list[dict],
  analysis: dict,
  *,
  kind: str,
  llm_error: str = "",
) -> str:
  lines = [
    "## op助手 AI 审阅",
    "",
    "**模式**: 规则摘要（未配置 GitHub `AI_API_KEY` 或 LLM 调用失败）",
    f"**仓库**: `{_env('GITHUB_REPOSITORY')}` ({kind})",
    f"**标题**: {pull.get('title', '')}",
    f"**分支**: `{(pull.get('head') or {}).get('ref')}` → `{(pull.get('base') or {}).get('ref')}`",
    f"**变更**: {len(files)} 文件, +{analysis.get('total_lines', 0)} 行量级",
    "",
    "### 文件",
  ]
  for f in files[:40]:
    lines.append(
      f"- `{f.get('filename')}` (+{f.get('additions', 0)}/-{f.get('deletions', 0)})"
    )
  if analysis.get("blocked_paths"):
    lines.extend(["", "### 路径门控", f"blocked: `{analysis['blocked_paths'][:8]}`"])
  if llm_error:
    lines.extend(["", f"_LLM 回退原因: {llm_error}_"])
  lines.extend([
    "",
    "### 结论",
    "- 自动摘要；请在 PC 查看完整 diff。",
    f"- 自动合并资格: **{'是' if analysis.get('auto_merge_eligible') else '否'}**（需 `{LABEL_SAFE_MERGE}` + CI 绿）",
  ])
  return "\n".join(lines)


def _llm_review_body(pull: dict, files: list[dict], analysis: dict, *, kind: str) -> tuple[str, str]:
  cfg = _github_ai_config()
  if not cfg["api_key"]:
    return _build_rules_review_body(pull, files, analysis, kind=kind), "rules"

  diff_text = _diff_excerpt(files)
  system = (
    "你是 op助手 PR 审阅机器人。用简体中文输出 Markdown。"
    "关注：正确性、回归风险、安全（尤其车控/安全相关路径）、测试缺口。"
    "结尾给出：风险等级(低/中/高)、是否建议合并、需人工关注的点。"
  )
  user = "\n".join([
    f"仓库类型: {kind}",
    f"PR 标题: {pull.get('title', '')}",
    f"分支: {(pull.get('head') or {}).get('ref')} → {(pull.get('base') or {}).get('ref')}",
    f"自动合并资格(规则): {analysis.get('auto_merge_eligible')}",
    "",
    "PR 描述:",
    (pull.get("body") or "")[:4000],
    "",
    "Diff:",
    diff_text or "(no patch in API response)",
  ])

  endpoint = _chat_endpoint(cfg)
  try:
    temp = float(cfg["temperature"] or "0.3")
  except ValueError:
    temp = 0.3

  resp = _http_json(
    "POST",
    f"{endpoint}/chat/completions",
    headers={"Authorization": f"Bearer {cfg['api_key']}"},
    body={
      "model": cfg["model"],
      "messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
      ],
      "temperature": temp,
      "max_tokens": 2048,
    },
  )
  choices = resp.get("choices") if isinstance(resp, dict) else None
  if choices:
    content = ((choices[0] or {}).get("message") or {}).get("content") or ""
    if content.strip():
      header = "\n".join([
        "## op助手 AI 审阅",
        "",
        f"**模型**: `{cfg['provider']}` / `{cfg['model']}`（GitHub Actions 配置）",
        f"**仓库**: `{_env('GITHUB_REPOSITORY')}` ({kind})",
        "",
      ])
      footer = "\n".join([
        "",
        "---",
        f"规则门控：自动合并资格 **{'是' if analysis.get('auto_merge_eligible') else '否'}**",
      ])
      return header + content.strip() + footer, "llm"

  err = resp.get("error") or resp.get("message") or resp
  print(f"LLM review failed, fallback to rules: {err}", file=sys.stderr)
  return _build_rules_review_body(pull, files, analysis, kind=kind, llm_error=str(err)[:200]), "rules"


def _build_review_body(pull: dict, files: list[dict], analysis: dict, *, kind: str) -> tuple[str, str]:
  return _llm_review_body(pull, files, analysis, kind=kind)


def _api(method: str, path: str, token: str, body: dict | None = None) -> Any:
  url = f"https://api.github.com{path}"
  data = None
  headers = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {token}",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "op-assistant-ai-pr-review",
  }
  if body is not None:
    data = json.dumps(body).encode("utf-8")
    headers["Content-Type"] = "application/json"
  req = urllib.request.Request(url, data=data, headers=headers, method=method)
  try:
    with urllib.request.urlopen(req, timeout=60) as resp:
      raw = resp.read().decode("utf-8")
      return json.loads(raw) if raw else {}
  except urllib.error.HTTPError as e:
    try:
      err_body = e.read().decode("utf-8")
      return json.loads(err_body) if err_body else {"message": str(e)}
    except Exception:
      return {"message": str(e)}


def _path_allowed(filename: str, *, kind: str) -> bool:
  fn = (filename or "").replace("\\", "/")
  if kind == "openpilot":
    for b in OPENPILOT_MERGE_BLOCK:
      if fn.startswith(b) or f"/{b}" in fn:
        return False
    return any(fn.startswith(p) for p in OPENPILOT_MERGE_ALLOW)
  return True


def _analyze_files(files: list[dict], *, kind: str) -> dict[str, Any]:
  names = [str(f.get("filename") or "") for f in files]
  additions = sum(int(f.get("additions") or 0) for f in files)
  deletions = sum(int(f.get("deletions") or 0) for f in files)
  total = additions + deletions
  blocked = [n for n in names if not _path_allowed(n, kind=kind)]
  max_lines = MAX_LINES_ASSISTANT if kind == "assistant" else MAX_LINES_OPENPILOT
  eligible = not blocked and total <= max_lines and len(names) > 0
  return {
    "files": names,
    "total_lines": total,
    "blocked_paths": blocked,
    "auto_merge_eligible": eligible,
  }


def _head_ok(head: str, *, kind: str) -> bool:
  prefixes = ("ai/", "fix/", "web/") if kind == "assistant" else ("ai/",)
  return any(head.startswith(p) for p in prefixes)


def _merge_allowed(pull: dict, files: list[dict], labels: list[str], *, kind: str) -> tuple[bool, str]:
  label_set = set(labels)
  if LABEL_SAFE_MERGE not in label_set:
    return False, f"missing label {LABEL_SAFE_MERGE}"
  head = ((pull.get("head") or {}).get("ref") or "")
  base = ((pull.get("base") or {}).get("ref") or "")
  if not _head_ok(head, kind=kind):
    return False, f"head {head!r} not allowed"
  if kind == "openpilot" and base in ("master-c3", "master", "main"):
    analysis = _analyze_files(files, kind=kind)
    if not analysis["auto_merge_eligible"]:
      return False, f"paths/size not eligible: {analysis.get('blocked_paths', [])[:3]}"
  return True, "ok"


def main() -> int:
  token = _env("GITHUB_TOKEN")
  if not token:
    print("GITHUB_TOKEN missing", file=sys.stderr)
    return 1

  event_path = _env("GITHUB_EVENT_PATH")
  if not event_path or not os.path.isfile(event_path):
    print("GITHUB_EVENT_PATH missing", file=sys.stderr)
    return 1

  with open(event_path, encoding="utf-8") as f:
    event = json.load(f)

  pr = event.get("pull_request") or {}
  pr_number = int(pr.get("number") or 0)
  if not pr_number:
    print("no pull_request in event", file=sys.stderr)
    return 0

  repo = _env("GITHUB_REPOSITORY")
  if "/" not in repo:
    print("invalid GITHUB_REPOSITORY", file=sys.stderr)
    return 1
  owner, name = repo.split("/", 1)
  kind = _repo_kind()

  labels_data = _api("GET", f"/repos/{owner}/{name}/issues/{pr_number}/labels", token)
  labels = [x.get("name") for x in labels_data] if isinstance(labels_data, list) else []
  if LABEL_AUTO_REVIEW not in labels and _env("AI_FORCE_REVIEW") != "1":
    print(f"skip: no {LABEL_AUTO_REVIEW} label")
    return 0

  files_data = _api("GET", f"/repos/{owner}/{name}/pulls/{pr_number}/files?per_page=100", token)
  files = files_data if isinstance(files_data, list) else []
  analysis = _analyze_files(files, kind=kind)

  cfg = _github_ai_config()
  body, review_mode = _build_review_body(pr, files, analysis, kind=kind)
  print(f"review mode: {review_mode} (provider={cfg.get('provider')}, model={cfg.get('model')})")

  review = _api(
    "POST",
    f"/repos/{owner}/{name}/pulls/{pr_number}/reviews",
    token,
    body={"body": body, "event": "COMMENT"},
  )
  if isinstance(review, dict) and review.get("message") and not review.get("id"):
    print("review failed:", review, file=sys.stderr)
    return 1
  print("review posted")

  if _env("AI_AUTO_MERGE", "1") != "1":
    print("AI_AUTO_MERGE disabled")
    return 0

  allowed, reason = _merge_allowed(pr, files, labels, kind=kind)
  if not allowed:
    print(f"skip merge: {reason}")
    return 0

  head_sha = ((pr.get("head") or {}).get("sha") or "")
  if head_sha:
    status = _api("GET", f"/repos/{owner}/{name}/commits/{head_sha}/status", token)
    state = status.get("state") if isinstance(status, dict) else None
    if state and state != "success":
      print(f"skip merge: combined status={state}")
      return 0

  merge = _api(
    "PUT",
    f"/repos/{owner}/{name}/pulls/{pr_number}/merge",
    token,
    body={"merge_method": "squash", "commit_title": pr.get("title", "")[:250]},
  )
  if isinstance(merge, dict) and merge.get("merged"):
    print("merged OK", merge.get("sha"))
    return 0
  print("merge failed:", merge, file=sys.stderr)
  return 1


if __name__ == "__main__":
  raise SystemExit(main())
