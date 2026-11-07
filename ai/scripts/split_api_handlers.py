#!/usr/bin/env python3
"""Split server/handlers/api.py into domain handler modules."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "server" / "handlers" / "api.py"
HANDLERS = ROOT / "server" / "handlers"

SPLITS: dict[str, list[str]] = {
  "chat_handlers.py": [
    "_parse_chat_body", "_prepare_chat_run", "_chat_tools_for_body",
    "api_chat", "api_chat_jobs", "api_chat_job_detail",
  ],
  "config_handlers.py": [
    "api_bootstrap", "api_status", "api_providers",
    "api_get_config", "api_post_config", "api_models", "api_test_connection",
    "api_model_hub_fetch", "api_model_hub_test",
    "api_onboarding_profile", "api_onboarding_complete",
  ],
  "sessions_handlers.py": ["api_sessions", "api_pc_sessions"],
  "memory_handlers.py": ["api_memory", "api_skills"],
  "rag_handlers.py": ["api_rag"],
  "scheduler_handlers.py": ["api_scheduler", "api_write_confirm", "api_write_pending"],
  "dev_handlers.py": ["api_dev_assets", "api_dev_cache", "api_shell", "api_state"],
  "tools_handlers.py": ["api_tools_meta", "api_workflows", "api_tune_passport", "api_tune_compare"],
  "fork_handlers.py": [
    "api_fork_detect", "api_fork_analyze", "api_fork_sync", "api_fork_run_stream",
    "api_integrate_openpilot",
  ],
  "publish_handlers.py": ["api_publish", "api_issues", "api_package_version", "api_package_update"],
  "misc_handlers.py": [
    "api_notifications", "api_adaptation_bundle", "api_usage",
  ],
}

HEADER = '''\
"""API handlers — {title}."""

from ai.server.handlers._api_common import *  # noqa: F403
'''


def extract_functions(src: str) -> dict[str, str]:
  pattern = re.compile(
    r"^((?:async )?def ([a-zA-Z0-9_]+)\([^)]*\)[^:]*:)(.*?)(?=^(?:async )?def |\Z)",
    re.MULTILINE | re.DOTALL,
  )
  out: dict[str, str] = {}
  for m in pattern.finditer(src):
    name = m.group(2)
    out[name] = m.group(0).rstrip() + "\n"
  return out


def main() -> None:
  src = API.read_text(encoding="utf-8")
  funcs = extract_functions(src)

  # common: module docstring + imports + module-level assignments until first def
  first_def = re.search(r"^(?:async )?def ", src, re.MULTILINE)
  common = src[: first_def.start()] if first_def else src
  (HANDLERS / "_api_common.py").write_text(common.rstrip() + "\n", encoding="utf-8")

  assigned: set[str] = set()
  for fname, names in SPLITS.items():
    parts = [HEADER.format(title=fname.replace("_handlers.py", ""))]
    for n in names:
      if n in funcs:
        parts.append(funcs[n])
        assigned.add(n)
      else:
        print(f"warn: missing {n} in api.py")
    (HANDLERS / fname).write_text("\n".join(parts), encoding="utf-8")

  # leftovers stay in api.py shim
  leftovers = [n for n in funcs if n not in assigned]
  shim_lines = [
    '"""Aggregated API handlers (re-exports)."""',
    "from ai.server.handlers._api_common import *  # noqa: F403",
  ]
  for fname in SPLITS:
    mod = fname.replace(".py", "")
    shim_lines.append(f"from ai.server.handlers.{mod} import *  # noqa: F403")
  API.write_text("\n".join(shim_lines) + "\n", encoding="utf-8")
  print("leftover functions:", leftovers)


if __name__ == "__main__":
  main()
