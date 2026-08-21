#!/usr/bin/env python3
"""Rewrite legacy ai.* root imports to canonical layered paths."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (old_module_suffix, new_module_path) — order matters for longer names first
REPLACEMENTS: list[tuple[str, str]] = [
  ("ai.cabana_replay_util", "ai.services.cabana.replay_util"),
  ("ai.cabana_routes_lite", "ai.services.cabana.routes_lite"),
  ("ai.session_compaction", "ai.core.chat.compaction"),
  ("ai.content_sanitize", "ai.core.chat.sanitize"),
  ("ai.evolution_pipeline", "ai.core.runtime.evolution_pipeline"),
  ("ai.model_accounts", "ai.core.llm.model_accounts"),
  ("ai.workspace_store", "ai.core.wspace.store"),
  ("ai.command_queue", "ai.core.chat.command_queue"),
  ("ai.sync_protocol", "ai.core.sync.protocol"),
  ("ai.cabana", "ai.services.cabana.app"),
  ("ai.chat_runner", "ai.core.chat.runner"),
  ("ai.model_router", "ai.core.llm.model_router"),
  ("ai.panda_routes", "ai.services.panda.routes"),
  ("ai.device_trust", "ai.core.sync.device_trust"),
  ("ai.sidecar_hub", "ai.core.runtime.sidecar_hub"),
  ("ai.timezone_util", "ai.infra.timezone"),
  ("ai.version_info", "ai.infra.version"),
  ("ai.tsk_routes", "ai.services.tsk.routes"),
  ("ai.chat_jobs", "ai.core.chat.jobs"),
  ("ai.usage_log", "ai.core.llm.usage"),
  ("ai.heartbeat", "ai.core.runtime.heartbeat"),
  ("ai.sync_hub", "ai.core.sync.hub"),
  ("ai.embedding", "ai.core.llm.embedding"),
  ("ai.web_auth", "ai.infra.auth.web"),
  ("ai.persona", "ai.core.wspace.persona"),
  ("ai.client", "ai.core.llm.client"),
]

SKIP_DIRS = {"__pycache__", ".git", "node_modules", "vendor"}
SKIP_FILES = {"rewrite_imports.py", "arch_migrate.py"}


def rewrite_text(text: str) -> tuple[str, int]:
  count = 0
  for old, new in REPLACEMENTS:
    if old == new:
      continue
    pattern = re.compile(rf"\b{re.escape(old)}\b")
    new_text, n = pattern.subn(new, text)
    if n:
      count += n
      text = new_text
  return text, count


def main() -> int:
  total_files = 0
  total_repls = 0
  for path in sorted(ROOT.rglob("*.py")):
    if any(p in SKIP_DIRS for p in path.parts):
      continue
    if path.name in SKIP_FILES:
      continue
    if path.parent == ROOT and path.name in {
      "client.py", "model_accounts.py", "model_router.py", "embedding.py",
      "usage_log.py", "chat_runner.py", "chat_jobs.py", "session_compaction.py",
      "command_queue.py", "content_sanitize.py", "sync_hub.py", "sync_protocol.py",
      "device_trust.py", "workspace_store.py", "persona.py", "heartbeat.py",
      "evolution_pipeline.py", "sidecar_hub.py", "web_auth.py", "timezone_util.py",
      "version_info.py", "cabana.py", "cabana_replay_util.py", "cabana_routes_lite.py",
      "tsk_routes.py", "panda_routes.py",
    }:
      continue
    original = path.read_text(encoding="utf-8")
    updated, n = rewrite_text(original)
    if n:
      path.write_text(updated, encoding="utf-8")
      print(f"  {n:3d}  {path.relative_to(ROOT)}")
      total_files += 1
      total_repls += n
  print(f"\nupdated {total_files} files, {total_repls} replacements")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
