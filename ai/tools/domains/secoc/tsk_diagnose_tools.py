"""Structured TSK / SecOC failure diagnostics for op助手."""

from __future__ import annotations

from typing import Any

from ai.tsk.guidance import enrich_failure_response, matcher_next_steps


def tsk_diagnose_failure(params=None) -> dict[str, Any]:
  """Return structured TSK pipeline status, issues, and next steps."""
  try:
    from ai.tsk import service as tsk_service
    from openpilot.common.params import Params
  except Exception as e:
    return {"ok": False, "error": str(e)}

  params = params or Params()
  status = tsk_service.get_summary()
  key_installed = bool(status.get("secoc_key_installed"))
  issues: list[str] = []
  if not key_installed:
    issues.append("secoc_key_missing")
  can = status.get("can") or {}
  df = status.get("dataflash") or {}
  if can.get("status") == "running":
    issues.append("can_job_running")
  if df.get("status") == "running":
    issues.append("dataflash_job_running")
  if can.get("status") == "failed":
    issues.append("can_job_failed")
  if df.get("status") == "failed":
    issues.append("dataflash_job_failed")

  match = status.get("match") or status.get("matcher") or {}
  next_steps = matcher_next_steps(match) if match else []
  enriched = enrich_failure_response(match) if match.get("status") and match.get("status") != "found" else {}

  return {
    "ok": True,
    "status": status,
    "issues": issues,
    "healthy": not issues and key_installed,
    "match_status": match.get("status"),
    "next_steps": next_steps or enriched.get("next_steps") or [],
    "debug": enriched.get("debug"),
    "skill": "secoc-toyota",
    "workflow": "secoc_tsk",
    "doc": "ai/docs/TSK_AND_AID.md",
  }
