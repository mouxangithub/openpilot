"""Profile sync manifest — cross-device preference merge (WorkBuddy s12)."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from openpilot.common.params import Params

from ai.common.storage import read_param, write_param
from ai.tools.deferred_loading import deferred_loading_enabled
from ai.tools.result_externalize import externalize_enabled, threshold_bytes
from ai.common.model_tier import normalize_tier
from ai.agents.config import agents_enabled_payload

MANIFEST_KEY = "ai_profile_sync_manifest"
_SYNC_SECTIONS = ("harness", "agents", "vehicle_profile", "model_tier")


def _hash_blob(data: Any) -> str:
  raw = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
  return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_manifest(params: Params | None = None) -> dict[str, Any]:
  p = params or Params()
  harness = {
    "deferredTools": deferred_loading_enabled(p),
    "externalizeResults": externalize_enabled(p),
    "externalizeThreshold": threshold_bytes(p),
    "modelTier": normalize_tier(str(read_param(p, "ai_model_tier", "auto") or "auto")),
  }
  agents = agents_enabled_payload(p)
  vehicle_raw = read_param(p, "ai_vehicle_profile", "") or ""
  try:
    vehicle = json.loads(vehicle_raw) if isinstance(vehicle_raw, str) and vehicle_raw.strip().startswith("{") else vehicle_raw
  except json.JSONDecodeError:
    vehicle = vehicle_raw
  sections = {
    "harness": harness,
    "agents": {"disabled": agents.get("disabled") or []},
    "vehicle_profile": vehicle,
    "model_tier": harness["modelTier"],
  }
  hashes = {k: _hash_blob(sections[k]) for k in _SYNC_SECTIONS if k in sections}
  return {
    "version": 1,
    "updatedAt": int(time.time()),
    "sections": sections,
    "hashes": hashes,
  }


def get_stored_manifest(params: Params | None = None) -> dict[str, Any]:
  p = params or Params()
  raw = read_param(p, MANIFEST_KEY, "") or ""
  if not raw:
    return build_manifest(p)
  try:
    if isinstance(raw, bytes):
      raw = raw.decode(errors="replace")
    return json.loads(raw)
  except json.JSONDecodeError:
    return build_manifest(p)


def save_manifest(params: Params | None, manifest: dict[str, Any]) -> None:
  write_param(params or Params(), MANIFEST_KEY, json.dumps(manifest, ensure_ascii=False))


def merge_remote_manifest(
  params: Params | None,
  remote: dict[str, Any],
  *,
  mode: str = "merge",
) -> dict[str, Any]:
  """Apply remote manifest sections. mode: merge | replace."""
  p = params or Params()
  local = build_manifest(p)
  remote_sections = remote.get("sections") or {}
  applied: list[str] = []

  if mode == "replace" or "harness" in remote_sections:
    h = remote_sections.get("harness") or {}
    if h:
      from ai.common.storage import write_param_bool, write_param as wp
      if "deferredTools" in h:
        write_param_bool(p, "ai_deferred_tools", bool(h["deferredTools"]))
      if "externalizeResults" in h:
        write_param_bool(p, "ai_externalize_results", bool(h["externalizeResults"]))
      if "externalizeThreshold" in h:
        wp(p, "ai_externalize_threshold", str(int(h["externalizeThreshold"])))
      if h.get("modelTier"):
        wp(p, "ai_model_tier", normalize_tier(str(h["modelTier"])))
      applied.append("harness")

  if mode == "replace" or "agents" in remote_sections:
    ag = remote_sections.get("agents") or {}
    if "disabled" in ag:
      from ai.agents.config import save_disabled_agent_ids
      save_disabled_agent_ids(p, list(ag.get("disabled") or []))
      applied.append("agents")

  if mode == "replace" or "vehicle_profile" in remote_sections:
    vp = remote_sections.get("vehicle_profile")
    if vp is not None:
      from ai.common.storage import write_param as wp
      blob = json.dumps(vp, ensure_ascii=False) if not isinstance(vp, str) else vp
      wp(p, "ai_vehicle_profile", blob)
      applied.append("vehicle_profile")

  manifest = build_manifest(p)
  save_manifest(p, manifest)
  return {"ok": True, "applied": applied, "manifest": manifest}
