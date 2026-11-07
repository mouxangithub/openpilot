"""
Tool domain index — maps builtin agents to tool modules.

Physical packages live under tools/domains/<name>/; tools/*.py shims re-export for compatibility.
"""

from __future__ import annotations

from ai.tools.domains import can, cloud, core, devops, media, platform, secoc, tune, vehicle

DOMAIN_MODULES: dict[str, list[str]] = {
  "core": list(core.MODULES) + ["ai.tools.agent_tools", "ai.tools.diagnostics_tools"],
  "tune": list(tune.MODULES),
  "vehicle": list(vehicle.MODULES),
  "can": list(can.MODULES) + ["ai.tools.domains.vehicle.adaptation", "ai.tools.domains.vehicle.fingerprint_lib"],
  "secoc": list(secoc.MODULES),
  "devops": list(devops.MODULES),
  "cloud": list(cloud.MODULES),
  "platform": list(platform.MODULES),
  "media": list(media.MODULES),
  "pc": list(devops.MODULES),  # pc_dev_tools lives in devops domain
}

AGENT_DOMAINS: dict[str, list[str]] = {
  "triage": ["core", "tune", "secoc"],
  "tune": ["tune"],
  "route": ["media", "tune"],
  "adapt": ["can", "tune", "vehicle"],
  "secoc": ["secoc", "tune"],
  "devops": ["devops"],
  "cloud": ["cloud"],
  "pc": ["pc", "media"],
}


def domain_module_names(domain: str) -> list[str]:
  return list(DOMAIN_MODULES.get(domain, ()))
