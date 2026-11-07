"""AI-assisted DBC editing for Cabana.

Capabilities (all read-only w.r.t. the opendbc originals):
- ``api_dbc_ai_infer``: statistical bit-field pre-analysis of raw frame samples
  (pure Python, deterministic) + optional LLM naming/units, producing a DBC
  draft and a decode validation report.
- ``api_dbc_ai_edit``: apply add/rename/remove/modify ops to a base DBC text
  (optionally converting a natural-language instruction into ops via LLM);
  returns the new text + unified diff + validation. Nothing is written to disk.
- ``api_dbc_commit`` / ``api_dbc_versions`` / ``api_dbc_rollback``: versioned
  storage of user DBCs in a dedicated user directory (never opendbc's).
"""
from __future__ import annotations

import asyncio
import difflib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from aiohttp import web

from ai.services.cabana.dbc import (
  _invalidate_dbc_catalog,
  _load_dbc_content,
  _user_dbc_dir,
)
from ai.services.cabana.decoder import _BE_BITS
from ai.services.cabana.decoder import _raw_value as _decoder_raw_value
from ai.services.cabana.decoder import decode_frames as _decode_frames
from ai.services.cabana.deps import cloudlog
from ai.services.cabana.handlers import _filter_frames_rel, _query_frames
from ai.services.cabana.http import json_response as _json_response
from ai.services.cabana.truth import _load_truth_cached

_INFER_SAMPLE_LIMIT_DEFAULT = 200
_INFER_SAMPLE_LIMIT_MAX = 1000
_USER_DBC_HISTORY_KEEP = 10
_NAME_SAFE_RE = re.compile(r"[^A-Za-z0-9_\-.]+")
_VERSION_RE = re.compile(r"^\d{14,20}$")

_SG_RE = re.compile(
  r"^\s*SG_\s+([A-Za-z_]\w*)"
  + r"(?:\s+[mM]\d?)*\s*:\s*"
  + r"(\d+)\|(\d+)@([01])([+-])\s*"
  + r"\(\s*([^,\s]+)\s*,\s*([^)\s]+)\s*\)\s*"
  + r"\[\s*([^|\]]+?)\s*\|\s*([^\]]+?)\s*\]\s*"
  + r'"([^"]*)"\s*(.*)$'
)
_BO_RE = re.compile(r"^\s*BO_\s+(\d+)\s+([A-Za-z_]\w*)\s*:\s*(\d+)\s+(\S+)")

# LLM output may wrap the JSON array in prose; salvage the outermost array.
_ARRAY_RE = re.compile(r"\[[\s\S]*\]")


# -----------------------------------------------------------------------------
# DBC text structural parse (independent of opendbc availability)
# -----------------------------------------------------------------------------

def _parse_sg_line(line: str) -> dict[str, Any] | None:
  m = _SG_RE.match(line)
  if not m:
    return None
  try:
    return {
      "name": m.group(1),
      "start_bit": int(m.group(2)),
      "size": int(m.group(3)),
      "little_endian": m.group(4) == "1",
      "signed": m.group(5) == "-",
      "factor": float(m.group(6)),
      "offset": float(m.group(7)),
      "min": float(m.group(8)),
      "max": float(m.group(9)),
      "unit": m.group(10),
      "receiver": m.group(11).strip() or "Vector__XXX",
    }
  except ValueError:
    return None


def _format_sg_line(sig: dict[str, Any]) -> str:
  e = "1" if sig.get("little_endian", True) else "0"
  s = "-" if sig.get("signed") else "+"
  factor = float(sig.get("factor", 1.0) or 0.0)
  offset = float(sig.get("offset", 0.0) or 0.0)
  lo = float(sig.get("min", 0.0) or 0.0)
  hi = float(sig.get("max", 0.0) or 0.0)
  unit = str(sig.get("unit") or "")
  receiver = str(sig.get("receiver") or "Vector__XXX")
  return (
    f' SG_ {sig["name"]} : {int(sig["start_bit"])}|{int(sig["size"])}@{e}{s}'
    + f" ({factor:g},{offset:g}) [{lo:g}|{hi:g}] \"{unit}\" {receiver}"
  )


def _parse_dbc_text(text: str) -> tuple[list[dict[str, Any]], list[str]]:
  """Structural parse of DBC text into signal dicts + a list of problems."""
  signals: list[dict[str, Any]] = []
  errors: list[str] = []
  address: int | None = None
  message: str | None = None
  seen: set[tuple[int, str]] = set()
  for lineno, line in enumerate(text.splitlines(), 1):
    stripped = line.strip()
    if stripped.startswith("BO_ "):
      m = _BO_RE.match(line)
      if not m:
        errors.append(f"line {lineno}: malformed BO_ statement")
        continue
      try:
        address = int(m.group(1), 0)
      except ValueError:
        errors.append(f"line {lineno}: bad BO_ address")
        continue
      message = m.group(2)
      continue
    if not stripped.startswith("SG_"):
      continue
    if address is None:
      errors.append(f"line {lineno}: SG_ before any BO_")
      continue
    parsed = _parse_sg_line(line)
    if parsed is None:
      errors.append(f"line {lineno}: malformed SG_ statement")
      continue
    if parsed["size"] <= 0 or parsed["size"] > 64:
      errors.append(f"line {lineno}: signal {parsed['name']} has invalid size")
      continue
    key = (address, parsed["name"])
    if key in seen:
      errors.append(f"line {lineno}: duplicate signal {parsed['name']}")
      continue
    seen.add(key)
    signals.append({**parsed, "address": address, "message": message or f"MSG_{address:X}"})
  if not signals:
    errors.append("no SG_ signal lines parsed")
  return signals, errors


def _opendbc_full_parse(dbc_text: str) -> tuple[bool | None, str | None]:
  """Full parse via opendbc (writes to a temp file; DBC() accepts paths).

  Returns (True, None) on success, (False, error) on parse failure, and
  (None, None) when opendbc is not importable (PC/dev environment).
  """
  from ai.services.cabana.deps import DBC as _OpenDBC

  if _OpenDBC is None:
    return None, None
  import tempfile

  tmp_path: Path | None = None
  try:
    with tempfile.NamedTemporaryFile("w", suffix=".dbc", delete=False, encoding="utf-8") as fh:
      fh.write(dbc_text)
      tmp_path = Path(fh.name)
    _OpenDBC(str(tmp_path))
    return True, None
  except Exception as e:
    return False, f"opendbc parse failed: {e}"
  finally:
    if tmp_path is not None:
      try:
        tmp_path.unlink()
      except OSError:
        pass


def _validate_dbc_text(
  dbc_text: str,
  samples_by_address: dict[int, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
  """Validate DBC text: structural parse + opendbc full parse + decode sampling."""
  signals, errors = _parse_dbc_text(dbc_text)
  parse_ok = not errors
  opendbc_ok: bool | None = None
  if parse_ok:
    opendbc_ok, opendbc_err = _opendbc_full_parse(dbc_text)
    if opendbc_ok is False:
      parse_ok = False
      errors.append(opendbc_err or "opendbc parse failed")

  decode_report: dict[str, Any] | None = None
  if samples_by_address and parse_ok:
    decode_report = _decode_report(signals, samples_by_address)

  return {
    "parse_ok": parse_ok,
    "opendbc_check": opendbc_ok,
    "errors": errors,
    "signal_count": len(signals),
    "decode_report": decode_report,
  }


def _decode_report(
  signals: list[dict[str, Any]],
  samples_by_address: dict[int, list[dict[str, Any]]],
) -> dict[str, Any]:
  """Decode sample frames with the proposed signals and sanity-check values."""
  total = 0
  decoded = 0
  non_finite = 0
  bool_violations = 0
  frames: list[dict[str, Any]] = []
  for addr, samples in samples_by_address.items():
    for f in samples:
      frames.append({**f, "address": addr})
  # decoder.decode_frames expects a "signal" key; structural parse produces "name".
  decoder_signals = [{**s, "signal": s["name"]} for s in signals]
  out = _decode_frames(decoder_signals, frames)
  decoded_values: dict[tuple[float, str], dict[str, float]] = {}
  for f in out:
    decoded_values[(float(f.get("time", 0.0)), str(f.get("data", "")))] = f.get("values", {})
  sig_by_key = {(int(s["address"]), str(s["name"])): s for s in signals}
  seen_keys: set[tuple[int, str]] = set()
  for f in frames:
    total += 1
    values = decoded_values.get((float(f.get("time", 0.0)), str(f.get("data", ""))))
    if not values:
      continue
    decoded += 1
    for name, v in values.items():
      seen_keys.add((int(f.get("address", 0)), str(name)))
      try:
        fv = float(v)
      except (TypeError, ValueError):
        non_finite += 1
        continue
      if fv != fv or fv in (float("inf"), float("-inf")):
        non_finite += 1
      sig = sig_by_key.get((int(f.get("address", 0)), str(name)))
      if sig is not None and sig.get("size") == 1 and not sig.get("signed") and fv not in (0.0, 1.0):
        bool_violations += 1
  undecodable_signals = sorted(
    f"0x{int(addr):X}.{name}" for (addr, name) in sig_by_key if (addr, name) not in seen_keys
  )
  return {
    "frames": total,
    "decoded_frames": decoded,
    "non_finite_values": non_finite,
    "bool_violations": bool_violations,
    "undecodable_signals": undecodable_signals,
    "ok": decoded > 0 and non_finite == 0 and bool_violations == 0,
  }


# -----------------------------------------------------------------------------
# Statistical signal inference (deterministic, no LLM)
# -----------------------------------------------------------------------------

def _samples_to_bytes(frames: list[dict[str, Any]]) -> list[tuple[float, bytes]]:
  out: list[tuple[float, bytes]] = []
  for f in frames:
    try:
      raw = bytes.fromhex(str(f.get("data", "")))
    except ValueError:
      continue
    if not raw:
      continue
    out.append(((float(f.get("time", 0.0)) or 0.0), (raw + bytes(8))[:8]))
  out.sort(key=lambda item: item[0])
  return out


def _active_bits(datas: list[bytes]) -> list[int]:
  n = len(datas)
  active: list[int] = []
  for bit in range(64):
    ones = 0
    for d in datas:
      ones += (d[bit >> 3] >> (bit & 7)) & 1
    if 0 < ones < n:
      active.append(bit)
  return active


def _runs_in_order(order: list[int], active_set: set[int]) -> list[list[int]]:
  runs: list[list[int]] = []
  current: list[int] = []
  for bit in order:
    if bit in active_set:
      current.append(bit)
    elif current:
      runs.append(current)
      current = []
  if current:
    runs.append(current)
  return runs


def _candidate_signal(start_bit: int, size: int, little_endian: bool) -> dict[str, Any]:
  return {
    "address": 0,
    "signal": "probe",
    "start_bit": start_bit,
    "size": size,
    "little_endian": little_endian,
    "signed": False,
    "factor": 1.0,
    "offset": 0.0,
  }


def _statistical_candidates(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
  """Extract candidate bit-fields from raw frame samples.

  - constant bits (all 0 / all 1 across samples) are excluded;
  - the remaining bits are clustered into contiguous runs under both endian
    hypotheses (little-endian ascending bit index, big-endian MSB-first stream);
  - single-bit runs are marked as bool candidates; byte-aligned runs whose raw
    value increments by exactly 1 per frame are marked as counters.
  """
  samples = _samples_to_bytes(frames)
  if len(samples) < 3:
    return []
  datas = [d for _, d in samples]
  active = _active_bits(datas)
  if not active:
    return []
  active_set = set(active)

  raw_orders = {"little": list(range(64)), "big": _BE_BITS}
  candidates: list[dict[str, Any]] = []
  seen_bitsets: set[frozenset[int]] = set()
  for endian in ("little", "big"):
    for run in _runs_in_order(raw_orders[endian], active_set):
      size = len(run)
      if size > 64:
        continue
      start = run[0]
      bitset = frozenset(run)
      # A full-byte run decodes identically under both hypotheses — keep only
      # the little-endian spelling to avoid duplicate candidates.
      if endian == "big" and bitset in seen_bitsets:
        continue
      sig = _candidate_signal(start, size, endian == "little")
      raws: list[int | None] = []
      usable = True
      for d in datas:
        try:
          raws.append(_decoder_raw_value(sig, d))
        except ValueError:
          usable = False
          break
      if not usable or any(r is None for r in raws):
        continue
      values = [int(r) for r in raws]
      unique = sorted(set(values))
      transitions = sum(1 for i in range(1, len(values)) if values[i] != values[i - 1])
      kind = "signal"
      if size == 1:
        kind = "bool"
      mod = 1 << size
      increments = sum(1 for i in range(1, len(values)) if values[i] == (values[i - 1] + 1) % mod)
      if len(values) >= 4 and increments / (len(values) - 1) >= 0.8 and len(unique) > 2:
        kind = "counter"
      default_name = f"S{start}_{size}"
      # Evidence is a list of "<source>: <content>" strings across the whole
      # codebase (sources: statistical / anchor / fit / decode / mux_hint).
      candidates.append({
        "name": default_name,
        "default_name": default_name,
        "start_bit": start,
        "size": size,
        "endian": endian,
        "signed": False,
        "factor": 1.0,
        "offset": 0.0,
        "unit": "",
        "kind": kind,
        "confidence": "statistical",
        "evidence": [
          "statistical: "
          + f"{len(unique)} unique raw values, min={min(values)}, max={max(values)}, "
          + f"transitions={transitions}/{len(values)}"
        ],
      })
      seen_bitsets.add(bitset)
  # Prefer shorter, higher-signal runs first for LLM context readability.
  candidates.sort(key=lambda c: (c["start_bit"], c["size"]))
  return candidates


def _safe_signal_name(raw: str, fallback: str) -> str:
  name = _NAME_SAFE_RE.sub("_", str(raw or "").strip())
  if not name or not re.match(r"^[A-Za-z_]", name):
    name = f"S_{name}" if name else fallback
  return name[:32]


def _build_dbc_draft(address: int, candidates: list[dict[str, Any]]) -> str:
  msg = f"MSG_{address:X}"
  lines = [f"BO_ {address} {msg}: 8 Vector__XXX"]
  for c in candidates:
    e = "1" if c.get("endian", "little") == "little" else "0"
    s = "-" if c.get("signed") else "+"
    factor = float(c.get("factor") or 1.0)
    offset = float(c.get("offset") or 0.0)
    unit = str(c.get("unit") or "")
    name = _safe_signal_name(c.get("name"), str(c.get("default_name") or "SIGNAL"))
    lines.append(
      f' SG_ {name} : {int(c["start_bit"])}|{int(c["size"])}@{e}{s}'
      + f' ({factor:g},{offset:g}) [0|0] "{unit}" Vector__XXX'
    )
  return "\n".join(lines) + "\n"


# -----------------------------------------------------------------------------
# LLM naming pass
# -----------------------------------------------------------------------------

def _infer_llm_messages(
  candidates: list[dict[str, Any]],
  address: int,
  hints: str,
  sample_count: int,
  anchor_notes: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
  compact: list[dict[str, Any]] = []
  for c in candidates:
    evidence = c.get("evidence") or []
    if isinstance(evidence, str):
      evidence = [evidence]
    item: dict[str, Any] = {
      "start_bit": c["start_bit"],
      "size": c["size"],
      "endian": c["endian"],
      "kind": c.get("kind", "signal"),
      "stats": " | ".join(str(e) for e in evidence),
    }
    if c.get("anchor"):
      item["anchor"] = c["anchor"]
    if c.get("functions"):
      item["functions"] = c["functions"]
    compact.append(item)
  prompt = (
    f"You are given {len(candidates)} candidate bit-fields extracted statistically from "
    + f"{sample_count} frames of one CAN message (address 0x{address:X}).\n"
    + f"Context/hints from the user: {hints or 'none'}\n"
    + "Candidate bit-fields JSON (start_bit is the MSB bit position for big-endian and the "
    + "LSB bit position for little-endian, opendbc convention):\n"
    + f"{json.dumps(compact)}\n\n"
    + "For each candidate, propose a DBC signal definition. Return a JSON array of objects with "
    + "exactly these keys: name (SHORT SCREAMING_SNAKE signal name), start_bit (int), size (int), "
    + 'endian ("little" or "big"), signed (bool), factor (number), offset (number), unit (string), '
    + "confidence (number 0..1), evidence (short reason). "
    + "Keep start_bit/size/endian as given unless the value distribution clearly proves otherwise. "
    + "Bool candidates get factor 1 and offset 0. Counter candidates get factor 1 and offset 0. "
    + "Output ONLY the JSON array."
  )
  if anchor_notes:
    prompt += (
      "\n\nPhysical anchoring is available: the anchor field of each candidate is its correlation "
      + "with hardware truth series (accel_long = longitudinal acceleration m/s^2, accel_vert = "
      + "vertical acceleration, yaw_rate = yaw rate rad/s, gps_speed = GPS speed m/s). Brake "
      + "candidates correlate negatively with accel_long, throttle positively; steering correlates "
      + "with yaw_rate; speed tracks gps_speed. Prefer the anchor evidence for naming and give a "
      + "factor suggestion consistent with it."
    )
  return [
    {"role": "system", "content": "You are a DBC signal definition assistant for CAN reverse engineering. Output only a JSON array."},
    {"role": "user", "content": prompt},
  ]


def _anchor_notes(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
  """Prompt addendum payload when any candidate carries anchor evidence."""
  if not any(c.get("anchor") for c in candidates):
    return None
  return {
    "legend": (
      "accel_long=longitudinal acceleration m/s^2, accel_vert=vertical acceleration, "
      + "yaw_rate=yaw rate rad/s, gps_speed=GPS speed m/s"
    ),
  }


def _parse_llm_candidates(text: str) -> list[dict[str, Any]]:
  raw = (text or "").strip()
  if not raw:
    return []
  blobs = [raw]
  m = _ARRAY_RE.search(raw)
  if m:
    blobs.insert(0, m.group(0))
  for blob in blobs:
    try:
      data = json.loads(blob)
    except json.JSONDecodeError:
      continue
    if isinstance(data, list):
      return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict) and isinstance(data.get("signals"), list):
      return [item for item in data["signals"] if isinstance(item, dict)]
  return []


def _merge_llm_candidates(candidates: list[dict[str, Any]], llm_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
  """Merge LLM naming/factor suggestions onto statistical candidates by position."""
  by_key: dict[tuple[int, int, str], dict[str, Any]] = {
    (int(c["start_bit"]), int(c["size"]), str(c["endian"])): c for c in candidates
  }
  order: list[dict[str, Any]] = []
  matched: set[int] = set()
  for idx, item in enumerate(llm_items):
    try:
      key = (int(item["start_bit"]), int(item["size"]), str(item.get("endian", "little")))
    except (KeyError, TypeError, ValueError):
      key = None
    target = by_key.get(key) if key is not None else None
    if target is None and 0 <= idx < len(candidates):
      target = candidates[idx]
    if target is None:
      continue
    matched.add(id(target))
    try:
      confidence = max(0.0, min(1.0, float(item.get("confidence", 0.5))))
    except (TypeError, ValueError):
      confidence = 0.5
    target["name"] = _safe_signal_name(item.get("name"), target["default_name"])
    # A physical calibration (anchor fit) beats the LLM's generic 1.0/0.0
    # factor guess — keep it unless the candidate has no calibration at all.
    has_fit = isinstance(target.get("calibration"), dict) and target.get("calibration")
    for field in ("factor", "offset"):
      if has_fit:
        continue
      try:
        target[field] = float(item.get(field, target[field]))
      except (TypeError, ValueError):
        pass
    target["unit"] = str(item.get("unit") or "") or str(target.get("unit") or "")
    target["signed"] = bool(item.get("signed", False))
    target["confidence"] = confidence
    evidence = str(item.get("evidence") or "").strip()
    if evidence:
      prev = target.get("evidence")
      prev_list = [prev] if isinstance(prev, str) else list(prev or [])
      target["evidence"] = [*prev_list, f"LLM: {evidence[:120]}"]
    order.append(target)
  for c in candidates:
    if id(c) not in matched:
      order.append(c)
  return order


# -----------------------------------------------------------------------------
# Edit ops
# -----------------------------------------------------------------------------

def _parse_op_target(target: Any) -> tuple[int, str] | None:
  """Target format: ``<address>.<SignalName>`` (address may be 0x-prefixed)."""
  if isinstance(target, dict):
    try:
      return int(target["address"]), str(target["signal"])
    except (KeyError, TypeError, ValueError):
      return None
  if not isinstance(target, str) or "." not in target:
    return None
  addr_str, _, sig = target.partition(".")
  try:
    return int(addr_str.strip(), 0), sig.strip()
  except ValueError:
    return None


def _find_message_span(lines: list[str], address: int) -> tuple[int, int] | None:
  """Return (bo_index, last_signal_index) for the message; last_signal_index == bo_index when empty."""
  bo_index = None
  last_sig = None
  for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped.startswith("BO_ "):
      if bo_index is not None:
        break
      m = _BO_RE.match(line)
      if m and int(m.group(1), 0) == address:
        bo_index = i
        last_sig = i
    elif bo_index is not None and stripped.startswith("SG_"):
      last_sig = i
  if bo_index is None:
    return None
  return bo_index, (last_sig if last_sig is not None else bo_index)


def _rewrite_sg_line(line: str, updates: dict[str, Any]) -> str | None:
  parsed = _parse_sg_line(line)
  if parsed is None:
    return None
  if "endian" in updates:
    parsed["little_endian"] = str(updates["endian"]).lower() != "big"
  for field in ("signed", "unit", "min", "max", "receiver"):
    if field in updates:
      parsed[field] = updates[field]
  for field in ("start_bit", "size"):
    if field in updates:
      try:
        parsed[field] = int(updates[field])
      except (TypeError, ValueError):
        return None
  for field in ("factor", "offset"):
    if field in updates:
      try:
        parsed[field] = float(updates[field])
      except (TypeError, ValueError):
        return None
  return _format_sg_line(parsed)


def _apply_dbc_ops(dbc_text: str, ops: list[dict[str, Any]]) -> tuple[str, list[str]]:
  """Apply add/rename/remove/modify ops; returns (new_text, errors)."""
  errors: list[str] = []
  lines = dbc_text.splitlines()
  for op in ops:
    if not isinstance(op, dict):
      errors.append("op entry must be an object")
      continue
    action = str(op.get("op", "")).lower()
    payload = op.get("payload") or {}
    if not isinstance(payload, dict):
      payload = {}
    target = _parse_op_target(op.get("target"))
    if action != "add" and target is None:
      errors.append(f"op {action or '?'}: target must be <address>.<SignalName>")
      continue
    if action == "add":
      try:
        address = int(payload.get("address", target[0] if target else 0))
      except (TypeError, ValueError):
        errors.append("op add: invalid payload.address")
        continue
      if not str(payload.get("name") or "").strip():
        errors.append("op add: payload.name required")
        continue
      sig = {
        "name": _safe_signal_name(payload.get("name"), "SIGNAL"),
        "start_bit": int(payload.get("start_bit", 0) or 0),
        "size": int(payload.get("size", 8) or 8),
        "little_endian": str(payload.get("endian", "little")).lower() != "big",
        "signed": bool(payload.get("signed", False)),
        "factor": float(payload.get("factor", 1.0) or 1.0),
        "offset": float(payload.get("offset", 0.0) or 0.0),
        "min": float(payload.get("min", 0.0) or 0.0),
        "max": float(payload.get("max", 0.0) or 0.0),
        "unit": str(payload.get("unit") or ""),
        "receiver": "Vector__XXX",
      }
      if sig["size"] <= 0 or sig["size"] > 64:
        errors.append("op add: payload.size must be 1..64")
        continue
      span = _find_message_span(lines, address)
      new_line = _format_sg_line(sig)
      if span is None:
        msg_name = str(payload.get("message") or f"MSG_{address:X}")
        lines.append("")
        lines.append(f"BO_ {address} {msg_name}: 8 Vector__XXX")
        lines.append(new_line)
      else:
        lines.insert(span[1] + 1, new_line)
      continue
    address, sig_name = target
    span = _find_message_span(lines, address)
    if span is None:
      errors.append(f"op {action}: message 0x{address:X} not found in base DBC")
      continue
    if action == "remove":
      kept = []
      removed = False
      in_msg = False
      for line in lines:
        stripped = line.strip()
        if stripped.startswith("BO_ "):
          m = _BO_RE.match(line)
          in_msg = bool(m and int(m.group(1), 0) == address)
        if in_msg and stripped.startswith("SG_"):
          m = _SG_RE.match(line)
          if m and m.group(1) == sig_name:
            removed = True
            continue
        if not removed and in_msg and stripped.startswith((
          f"CM_ SG_ {address} {sig_name} ", f"VAL_ {address} {sig_name} ",
        )):
          continue
        kept.append(line)
      lines = kept
      if not removed:
        errors.append(f"op remove: signal {sig_name} not found in 0x{address:X}")
      continue
    # rename / modify need the exact SG_ line
    line_idx = None
    in_msg = False
    for i, line in enumerate(lines):
      stripped = line.strip()
      if stripped.startswith("BO_ "):
        m = _BO_RE.match(line)
        in_msg = bool(m and int(m.group(1), 0) == address)
      if in_msg and stripped.startswith("SG_"):
        m = _SG_RE.match(line)
        if m and m.group(1) == sig_name:
          line_idx = i
          break
    if line_idx is None:
      errors.append(f"op {action}: signal {sig_name} not found in 0x{address:X}")
      continue
    if action == "rename":
      new_name = _safe_signal_name(payload.get("new_name"), "")
      if not new_name:
        errors.append("op rename: payload.new_name required")
        continue
      old_name = sig_name
      lines[line_idx] = re.sub(
        rf"^(\s*SG_\s+){re.escape(old_name)}\b", rf"\g<1>{new_name}", lines[line_idx],
      )
      # keep annotations pointing at the signal
      lines = [
        re.sub(rf"^(CM_\s+SG_\s+{address}\s+){re.escape(old_name)}\b", rf"\g<1>{new_name}", ln)
        if ln.strip().startswith("CM_") else ln
        for ln in lines
      ]
      lines = [
        re.sub(rf"^(VAL_\s+{address}\s+){re.escape(old_name)}\b", rf"\g<1>{new_name}", ln)
        if ln.strip().startswith("VAL_") else ln
        for ln in lines
      ]
      continue
    if action == "modify":
      new_line = _rewrite_sg_line(lines[line_idx], payload)
      if new_line is None:
        errors.append(f"op modify: cannot rewrite signal {sig_name}")
        continue
      lines[line_idx] = new_line
      continue
    errors.append(f"op {action}: unknown op")
  return "\n".join(lines) + ("\n" if lines else ""), errors


async def _ops_from_instruction_async(instruction: str, dbc_text: str) -> tuple[list[dict[str, Any]] | None, str | None]:
  from ai.services.cabana.ai_explain import _cabana_ai_complete

  messages = [
    {
      "role": "system",
      "content": (
        "You convert CAN DBC edit requests into JSON op arrays. Output only a JSON array. "
        + 'Each op: {"op":"add|rename|remove|modify","target":"<address>.<SignalName>","payload":{...}}. '
        + "add payload: {address, name, start_bit, size, endian, signed, factor, offset, unit}. "
        + "rename payload: {new_name}. modify payload: only the fields to change."
      ),
    },
    {
      "role": "user",
      "content": (
        f"Base DBC (excerpt):\n{dbc_text[:4000]}\n\n"
        + f"User instruction: {instruction}\n\n"
        + "Return only the JSON array of ops."
      ),
    },
  ]
  result = await _cabana_ai_complete(messages, prefer_json=True, lang="en", temperature=0.1)
  if not result.get("ok"):
    return None, str(result.get("error") or "AI unavailable")
  ops = _parse_llm_candidates(result.get("response", ""))
  if not ops:
    return None, "AI returned no usable ops"
  return ops, None


# -----------------------------------------------------------------------------
# HTTP handlers
# -----------------------------------------------------------------------------

async def _read_json_body(request: web.Request) -> dict[str, Any] | None:
  try:
    body = await request.json()
  except Exception:
    return None
  return body if isinstance(body, dict) else None


def _fetch_samples(
  route: str,
  address: int,
  t0: float | None,
  t1: float | None,
  sample_limit: int,
) -> tuple[list[dict[str, Any]], float, str | None]:
  """Same data path as the /frames endpoint (cache + in-flight dedup included).

  Returns ``(samples, base, error)``; ``base`` is the route-relative time
  origin (first frame's absolute time) used for truth-series alignment.
  """
  frames, err = _query_frames(route)
  if err or frames is None:
    return [], 0.0, err or "Route not found"
  window, base = _filter_frames_rel(frames, address, t0, t1)
  if not window:
    return [], base, None
  return window[-sample_limit:], base, None


async def api_dbc_ai_infer(request: web.Request) -> web.Response:
  """POST /api/cabana/dbc/ai/infer — statistical candidates + LLM naming + draft."""
  body = await _read_json_body(request)
  if body is None:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  route = str(body.get("route", "")).strip()
  try:
    address = int(body.get("address"))
  except (TypeError, ValueError):
    return _json_response({"ok": False, "error": "address required"}, status=400)
  if not route:
    return _json_response({"ok": False, "error": "route required"}, status=400)
  try:
    t0 = float(body["t0"]) if body.get("t0") is not None else None
    t1 = float(body["t1"]) if body.get("t1") is not None else None
  except (TypeError, ValueError):
    return _json_response({"ok": False, "error": "Invalid t0/t1"}, status=400)
  try:
    sample_limit = int(body.get("sample_limit") or _INFER_SAMPLE_LIMIT_DEFAULT)
  except (TypeError, ValueError):
    sample_limit = _INFER_SAMPLE_LIMIT_DEFAULT
  sample_limit = max(3, min(sample_limit, _INFER_SAMPLE_LIMIT_MAX))
  hints = str(body.get("hints") or "").strip()
  use_anchor = body.get("use_anchor")
  use_anchor = True if use_anchor is None else bool(use_anchor)

  loop = asyncio.get_running_loop()
  samples, base, err = await loop.run_in_executor(None, _fetch_samples, route, address, t0, t1, sample_limit)
  if err:
    return _json_response({"ok": False, "error": err}, status=404)
  if not samples:
    return _json_response({"ok": False, "error": "No frames for this address in the requested window"}, status=404)

  candidates = _statistical_candidates(samples)
  if not candidates:
    return _json_response({
      "ok": False,
      "error": "No active bit-fields found in samples (payload may be constant)",
    }, status=422)

  # Optional physical anchoring: annotate candidates with hardware-truth
  # correlations, factor/offset fits and checksum detection (zero LLM cost).
  if use_anchor:
    truth = _load_truth_cached(route)
    if truth and truth.get("available"):
      try:
        from ai.services.cabana.anchor import _annotate_candidates

        candidates = _annotate_candidates(address, samples, truth, base)
      except Exception as e:
        cloudlog.warning(f"cabana: dbc ai infer anchor pass failed: {e}")
  candidates = [c for c in candidates if c.get("flag") != "checksum"]
  if not candidates:
    return _json_response({
      "ok": False,
      "error": "All candidates are checksum/counter fields; nothing to infer",
    }, status=422)

  anchor_notes = _anchor_notes(candidates)
  dbc_text_draft = _build_dbc_draft(address, candidates)
  llm_used = False
  llm_error = None
  try:
    from ai.services.cabana.ai_explain import _cabana_ai_complete

    result = await _cabana_ai_complete(
      _infer_llm_messages(candidates, address, hints, len(samples), anchor_notes),
      prefer_json=True,
      lang="en",
      temperature=0.2,
      max_tokens=2048,
    )
    if result.get("ok"):
      llm_items = _parse_llm_candidates(result.get("response", ""))
      if llm_items:
        candidates = _merge_llm_candidates(candidates, llm_items)
        dbc_text_draft = _build_dbc_draft(address, candidates)
        llm_used = True
      else:
        llm_error = "LLM returned no usable candidates"
    else:
      llm_error = str(result.get("error") or "AI unavailable")
  except Exception as e:
    cloudlog.error(f"cabana: dbc ai infer LLM pass failed: {e}")
    llm_error = str(e)

  validation = _validate_dbc_text(dbc_text_draft, {address: samples})
  return _json_response({
    "ok": True,
    "address": address,
    "route": route,
    "sample_count": len(samples),
    "llm_used": llm_used,
    "llm_error": llm_error,
    "candidates": candidates,
    "dbc_text_draft": dbc_text_draft,
    "validation": validation,
  })


async def api_dbc_ai_edit(request: web.Request) -> web.Response:
  """POST /api/cabana/dbc/ai/edit — apply ops (optionally LLM-derived) to a base DBC text."""
  body = await _read_json_body(request)
  if body is None:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  base_dbc = str(body.get("base_dbc") or "")
  instruction = str(body.get("instruction") or "").strip()
  ops = body.get("ops")
  if not base_dbc:
    return _json_response({"ok": False, "error": "base_dbc required"}, status=400)
  # base_dbc may be raw DBC text or a DBC name; treat it as text when it looks like one.
  if "BO_" not in base_dbc:
    loaded = await asyncio.get_running_loop().run_in_executor(None, _load_dbc_content, base_dbc)
    if not loaded:
      return _json_response({"ok": False, "error": f"DBC not found: {base_dbc}"}, status=404)
    base_dbc = loaded

  if not ops and not instruction:
    return _json_response({"ok": False, "error": "ops or instruction required"}, status=400)
  if not ops and instruction:
    ops, err = await _ops_from_instruction_async(instruction, base_dbc)
    if err:
      return _json_response({"ok": False, "error": err}, status=502)
  if not isinstance(ops, list) or not ops:
    return _json_response({"ok": False, "error": "ops must be a non-empty array"}, status=400)

  new_text, op_errors = await asyncio.get_running_loop().run_in_executor(
    None, _apply_dbc_ops, base_dbc, ops,
  )
  validation = _validate_dbc_text(new_text)
  diff = "\n".join(difflib.unified_diff(
    base_dbc.splitlines(), new_text.splitlines(),
    fromfile="base.dbc", tofile="edited.dbc", lineterm="",
  ))
  return _json_response({
    "ok": True,
    "dbc_text": new_text,
    "diff": diff,
    "op_errors": op_errors,
    "validation": validation,
  })


# -----------------------------------------------------------------------------
# User DBC store (versioned)
# -----------------------------------------------------------------------------

def _safe_dbc_name(name: str) -> str | None:
  cleaned = _NAME_SAFE_RE.sub("_", str(name or "").strip()).strip("._")
  if not cleaned or not re.match(r"^[A-Za-z_]", cleaned):
    return None
  return cleaned[:64]


def _dbc_version_now() -> str:
  return datetime.now().strftime("%Y%m%d%H%M%S%f")[:17]


def _user_dbc_paths(name: str) -> tuple[Path, list[Path]]:
  user_dir = _user_dbc_dir()
  current = user_dir / f"{name}.dbc"
  history = sorted(user_dir.glob(f"{name}.*.dbc"), key=lambda p: p.stat().st_mtime if p.exists() else 0)
  return current, history


def _prune_history(history: list[Path]) -> None:
  overflow = len(history) - _USER_DBC_HISTORY_KEEP
  for path in history[:max(0, overflow)]:
    try:
      path.unlink()
    except OSError:
      pass


def _commit_user_dbc(name: str, dbc_text: str) -> tuple[str, str | None]:
  """Write the current version + a history snapshot. Returns (version, error)."""
  user_dir = _user_dbc_dir()
  user_dir.mkdir(parents=True, exist_ok=True)
  version = _dbc_version_now()
  current, history = _user_dbc_paths(name)
  current.write_text(dbc_text, encoding="utf-8")
  history_path = user_dir / f"{name}.{version}.dbc"
  history_path.write_text(dbc_text, encoding="utf-8")
  _prune_history([p for p in history if p != history_path] + [history_path])
  return version, None


def _list_versions(name: str) -> list[dict[str, Any]]:
  current, history = _user_dbc_paths(name)
  versions: list[dict[str, Any]] = []
  for path in sorted(history, key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True):
    try:
      stat = path.stat()
    except OSError:
      continue
    m = re.match(rf"^{re.escape(name)}\.(\d+)\.dbc$", path.name)
    if not m:
      continue
    versions.append({
      "version": m.group(1),
      "size": stat.st_size,
      "mtime": int(stat.st_mtime),
      "current": False,
    })
  if current.exists():
    try:
      stat = current.stat()
      versions.insert(0, {
        "version": "current",
        "size": stat.st_size,
        "mtime": int(stat.st_mtime),
        "current": True,
      })
    except OSError:
      pass
  return versions


def _rollback_user_dbc(name: str, version: str) -> tuple[str, str | None]:
  """Copy a history version over the current file; register it as a new version."""
  if not _VERSION_RE.match(version or ""):
    return "", "invalid version"
  user_dir = _user_dbc_dir()
  source = user_dir / f"{name}.{version}.dbc"
  if not source.exists():
    return "", f"version not found: {version}"
  text = source.read_text(encoding="utf-8")
  return _commit_user_dbc(name, text)


async def api_dbc_commit(request: web.Request) -> web.Response:
  """POST /api/cabana/dbc/commit — validate then store a user DBC (versioned)."""
  body = await _read_json_body(request)
  if body is None:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  name = _safe_dbc_name(str(body.get("name") or ""))
  dbc_text = str(body.get("dbc_text") or "")
  if not name:
    return _json_response({"ok": False, "error": "valid name required"}, status=400)
  if not dbc_text.strip():
    return _json_response({"ok": False, "error": "dbc_text required"}, status=400)

  validation = await asyncio.get_running_loop().run_in_executor(None, _validate_dbc_text, dbc_text)
  if not validation.get("parse_ok"):
    return _json_response({"ok": False, "error": "DBC validation failed", "validation": validation}, status=422)

  version, err = await asyncio.get_running_loop().run_in_executor(None, _commit_user_dbc, name, dbc_text)
  if err:
    return _json_response({"ok": False, "error": err}, status=500)
  _invalidate_dbc_catalog()
  cloudlog.info(f"cabana: user DBC committed: {name} v{version}")
  return _json_response({"ok": True, "name": name, "version": version, "validation": validation})


async def api_dbc_versions(request: web.Request) -> web.Response:
  """GET /api/cabana/dbc/versions?name= — list stored versions of a user DBC."""
  name = _safe_dbc_name(request.query.get("name", ""))
  if not name:
    return _json_response({"ok": False, "error": "valid name required"}, status=400)
  versions = await asyncio.get_running_loop().run_in_executor(None, _list_versions, name)
  return _json_response({"ok": True, "name": name, "versions": versions})


async def api_dbc_rollback(request: web.Request) -> web.Response:
  """POST /api/cabana/dbc/rollback — restore a history version as the current one."""
  body = await _read_json_body(request)
  if body is None:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  name = _safe_dbc_name(str(body.get("name") or ""))
  version = str(body.get("version") or "")
  if not name:
    return _json_response({"ok": False, "error": "valid name required"}, status=400)
  version_out, err = await asyncio.get_running_loop().run_in_executor(None, _rollback_user_dbc, name, version)
  if err:
    return _json_response({"ok": False, "error": err}, status=404)
  _invalidate_dbc_catalog()
  cloudlog.info(f"cabana: user DBC rollback: {name} -> {version} (new version {version_out})")
  return _json_response({"ok": True, "name": name, "version": version_out})
