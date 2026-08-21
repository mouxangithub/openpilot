#!/usr/bin/env python3
"""Move tools/*.py into tools/domains/<domain>/ with compatibility shims."""

from __future__ import annotations

import shutil
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "tools"

# filename -> domain folder
DOMAIN_MAP: dict[str, str] = {
  # core
  "mads_diagnostics_tools.py": "core",
  "memory_store.py": "core",
  "memory_vectors.py": "core",
  "memory_protocol.py": "core",
  "daily_memory.py": "core",
  "rag_store.py": "core",
  "rag_seed.py": "core",
  "rag_jobs.py": "core",
  "rag_vectors.py": "core",
  "rag_sync_tools.py": "core",
  "rag_extra_seed.py": "core",
  "secoc_rag.py": "core",
  "wiki_rag.py": "core",
  "secoc_rag_pages.py": "core",
  "wiki_rag_pages.py": "core",
  "comma_docs_rag.py": "core",
  # tune
  "presets.py": "tune",
  "sp_presets.py": "tune",
  "dp_settings.py": "tune",
  "sp_settings.py": "tune",
  "tune_snapshot_store.py": "tune",
  "tune_write_pipeline.py": "tune",
  "tune_regression.py": "tune",
  "tune_passport_store.py": "tune",
  "model_tune_tools.py": "tune",
  "sp_tune_groups.py": "tune",
  "route_scoring_tools.py": "tune",
  "maneuver_tools.py": "tune",
  # vehicle / can
  "vehicle_platform.py": "vehicle",
  "mads_tools.py": "vehicle",
  "car_porting_tools.py": "vehicle",
  "adaptation.py": "vehicle",
  "adaptation_templates.py": "vehicle",
  "adaptation_pr_tools.py": "vehicle",
  "fingerprint_lib.py": "vehicle",
  "cabana_route_tools.py": "can",
  # secoc
  "tsk_tools.py": "secoc",
  "tsk_diagnose_tools.py": "secoc",
  "secoc_lookup.py": "secoc",
  # devops
  "git_tools.py": "devops",
  "git_pr_tools.py": "devops",
  "git_remote_tools.py": "devops",
  "git_repo_context.py": "devops",
  "github_api_client.py": "devops",
  "github_actions_tools.py": "devops",
  "github_runner_tools.py": "devops",
  "branch_tools.py": "devops",
  "ota_tools.py": "devops",
  "devops_tools.py": "devops",
  "pc_dev_tools.py": "devops",
  "dev_ci_tools.py": "devops",
  "dev_cache_tools.py": "devops",
  "dev_assets.py": "devops",
  # cloud
  "konik_connect_tools.py": "cloud",
  "sunnylink_tools.py": "cloud",
  "comma_cloud_tools.py": "cloud",
  # media
  "route_tools.py": "media",
  "route_analysis_tools.py": "media",
  "route_media_tools.py": "media",
  "route_timeline_tools.py": "media",
  "vision_route_tools.py": "media",
  "plotjuggler_tools.py": "media",
  "live_tools.py": "media",
  # platform
  "system_control_tools.py": "platform",
  "system_info_tools.py": "platform",
  "device_hw_tools.py": "platform",
  "device_health_tools.py": "platform",
  "display_device_tools.py": "platform",
  "health_check_tools.py": "platform",
  "network_tools.py": "platform",
  "ssh_tools.py": "platform",
  "notifications.py": "platform",
  "publish_tools.py": "platform",
  "publish_units.py": "platform",
  "platform_backup.py": "platform",
  "platform_extensions.py": "platform",
  "sp_tool_extensions.py": "platform",
  "issue_tools.py": "platform",
  "issue_template_lib.py": "platform",
  "bug_report_tools.py": "platform",
  "scheduler.py": "platform",
  "scheduler_actions.py": "platform",
  "workflows.py": "platform",
  "catalog_builder.py": "platform",
  "model_manager_tools.py": "platform",
  "osm_tools.py": "platform",
  "translation_tools.py": "platform",
  "viz_layout_tools.py": "platform",
  "voice_summary_tools.py": "platform",
  "skill_evolution.py": "platform",
  "skill_learning.py": "platform",
  "skill_evaluation.py": "platform",
  "workspace_enrich.py": "platform",
  "evolution_reflect.py": "platform",
  "panda_flash_tools.py": "platform",
  "op_run.py": "platform",
  "fs_tools.py": "platform",
  "consumer_tools.py": "platform",
  "consumer_wizards.py": "platform",
  "session_store.py": "platform",
  "session_index.py": "platform",
  "audit_store.py": "platform",
  "param_write.py": "platform",
  "params_policy.py": "platform",
  "write_pending.py": "platform",
  "tool_desc_store.py": "platform",
  "tool_ui_meta.py": "platform",
}

KEEP_AT_ROOT = frozenset({
  "agent_tools.py",
  "registry.py",
  "executor.py",
  "extensions.py",
  "toolsets.py",
  "diagnostics_tools.py",  # already shimmed to domains/core
  "__init__.py",
})

SHIM = '''\
"""Compatibility shim — use `{mod}` instead."""

from {mod} import *  # noqa: F403
'''


def ensure_init(domain: str) -> None:
  d = ROOT / "domains" / domain
  d.mkdir(parents=True, exist_ok=True)
  init = d / "__init__.py"
  if not init.exists():
    init.write_text(f'"""Tools domain: {domain}."""\n', encoding="utf-8")


def move_one(name: str, domain: str) -> None:
  src = ROOT / name
  if not src.is_file():
    print(f"skip missing {name}")
    return
  ensure_init(domain)
  dst = ROOT / "domains" / domain / name
  if dst.exists():
    # already migrated
    if src.read_text(encoding="utf-8").startswith('"""Compatibility shim'):
      return
  else:
    shutil.copy2(src, dst)
  mod = f"ai.tools.domains.{domain}.{name[:-3]}"
  src.write_text(SHIM.format(mod=mod), encoding="utf-8")
  print(f"{name} -> domains/{domain}/")


def write_domain_modules() -> None:
  by_domain: dict[str, list[str]] = {}
  for name, domain in DOMAIN_MAP.items():
    mod = f"ai.tools.domains.{domain}.{name[:-3]}"
    by_domain.setdefault(domain, []).append(mod)

  for domain, modules in sorted(by_domain.items()):
    path = ROOT / "domains" / f"{domain}.py"
    lines = [
      f'"""{domain.title()} tools domain."""',
      "",
      "from __future__ import annotations",
      "",
      "MODULES = (",
    ]
    for m in sorted(modules):
      lines.append(f'  "{m}",')
    lines.extend([")", "", '__all__ = ["MODULES"]', ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"updated domains/{domain}.py ({len(modules)} modules)")


def main() -> int:
  for name, domain in sorted(DOMAIN_MAP.items()):
    if name in KEEP_AT_ROOT:
      continue
    move_one(name, domain)
  write_domain_modules()
  print("done")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
