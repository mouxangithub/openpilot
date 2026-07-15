"""Fingerprint loading and comparison against opendbc."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

_HEX_RE = re.compile(r"0x([0-9a-fA-F]+)", re.IGNORECASE)
_FRAME_ADDR_RE = re.compile(r"(?:addr(?:ess)?|id)\s*[=:]\s*0x([0-9a-fA-F]+)", re.IGNORECASE)
_FRAME_LEN_RE = re.compile(r"len(?:gth)?\s*[=:]\s*(\d+)", re.IGNORECASE)


def extract_hex_ids_from_text(text: str) -> list[str]:
  """Extract unique CAN addresses from Cabana frame text or similar."""
  if not text:
    return []
  seen: set[str] = set()
  out: list[str] = []
  for m in _HEX_RE.finditer(text):
    val = int(m.group(1), 16)
    if val > 0x7FF:
      continue
    hx = f"0x{val:X}"
    if hx not in seen:
      seen.add(hx)
      out.append(hx)
  return sorted(out, key=lambda x: int(x, 16))


def extract_observed_fingerprint(text: str) -> dict[int, int]:
  """Best-effort {address: length} from frame lines."""
  observed: dict[int, int] = {}
  for line in (text or "").splitlines():
    addrs = _FRAME_ADDR_RE.findall(line)
    if not addrs:
      for m in _HEX_RE.finditer(line):
        addrs.append(m.group(1))
    if not addrs:
      continue
    length = 8
    lm = _FRAME_LEN_RE.search(line)
    if lm:
      length = int(lm.group(1))
    else:
      data_m = re.search(r"data\s*[=:]\s*([0-9a-fA-F\s]+)", line, re.IGNORECASE)
      if data_m:
        hex_bytes = re.findall(r"[0-9a-fA-F]{2}", data_m.group(1))
        if hex_bytes:
          length = len(hex_bytes)
    for a in addrs:
      addr = int(a, 16)
      if addr <= 0x7FF:
        observed[addr] = max(observed.get(addr, 0), length)
  if observed:
    return observed
  for hx in extract_hex_ids_from_text(text):
    observed[int(hx, 16)] = 8
  return observed


def _opendbc_car_dir() -> Path | None:
  try:
    from openpilot.common.basedir import BASEDIR
    p = Path(BASEDIR) / "opendbc" / "car"
    if p.is_dir():
      return p
  except Exception:
    pass
  here = Path(__file__).resolve()
  for rel in ("opendbc_repo/opendbc/car", "opendbc/car"):
    p = here.parents[2] / rel
    if p.is_dir():
      return p
  return None


def _parse_fingerprints_from_repo() -> dict[str, list[dict[int, int]]]:
  car_dir = _opendbc_car_dir()
  if not car_dir:
    return {}
  out: dict[str, list[dict[int, int]]] = {}
  for fp_file in car_dir.glob("*/fingerprints.py"):
    try:
      text = fp_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
      continue
    if "FINGERPRINTS" not in text:
      continue
    try:
      tree = ast.parse(text)
      for node in tree.body:
        if isinstance(node, ast.Assign):
          for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "FINGERPRINTS":
              val = ast.literal_eval(node.value)
              if isinstance(val, dict):
                for car, fps in val.items():
                  parsed: list[dict[int, int]] = []
                  for fp in fps if isinstance(fps, list) else [fps]:
                    if isinstance(fp, dict):
                      parsed.append({int(k): int(v) for k, v in fp.items()})
                  if parsed:
                    out[str(car)] = parsed
    except Exception:
      continue
  return out


def load_all_fingerprints() -> dict[str, list[dict[int, int]]]:
  try:
    from opendbc.car.fingerprints import _FINGERPRINTS  # type: ignore
    result: dict[str, list[dict[int, int]]] = {}
    for car, fps in _FINGERPRINTS.items():
      result[str(car)] = [{int(k): int(v) for k, v in fp.items()} for fp in fps]
    return result
  except Exception:
    return _parse_fingerprints_from_repo()


def _jaccard(a: set[int], b: set[int]) -> float:
  if not a and not b:
    return 0.0
  inter = len(a & b)
  union = len(a | b)
  return inter / union if union else 0.0


def _length_match_score(observed: dict[int, int], candidate: dict[int, int]) -> float:
  if not observed:
    return 0.0
  matched = 0
  for addr, length in observed.items():
    if addr in candidate and candidate[addr] == length:
      matched += 1
  return matched / len(observed)


def compare_fingerprint(
  hex_ids: list[str] | None = None,
  observed: dict[int, int] | None = None,
  *,
  brand: str = "",
  limit: int = 10,
) -> dict[str, Any]:
  """Compare observed CAN IDs against opendbc fingerprint database."""
  obs = dict(observed or {})
  if not obs and hex_ids:
    for h in hex_ids:
      h = h.strip().lower().replace("0x", "")
      if h:
        obs[int(h, 16)] = 8
  if not obs:
    return {"ok": False, "error": "Provide hex_ids or observed fingerprint dict"}

  all_fps = load_all_fingerprints()
  if not all_fps:
    return {"ok": False, "error": "Could not load opendbc fingerprints on this host"}

  brand_l = (brand or "").lower()
  obs_addrs = set(obs.keys())
  scored: list[tuple[float, str, int, dict[int, int]]] = []

  for car, variants in all_fps.items():
    if brand_l and brand_l not in car.lower():
      continue
    for idx, fp in enumerate(variants):
      fp_addrs = set(fp.keys())
      score = 0.55 * _jaccard(obs_addrs, fp_addrs) + 0.45 * _length_match_score(obs, fp)
      if score > 0.05:
        scored.append((score, car, idx, fp))

  if not scored and brand_l:
    for car, variants in all_fps.items():
      for idx, fp in enumerate(variants):
        fp_addrs = set(fp.keys())
        score = 0.55 * _jaccard(obs_addrs, fp_addrs) + 0.45 * _length_match_score(obs, fp)
        if score > 0.05:
          scored.append((score, car, idx, fp))

  scored.sort(key=lambda x: x[0], reverse=True)
  matches = []
  for score, car, idx, fp in scored[:limit]:
    missing = sorted(obs_addrs - set(fp.keys()))
    extra = sorted(set(fp.keys()) - obs_addrs)[:20]
    matches.append({
      "car": car,
      "variant_index": idx,
      "score": round(score, 4),
      "matched_ids": len(obs_addrs & set(fp.keys())),
      "observed_count": len(obs_addrs),
      "fingerprint_count": len(fp),
      "missing_in_candidate": [f"0x{a:X}" for a in missing[:15]],
      "extra_in_candidate": [f"0x{a:X}" for a in extra],
    })

  fingerprint_str = "{" + ", ".join(f"0x{k:X}: {v}" for k, v in sorted(obs.items())) + "}"
  return {
    "ok": True,
    "observed": {f"0x{k:X}": v for k, v in sorted(obs.items())},
    "fingerprint_candidate": fingerprint_str,
    "match_count": len(matches),
    "matches": matches,
    "hint": "High score + few missing IDs → likely match; use suggest_signals_for_adaptation for signal mapping.",
  }


def extract_can_ids_from_route(route_name: str, *, max_frames: int = 8000) -> dict[str, Any]:
  """Scan route qlog/rlog for unique CAN addresses (read-only)."""
  if not route_name or ".." in route_name or "/" in route_name or "\\" in route_name:
    return {"ok": False, "error": "Invalid route name"}

  from ai.cabana import _find_qlogs, _find_rlogs, _get_routes_dir, _pick_can_log_paths

  routes_dir = _get_routes_dir()
  if routes_dir is None:
    return {"ok": False, "error": "Routes directory not found"}

  route_path = routes_dir / route_name
  if not route_path.is_dir():
    return {"ok": False, "error": f"Route not found: {route_name}"}

  qlogs = _find_qlogs(route_path)
  rlogs = _find_rlogs(route_path)
  log_paths, source = _pick_can_log_paths(qlogs, rlogs)
  if not log_paths:
    return {"ok": False, "error": "No qlog/rlog in route"}

  try:
    from openpilot.tools.lib.logreader import LogReader
  except Exception:
    try:
      from tools.lib.logreader import LogReader  # type: ignore
    except Exception as e:
      return {"ok": False, "error": f"LogReader unavailable: {e}"}

  observed: dict[int, int] = {}
  frames = 0
  for log_path in log_paths:
    try:
      lr = LogReader(str(log_path))
    except Exception as e:
      return {"ok": False, "error": f"Failed to open log {log_path.name}: {e}"}
    for msg in lr:
      if frames >= max_frames:
        break
      if msg.which() != "can":
        continue
      for c in msg.can:
        frames += 1
        if frames > max_frames:
          break
        addr = int(c.address)
        if addr > 0x7FF:
          continue
        ln = len(c.dat) if c.dat else 8
        observed[addr] = max(observed.get(addr, 0), ln)

  hex_ids = [f"0x{a:X}" for a in sorted(observed.keys())]
  pattern = None
  if hex_ids:
    from ai.tools.adaptation import analyze_can_id_pattern
    pattern = analyze_can_id_pattern(hex_ids)
  compare = compare_fingerprint(observed=observed) if observed else {"ok": False}

  return {
    "ok": True,
    "route": route_name,
    "log_source": source,
    "frames_scanned": frames,
    "unique_ids": len(hex_ids),
    "hex_ids": hex_ids[:120],
    "observed": {f"0x{k:X}": v for k, v in sorted(observed.items())},
    "pattern_analysis": pattern,
    "fingerprint_compare": compare,
    "hint": "Use save_adaptation_draft with fingerprint_candidate after human review.",
  }
