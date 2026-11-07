#!/usr/bin/env python3
"""One-shot architecture migration: move modules + write compatibility shims."""

from __future__ import annotations

import shutil
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (old_relative, new_relative)
MOVES: list[tuple[str, str]] = [
  # core/llm
  ("client.py", "core/llm/client.py"),
  ("model_accounts.py", "core/llm/model_accounts.py"),
  ("model_router.py", "core/llm/model_router.py"),
  ("embedding.py", "core/llm/embedding.py"),
  ("usage_log.py", "core/llm/usage.py"),
  # core/chat
  ("chat_runner.py", "core/chat/runner.py"),
  ("chat_jobs.py", "core/chat/jobs.py"),
  ("session_compaction.py", "core/chat/compaction.py"),
  ("command_queue.py", "core/chat/command_queue.py"),
  ("content_sanitize.py", "core/chat/sanitize.py"),
  # core/sync
  ("sync_hub.py", "core/sync/hub.py"),
  ("sync_protocol.py", "core/sync/protocol.py"),
  ("device_trust.py", "core/sync/device_trust.py"),
  # core/wspace (code); user markdown data in ai/workspace/
  ("workspace_store.py", "core/wspace/store.py"),
  ("persona.py", "core/wspace/persona.py"),
  # core/runtime
  ("heartbeat.py", "core/runtime/heartbeat.py"),
  ("evolution_pipeline.py", "core/runtime/evolution_pipeline.py"),
  ("sidecar_hub.py", "core/runtime/sidecar_hub.py"),
  # infra
  ("web_auth.py", "infra/auth/web.py"),
  ("timezone_util.py", "infra/timezone.py"),
  ("version_info.py", "infra/version.py"),
  # services
  ("cabana.py", "services/cabana/app.py"),
  ("cabana_replay_util.py", "services/cabana/replay_util.py"),
  ("cabana_routes_lite.py", "services/cabana/routes_lite.py"),
  ("tsk_routes.py", "services/tsk/routes.py"),
  ("panda_routes.py", "services/panda/routes.py"),
]

SHIM_TEMPLATE = '''\
"""Compatibility shim — use `{new_mod}` instead."""

from {new_mod} import *  # noqa: F403
'''

MODULE_MAP = {
  "client.py": "ai.core.llm.client",
  "model_accounts.py": "ai.core.llm.model_accounts",
  "model_router.py": "ai.core.llm.model_router",
  "embedding.py": "ai.core.llm.embedding",
  "usage_log.py": "ai.core.llm.usage",
  "chat_runner.py": "ai.core.chat.runner",
  "chat_jobs.py": "ai.core.chat.jobs",
  "session_compaction.py": "ai.core.chat.compaction",
  "command_queue.py": "ai.core.chat.command_queue",
  "content_sanitize.py": "ai.core.chat.sanitize",
  "sync_hub.py": "ai.core.sync.hub",
  "sync_protocol.py": "ai.core.sync.protocol",
  "device_trust.py": "ai.core.sync.device_trust",
  "workspace_store.py": "ai.core.wspace.store",
  "persona.py": "ai.core.wspace.persona",
  "heartbeat.py": "ai.core.runtime.heartbeat",
  "evolution_pipeline.py": "ai.core.runtime.evolution_pipeline",
  "sidecar_hub.py": "ai.core.runtime.sidecar_hub",
  "web_auth.py": "ai.infra.auth.web",
  "timezone_util.py": "ai.infra.timezone",
  "version_info.py": "ai.infra.version",
  "cabana.py": "ai.services.cabana.app",
  "cabana_replay_util.py": "ai.services.cabana.replay_util",
  "cabana_routes_lite.py": "ai.services.cabana.routes_lite",
  "tsk_routes.py": "ai.services.tsk.routes",
  "panda_routes.py": "ai.services.panda.routes",
}


def ensure_pkg(path: Path, doc: str = "") -> None:
  path.mkdir(parents=True, exist_ok=True)
  init = path / "__init__.py"
  if not init.exists():
    init.write_text(f'"""{doc or path.name}."""\n', encoding="utf-8")


def move_and_shim(old_name: str, new_rel: str) -> None:
  old = ROOT / old_name
  new = ROOT / new_rel
  if not old.exists():
    print(f"skip missing {old_name}")
    return
  if new.exists() and new.read_text(encoding="utf-8") != old.read_text(encoding="utf-8"):
    print(f"skip exists {new_rel}")
    return
  ensure_pkg(new.parent)
  shutil.copy2(old, new)
  mod = MODULE_MAP[old_name]
  old.write_text(SHIM_TEMPLATE.format(new_mod=mod), encoding="utf-8")
  print(f"moved {old_name} -> {new_rel}")


def main() -> None:
  for pkg in [
    "core", "core/llm", "core/chat", "core/sync", "core/wspace", "core/runtime",
    "infra", "infra/auth", "infra/config", "infra/safety", "infra/paths", "infra/hardware",
    "services", "services/cabana", "services/tsk", "services/panda", "services/rag",
    "integration",
  ]:
    ensure_pkg(ROOT / pkg)

  # infra re-exports
  (ROOT / "infra/config/__init__.py").write_text(
    '"""Config store — re-exports ai.common."""\nfrom ai.common.config_store import *  # noqa: F403\n',
    encoding="utf-8",
  )
  (ROOT / "infra/safety/__init__.py").write_text(
    '"""Safety — re-exports ai.system.safety."""\nfrom ai.system.safety import *  # noqa: F403\n',
    encoding="utf-8",
  )
  (ROOT / "infra/paths/__init__.py").write_text(
    '"""Paths — re-exports ai.system paths helpers."""\nfrom ai.system.host_env import *  # noqa: F403\nfrom ai.system.paths import *  # noqa: F403\n',
    encoding="utf-8",
  )
  (ROOT / "infra/hardware/__init__.py").write_text(
    '"""Hardware — re-exports ai.system hardware."""\nfrom ai.system.panda_stack import *  # noqa: F403\n',
    encoding="utf-8",
  )

  for old, new in MOVES:
    move_and_shim(old, new)

  # services/cabana public API
  qlog = ROOT / "services/cabana/qlog_finder.py"
  if not qlog.exists():
    qlog.write_text(textwrap.dedent('''\
      """Public qlog/rlog discovery API for tools and tests."""
      from __future__ import annotations
      from pathlib import Path
      from ai.services.cabana.app import _find_qlogs, _find_rlogs

      def find_qlogs(route_dir: Path) -> list[Path]:
        return _find_qlogs(route_dir)

      def find_rlogs(route_dir: Path) -> list[Path]:
        return _find_rlogs(route_dir)
    '''), encoding="utf-8")

  cab_init = ROOT / "services/cabana/__init__.py"
  cab_init.write_text(textwrap.dedent('''\
    """Cabana CAN visualization service."""
    from ai.services.cabana.app import register_routes
    from ai.services.cabana.qlog_finder import find_qlogs, find_rlogs

    __all__ = ["register_routes", "find_qlogs", "find_rlogs"]
  '''), encoding="utf-8")

  (ROOT / "services/tsk/__init__.py").write_text(
    'from ai.services.tsk.routes import init_tsk_for_aid\n__all__ = ["init_tsk_for_aid"]\n',
    encoding="utf-8",
  )
  (ROOT / "services/panda/__init__.py").write_text(
    'from ai.services.panda.routes import register_routes\n__all__ = ["register_routes"]\n',
    encoding="utf-8",
  )

  print("done")


if __name__ == "__main__":
  main()
