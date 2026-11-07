#!/usr/bin/env python3
"""GitHub Actions: rule-based safe squash merge only (no LLM review)."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

LABEL_SAFE_MERGE = "ai-safe-merge"
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


def _api(method: str, path: str, token: str, body: dict | None = None) -> Any:
  url = f"https://api.github.com{path}"
  data = None
  headers = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {token}",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "op-assistant-ai-pr-safe-merge",
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
  if LABEL_SAFE_MERGE not in set(labels):
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
    return 1
  owner, name = repo.split("/", 1)
  kind = _repo_kind()

  labels_data = _api("GET", f"/repos/{owner}/{name}/issues/{pr_number}/labels", token)
  labels = [x.get("name") for x in labels_data] if isinstance(labels_data, list) else []
  if LABEL_SAFE_MERGE not in labels:
    print(f"skip: no {LABEL_SAFE_MERGE} label")
    return 0

  files_data = _api("GET", f"/repos/{owner}/{name}/pulls/{pr_number}/files?per_page=100", token)
  files = files_data if isinstance(files_data, list) else []

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

  mergeable = pr.get("mergeable")
  if mergeable is False:
    print("skip merge: conflicts")
    return 0

  merge = _api(
    "PUT",
    f"/repos/{owner}/{name}/pulls/{pr_number}/merge",
    token,
    body={"merge_method": "squash", "commit_title": (pr.get("title") or "")[:250]},
  )
  if isinstance(merge, dict) and merge.get("merged"):
    print("merged OK", merge.get("sha"))
    return 0
  print("merge failed:", merge, file=sys.stderr)
  return 1


if __name__ == "__main__":
  raise SystemExit(main())
