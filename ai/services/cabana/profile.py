"""One-click vehicle profile: CAN scan + on-demand LLM naming + DBC commit.

Three endpoints (see artifacts/software-cabana-autodbc/DESIGN.md §2):
- ``POST /api/cabana/profile/scan``   — full-route statistical scan, ZERO LLM.
- ``POST /api/cabana/profile/naming`` — per-address LLM naming (cost gate:
  ≤ 8 candidates per call, user-triggered only, no log re-read).
- ``POST /api/cabana/profile/commit`` — one-shot versioned DBC commit built
  from the scan/naming state (reuses the user-DBC store + rollback chain).

Scan state is cached in ``_profile_state`` (LRU, last 2 routes) so naming and
commit never touch the logs again.
"""
from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

from aiohttp import web

from ai.services.cabana.anchor import (
  _annotate_candidates,
  _confidence,
  _decode_selfcheck,
  _fit_linear,
  _s_stat,
  _truth_variance_ok,
)
from ai.services.cabana.car_params import _resolve_car_params
from ai.services.cabana.dbc import _invalidate_dbc_catalog, _suggest_dbc_for_fingerprint
from ai.services.cabana.dbc_edit import (
  _build_dbc_draft,
  _commit_user_dbc,
  _infer_llm_messages,
  _merge_llm_candidates,
  _parse_llm_candidates,
  _read_json_body,
  _safe_dbc_name,
  _validate_dbc_text,
)
from ai.services.cabana.deps import cloudlog
from ai.services.cabana.handlers import _filter_frames_rel
from ai.services.cabana.http import json_response as _json_response
from ai.services.cabana.replay import _query_frames
from ai.services.cabana.truth import _load_truth_cached

PROFILE_SCHEMA = "cabana.profile.v1"
_PROFILE_MAX_ADDRESSES = 40
_PROFILE_SAMPLE_LIMIT = 1000
_PROFILE_NAMING_MAX_CANDIDATES = 8
_PROFILE_STATE_MAX = 2
_PROFILE_SCAN_WORKERS = 2
_PROFILE_SUMMARY_TOP = 5
_PROFILE_SUMMARY_GROUPS = ("speed", "brake", "throttle", "steering", "gear", "other")

# LRU scan state: route -> {"fingerprint", "truth", "base", "addresses": {...}}
_profile_state: dict[str, dict[str, Any]] = {}
_profile_state_order: list[str] = []


def _candidate_key(c: dict[str, Any]) -> tuple[int, int, str]:
  return (int(c.get("start_bit", 0) or 0), int(c.get("size", 0) or 0), str(c.get("endian", "little")))


def _remember_state(route: str, entry: dict[str, Any]) -> None:
  _profile_state.pop(route, None)
  if route in _profile_state_order:
    _profile_state_order.remove(route)
  _profile_state[route] = entry
  _profile_state_order.append(route)
  while len(_profile_state_order) > _PROFILE_STATE_MAX:
    old = _profile_state_order.pop(0)
    _profile_state.pop(old, None)


# -----------------------------------------------------------------------------
# Scan
# -----------------------------------------------------------------------------

def _bus_majority(frames: list[dict[str, Any]]) -> int:
  counts: dict[int, int] = {}
  for f in frames:
    try:
      bus = int(f.get("bus", 0) or 0)
    except (TypeError, ValueError):
      continue
    counts[bus] = counts.get(bus, 0) + 1
  return max(counts, key=lambda b: counts[b]) if counts else 0


def _payload_len(frames: list[dict[str, Any]]) -> int:
  counts: dict[int, int] = {}
  for f in frames:
    try:
      n = len(bytes.fromhex(str(f.get("data", ""))))
    except ValueError:
      continue
    counts[n] = counts.get(n, 0) + 1
  return max(counts, key=lambda n: counts[n]) if counts else 0


def _scan_address(
  address: int,
  frames: list[dict[str, Any]],
  truth: dict[str, Any] | None,
  t0: float | None,
  t1: float | None,
  sample_limit: int,
) -> dict[str, Any]:
  """Analyze one address: window → sample → annotate → draft. Never raises."""
  window, base = _filter_frames_rel(frames, address, t0, t1)
  if len(window) < 3:
    return {"address": address, "candidates": [], "dbc_text_draft": ""}
  sampled = window[-sample_limit:]
  try:
    candidates = _annotate_candidates(address, sampled, truth, base)
  except Exception as e:  # defensive: a broken address must not kill the scan
    cloudlog.warning(f"cabana: profile scan address 0x{address:X} failed: {e}")
    candidates = []
  draft_candidates = [c for c in candidates if c.get("flag") != "checksum"]
  return {
    "address": address,
    "candidates": candidates,
    "dbc_text_draft": _build_dbc_draft(address, draft_candidates) if draft_candidates else "",
  }


def _scan_worker(
  route: str,
  t0: float | None,
  t1: float | None,
  min_hz: float,
  min_frames: int,
  max_addresses: int,
  sample_limit: int,
) -> dict[str, Any]:
  started = time.monotonic()
  frames, err = _query_frames(route)
  if err or frames is None:
    return {"ok": False, "error": err or "Route not found"}
  if not frames:
    return {"ok": False, "error": "No CAN frames found"}
  base = float(frames[0]["time"])

  truth = _load_truth_cached(route)
  cp = _resolve_car_params(route) or {}
  fingerprint_name = str(cp.get("carFingerprint", "") or "")
  suggested_dbc = None
  if fingerprint_name:
    suggested_dbc = _suggest_dbc_for_fingerprint(fingerprint_name, brand=str(cp.get("brand", "") or ""))

  # Group by address (bus-agnostic analysis, majority bus recorded per design).
  by_address: dict[int, list[dict[str, Any]]] = {}
  for f in frames:
    try:
      addr = int(f.get("address", -1))
    except (TypeError, ValueError):
      continue
    by_address.setdefault(addr, []).append(f)
  # Global t0/t1 window first (route-relative), then rate/frame-count filters.
  if t0 is not None or t1 is not None:
    for addr, flist in by_address.items():
      by_address[addr] = [
        f for f in flist
        if (t0 is None or float(f["time"]) - base >= t0 - 1e-9)
        and (t1 is None or float(f["time"]) - base <= t1 + 1e-9)
      ]
  stats = []
  for addr, flist in by_address.items():
    count = len(flist)
    if count < min_frames:
      continue
    t_first = float(flist[0]["time"])
    t_last = float(flist[-1]["time"])
    span = max(t_last - t_first, 1e-6)
    hz = count / span
    if hz < min_hz:
      continue
    stats.append({"addr": addr, "frames": flist, "count": count, "hz": hz})
  stats.sort(key=lambda s: (-s["count"], s["addr"]))
  stats = stats[:max_addresses]

  address_results: list[dict[str, Any]] = []
  state_addresses: dict[int, dict[str, Any]] = {}
  if stats:
    with ThreadPoolExecutor(max_workers=_PROFILE_SCAN_WORKERS) as pool:
      futures = {
        pool.submit(_scan_address, s["addr"], s["frames"], truth, None, None, sample_limit): s
        for s in stats
      }
      for fut, s in futures.items():
        result = fut.result()
        addr = int(result["address"])
        count = s["count"]
        address_results.append({
          "address": addr,
          "bus": _bus_majority(s["frames"]),
          "frames": count,
          "hz": round(s["hz"], 2),
          "payload_len": _payload_len(s["frames"]),
          "candidates": result["candidates"],
          "dbc_text_draft": result["dbc_text_draft"],
        })
        state_addresses[addr] = {
          "frames": s["frames"][-sample_limit:],
          "candidates": result["candidates"],
          "sample_count": min(count, sample_limit),
        }
  address_results.sort(key=lambda a: a["address"])

  # ---- summary groups (confidence desc, top 5 per group) ----
  summary: dict[str, list[dict[str, Any]]] = {group: [] for group in _PROFILE_SUMMARY_GROUPS}
  for block in address_results:
    for cand in block["candidates"]:
      if cand.get("flag") == "checksum":
        continue
      conf = cand.get("confidence")
      if not isinstance(conf, int):
        continue
      tags = cand.get("functions") or ["other"]
      for tag in tags:
        if tag not in summary:
          tag = "other"
        summary[tag].append({
          "address": block["address"],
          "name": str(cand.get("name", "")),
          "confidence": conf,
          # Identity tuple mirrors backend _candidate_key so the frontend can
          # re-match summary entries to candidates even after LLM renaming.
          "start_bit": int(cand.get("start_bit", 0) or 0),
          "size": int(cand.get("size", 0) or 0),
          "endian": str(cand.get("endian", "little") or "little"),
        })
  for group in summary:
    summary[group].sort(key=lambda e: (-e["confidence"], e["address"], e["name"]))
    summary[group] = summary[group][:_PROFILE_SUMMARY_TOP]

  # ---- truth report ----
  truth_series_report: dict[str, dict[str, Any]] = {}
  if truth and truth.get("available"):
    for name, s in (truth.get("series") or {}).items():
      ts = s.get("t", [])
      if not ts:
        continue
      span = max(float(ts[-1]) - float(ts[0]), 1e-6)
      truth_series_report[str(name)] = {"hz": round(len(ts) / span, 2), "count": len(ts)}

  report: dict[str, Any] = {
    "ok": True,
    "schema": PROFILE_SCHEMA,
    "route": route,
    "duration_sec": round(time.monotonic() - started, 2),
    "generated_at": int(datetime.now(UTC).timestamp()),
    "fingerprint": {
      "carFingerprint": fingerprint_name,
      "suggested_dbc": suggested_dbc,
      "matched": bool(suggested_dbc),
    },
    "truth": {
      "available": bool(truth and truth.get("available")),
      "series": truth_series_report,
      "variance_ok": _truth_variance_ok(truth),
      "note": str((truth or {}).get("note", "") or ""),
    },
    "addresses": address_results,
    "summary": summary,
    "llm_used": False,
  }
  _remember_state(route, {
    "fingerprint": report["fingerprint"],
    "truth": truth,
    "base": base,
    "addresses": state_addresses,
  })
  return report


async def api_profile_scan(request: web.Request) -> web.Response:
  """POST /api/cabana/profile/scan — zero-LLM full-route vehicle profile."""
  body = await _read_json_body(request)
  if body is None:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  route = str(body.get("route", "")).strip()
  if not route:
    return _json_response({"ok": False, "error": "route required"}, status=400)
  try:
    t0 = float(body["t0"]) if body.get("t0") is not None else None
    t1 = float(body["t1"]) if body.get("t1") is not None else None
  except (TypeError, ValueError):
    return _json_response({"ok": False, "error": "Invalid t0/t1"}, status=400)
  try:
    min_hz = float(body.get("min_hz") or 5.0)
  except (TypeError, ValueError):
    min_hz = 5.0
  try:
    min_frames = int(body.get("min_frames") or 200)
  except (TypeError, ValueError):
    min_frames = 200
  try:
    max_addresses = int(body.get("max_addresses") or _PROFILE_MAX_ADDRESSES)
  except (TypeError, ValueError):
    max_addresses = _PROFILE_MAX_ADDRESSES
  try:
    sample_limit = int(body.get("sample_limit") or _PROFILE_SAMPLE_LIMIT)
  except (TypeError, ValueError):
    sample_limit = _PROFILE_SAMPLE_LIMIT
  max_addresses = max(1, min(max_addresses, _PROFILE_MAX_ADDRESSES))
  sample_limit = max(3, min(sample_limit, _PROFILE_SAMPLE_LIMIT))

  loop = asyncio.get_running_loop()
  report = await loop.run_in_executor(
    None, _scan_worker, route, t0, t1, min_hz, min_frames, max_addresses, sample_limit,
  )
  status = 200 if report.get("ok") else 404
  return _json_response(report, status=status)


# -----------------------------------------------------------------------------
# Naming (on-demand LLM, cost-gated)
# -----------------------------------------------------------------------------

def _anchor_notes_for(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
  if not any(c.get("anchor") for c in candidates):
    return None
  return {
    "legend": (
      "anchor/calibration fields give each candidate's correlation with hardware "
      + "truth series (accel_long = longitudinal acceleration m/s^2, accel_vert = "
      + "vertical acceleration, yaw_rate = yaw rate rad/s, gps_speed = GPS speed m/s). "
      + "Brake candidates correlate negatively with accel_long, throttle positively; "
      + "steering correlates with yaw_rate; speed tracks gps_speed. Prefer anchor "
      + "evidence for naming and factor suggestions."
    ),
  }


def _naming_merge(
  addr_entry: dict[str, Any],
  wanted_keys: list[tuple[int, int, str]],
  llm_items: list[dict[str, Any]],
  truth: dict[str, Any] | None,
  base: float,
) -> list[dict[str, Any]]:
  """Merge LLM output onto the wanted candidates and recompute confidence."""
  all_candidates = addr_entry.get("candidates") or []
  by_key = {_candidate_key(c): c for c in all_candidates}
  wanted = [by_key[k] for k in wanted_keys if k in by_key]
  if not wanted:
    return all_candidates
  merged = _merge_llm_candidates(wanted, llm_items)
  # Recompute anchor-aware confidence / calibration on the merged candidates.
  try:
    from ai.services.cabana.anchor import _enrich_candidates

    merged = _enrich_candidates(merged, addr_entry.get("frames") or [], truth, base)
  except Exception as e:
    cloudlog.warning(f"cabana: profile naming re-enrich failed: {e}")
  # Persist merged versions back into the state candidate list (by identity).
  by_id = {id(c): c for c in wanted}
  out: list[dict[str, Any]] = []
  for c in all_candidates:
    out.append(by_id.get(id(c), c))
  return out


async def api_profile_naming(request: web.Request) -> web.Response:
  """POST /api/cabana/profile/naming — LLM naming for ≤8 user-opened candidates."""
  body = await _read_json_body(request)
  if body is None:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  route = str(body.get("route", "")).strip()
  if not route:
    return _json_response({"ok": False, "error": "route required"}, status=400)
  try:
    address = int(body.get("address"))
  except (TypeError, ValueError):
    return _json_response({"ok": False, "error": "address required"}, status=400)
  hints = str(body.get("hints") or "").strip()
  raw_candidates = body.get("candidates")
  if not isinstance(raw_candidates, list) or not raw_candidates:
    return _json_response({"ok": False, "error": "candidates required"}, status=400)
  if len(raw_candidates) > _PROFILE_NAMING_MAX_CANDIDATES:
    return _json_response(
      {"ok": False, "error": f"at most {_PROFILE_NAMING_MAX_CANDIDATES} candidates per naming call"},
      status=400,
    )
  wanted_keys: list[tuple[int, int, str]] = []
  for item in raw_candidates:
    if not isinstance(item, dict):
      continue
    try:
      wanted_keys.append((int(item["start_bit"]), int(item["size"]), str(item.get("endian", "little"))))
    except (KeyError, TypeError, ValueError):
      continue
  if not wanted_keys:
    return _json_response({"ok": False, "error": "candidates must carry start_bit/size/endian"}, status=400)

  state = _profile_state.get(route)
  if state is None:
    return _json_response({"ok": False, "error": "profile scan first"}, status=409)
  addr_entry = state.get("addresses", {}).get(address)
  if addr_entry is None:
    return _json_response({"ok": False, "error": f"address 0x{address:X} not in profile scan"}, status=404)

  from ai.services.cabana.ai_explain import _cabana_ai_complete

  all_candidates = addr_entry.get("candidates") or []
  by_key = {_candidate_key(c): c for c in all_candidates}
  selected = [by_key[k] for k in wanted_keys if k in by_key]
  if not selected:
    return _json_response({"ok": False, "error": "no matching candidates in scan state"}, status=404)

  anchor_notes = _anchor_notes_for(selected)
  llm_used = False
  llm_error = None
  try:
    result = await _cabana_ai_complete(
      _infer_llm_messages(selected, address, hints, int(addr_entry.get("sample_count", 0)), anchor_notes),
      prefer_json=True,
      lang="en",
      temperature=0.2,
      max_tokens=2048,
    )
    if result.get("ok"):
      llm_items = _parse_llm_candidates(result.get("response", ""))
      if llm_items:
        updated = _naming_merge(addr_entry, wanted_keys, llm_items, state.get("truth"), state.get("base", 0.0))
        addr_entry["candidates"] = updated
        llm_used = True
      else:
        llm_error = "LLM returned no usable candidates"
    else:
      llm_error = str(result.get("error") or "AI unavailable")
  except Exception as e:
    cloudlog.error(f"cabana: profile naming LLM pass failed: {e}")
    llm_error = str(e)

  final_candidates = addr_entry.get("candidates") or []
  draft_candidates = [c for c in final_candidates if c.get("flag") != "checksum"]
  return _json_response({
    "ok": True,
    "address": address,
    "llm_used": llm_used,
    "llm_error": llm_error,
    "candidates": final_candidates,
    "dbc_text_draft": _build_dbc_draft(address, draft_candidates) if draft_candidates else "",
  })


# -----------------------------------------------------------------------------
# Commit (one-shot DBC from the scan state)
# -----------------------------------------------------------------------------

def _commit_text_worker(
  route: str,
  addresses: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
  state = _profile_state.get(route)
  if state is None:
    return None, "profile scan first"
  texts: list[str] = []
  for entry in addresses:
    if not isinstance(entry, dict):
      continue
    try:
      address = int(entry.get("address"))
    except (TypeError, ValueError):
      continue
    addr_entry = state.get("addresses", {}).get(address)
    if addr_entry is None:
      continue
    all_candidates = addr_entry.get("candidates") or []
    wanted = entry.get("candidates")
    if isinstance(wanted, list) and wanted:
      keys = set()
      for item in wanted:
        if isinstance(item, dict):
          try:
            keys.add((int(item["start_bit"]), int(item["size"]), str(item.get("endian", "little"))))
          except (KeyError, TypeError, ValueError):
            continue
      selected = [c for c in all_candidates if _candidate_key(c) in keys]
    else:
      selected = [c for c in all_candidates if c.get("flag") != "checksum"]
    selected = [c for c in selected if c.get("flag") != "checksum"]
    if selected:
      texts.append(_build_dbc_draft(address, selected))
  if not texts:
    return None, "no candidates selected"
  return "\n".join(texts), None


async def api_profile_commit(request: web.Request) -> web.Response:
  """POST /api/cabana/profile/commit — build + validate + store a user DBC."""
  body = await _read_json_body(request)
  if body is None:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  route = str(body.get("route", "")).strip()
  if not route:
    return _json_response({"ok": False, "error": "route required"}, status=400)
  name = _safe_dbc_name(str(body.get("name") or ""))
  if not name:
    return _json_response({"ok": False, "error": "valid name required"}, status=400)
  raw_addresses = body.get("addresses")
  if not isinstance(raw_addresses, list) or not raw_addresses:
    return _json_response({"ok": False, "error": "addresses required"}, status=400)

  loop = asyncio.get_running_loop()
  dbc_text, err = await loop.run_in_executor(None, _commit_text_worker, route, raw_addresses)
  if err or dbc_text is None:
    return _json_response({"ok": False, "error": err or "nothing to commit"}, status=409)

  validation = await loop.run_in_executor(None, _validate_dbc_text, dbc_text)
  if not validation.get("parse_ok"):
    return _json_response({"ok": False, "error": "DBC validation failed", "validation": validation}, status=422)
  version, commit_err = await loop.run_in_executor(None, _commit_user_dbc, name, dbc_text)
  if commit_err:
    return _json_response({"ok": False, "error": commit_err}, status=500)
  _invalidate_dbc_catalog()
  cloudlog.info(f"cabana: profile DBC committed: {name} v{version}")
  return _json_response({"ok": True, "name": name, "version": version, "validation": validation})


# Re-exported for tests / potential reuse of the confidence pipeline.
__all__ = [
  "PROFILE_SCHEMA",
  "api_profile_commit",
  "api_profile_naming",
  "api_profile_scan",
  "_confidence",
  "_decode_selfcheck",
  "_fit_linear",
  "_s_stat",
]
