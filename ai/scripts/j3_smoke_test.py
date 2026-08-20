#!/usr/bin/env python3
"""Comprehensive op助手 API smoke test (run on device or PC against BASE URL)."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

BASE = os.environ.get("AID_BASE", "http://127.0.0.1:5090").rstrip("/")
TIMEOUT = float(os.environ.get("AID_TIMEOUT", "20"))


def req(method: str, path: str, body: dict | None = None, *, timeout: float | None = None) -> tuple[int, Any]:
  url = f"{BASE}{path}"
  data = json.dumps(body).encode() if body is not None else None
  headers = {"Content-Type": "application/json"} if data is not None else {}
  request = urllib.request.Request(url, data=data, headers=headers, method=method)
  try:
    with urllib.request.urlopen(request, timeout=timeout or TIMEOUT) as resp:
      raw = resp.read().decode("utf-8", errors="replace")
      try:
        return resp.status, json.loads(raw)
      except json.JSONDecodeError:
        return resp.status, raw[:500]
  except urllib.error.HTTPError as e:
    raw = e.read().decode("utf-8", errors="replace")
    try:
      return e.code, json.loads(raw)
    except json.JSONDecodeError:
      return e.code, raw[:500]


def get(path: str, **kw) -> tuple[int, Any]:
  return req("GET", path, **kw)


def post(path: str, body: dict, **kw) -> tuple[int, Any]:
  return req("POST", path, body, **kw)


def check(name: str, ok: bool, detail: str = "") -> None:
  mark = "PASS" if ok else "FAIL"
  line = f"[{mark}] {name}"
  if detail:
    line += f" — {detail}"
  print(line)
  if not ok:
    FAILURES.append(f"{name}: {detail}")


FAILURES: list[str] = []


def main() -> int:
  print(f"aid smoke @ {BASE}\n")

  code, data = get("/api/ai/status")
  check("status", code == 200 and isinstance(data, dict) and data.get("ok") is True, f"http={code}")

  code, data = get("/api/ai/bootstrap?lite=1")
  check(
    "bootstrap",
    code == 200 and data.get("ok") and isinstance(data.get("providers"), list),
    f"providers={len(data.get('providers') or [])} embed={len(data.get('embeddingProviders') or [])}",
  )
  providers = data.get("providers") or []
  check("bootstrap siliconflow", "siliconflow" in providers, "present" if "siliconflow" in providers else "missing")

  code, data = get("/api/ai/config")
  check("config", code == 200 and data.get("ok"), f"configured={data.get('config', {}).get('configured')}")

  code, data = get("/api/ai/providers")
  check("providers", code == 200 and data.get("ok"), "")

  code, data = get("/api/ai/rag")
  check(
    "rag list",
    code == 200 and data.get("ok"),
    f"docs={data.get('count')} chunks={data.get('vector_chunks')} limits={data.get('limits')}",
  )

  code, data = get("/api/ai/rag?job=1")
  check(
    "rag job poll",
    code == 200 and data.get("ok") and "running" in data,
    f"running={data.get('running')} status={data.get('status')}",
  )

  code, data = get("/api/ai/memory")
  check("memory", code == 200 and data.get("ok"), f"notes={len(data.get('notes') or [])}")

  code, data = get("/api/ai/skills")
  check("skills", code == 200 and data.get("ok"), f"count={len(data.get('skills') or [])}")

  code, data = get("/api/ai/tools")
  check("tools meta", code == 200 and data.get("ok"), f"tools={len(data.get('tools') or [])}")

  code, data = get("/api/ai/sessions")
  check("sessions", code == 200 and data.get("ok"), f"count={len(data.get('sessions') or [])}")

  code, data = get("/api/ai/scheduler")
  check("scheduler", code == 200 and data.get("ok"), "")

  code, data = get("/api/ai/usage")
  check("usage", code == 200 and data.get("ok"), "")

  code, data = get("/api/ai/fork/detect")
  check("fork detect", code == 200 and data.get("ok"), data.get("fork") or data.get("profile") or "")

  code, data = get("/api/ai/workflows")
  check("workflows", code == 200 and data.get("ok"), "")

  code, data = get("/api/ai/notifications")
  check("notifications", code == 200 and data.get("ok"), "")

  code, data = get("/api/ai/package/version")
  check("package version", code == 200 and data.get("ok"), data.get("version") or "")

  code, data = get("/api/ai/dev-cache")
  check("dev-cache", code == 200 and data.get("ok"), "")

  code, data = get("/api/ai/toolsets")
  check("toolsets", code == 200 and data.get("ok"), "")

  code, data = get("/api/ai/workspace")
  check("workspace", code == 200 and data.get("ok"), "")

  code, data = get("/api/ai/platform/workspace-health")
  check("workspace-health", code == 200 and data.get("ok"), "")

  code, data = get("/api/ai/consumer/lexicon")
  check("consumer lexicon", code == 200 and data.get("ok"), "")

  code, data = get("/api/ai/issues")
  check("issues", code == 200 and data.get("ok"), "")

  code, data = get("/api/ai/publish")
  check("publish", code == 200 and data.get("ok"), "")

  code, data = get("/api/ai/sessions/search?q=hello")
  check("sessions search", code == 200 and data.get("ok"), f"hits={len(data.get('hits') or [])}")

  code, data = get("/api/ai/sessions/search?q=it's")
  check("sessions search quote", code == 200 and data.get("ok") is not False, data.get("error") or "ok")

  code, data = get("/api/ai/sync/schema")
  check("sync schema", code == 200 and data.get("ok"), "")

  # RAG job start should return started + pollable running flag (no full reindex wait)
  code, data = post("/api/ai/rag", {"background": True, "operation": "reindex"})
  if code == 200 and data.get("ok") and data.get("started"):
    check("rag reindex start", True, f"jobId={data.get('jobId')}")
    code2, poll = get("/api/ai/rag?job=1")
    check(
      "rag reindex poll shape",
      code2 == 200 and poll.get("ok") and "running" in poll,
      f"running={poll.get('running')}",
    )
  elif data.get("error") and "已有任务" in str(data.get("error")):
    check("rag reindex start", True, "job already running")
  else:
    check("rag reindex start", False, str(data)[:200])

  # Import sanity on device python
  if os.environ.get("AID_IMPORT_CHECK") == "1":
    try:
      import ai.tools.domains.core.rag_jobs as rj
      import ai.tools.domains.core.rag_store as rs
      import ai.tools.domains.core.rag_vectors as rv

      from ai.common.rag_config import rag_max_chunks

      check("import rag_jobs", hasattr(rj, "job_poll_view"), "")
      check("rag_max_chunks", rag_max_chunks() >= 100_000, f"rag_max_chunks={rag_max_chunks()}")
    except Exception as e:
      check("import rag modules", False, str(e))

  print()
  if FAILURES:
    print(f"FAILED {len(FAILURES)}:")
    for f in FAILURES:
      print(" -", f)
    return 1
  print("ALL PASSED")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
