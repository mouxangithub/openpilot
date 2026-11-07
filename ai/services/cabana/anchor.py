"""Physical anchoring / calibration / detection algorithms for DBC reverse
engineering (pure functions, no I/O).

Pipeline (see artifacts/software-cabana-autodbc/DESIGN.md §4):
- ``_best_lag_correlation``: resample CAN signal + truth series onto a common
  20 Hz grid over the overlap window, lag-search ±0.3 s, best |pearson|.
- ``_function_tags``: speed / brake / throttle / steering / gear labeling.
- ``_detect_checksum``: per-byte sensitivity (popcount correlation, XOR and
  SUM checksum match rates).
- ``_detect_mux_hint``: small-unique-value field co-occurrence annotation.
- ``_fit_linear``: closed-form least-squares factor/offset with R² gating.
- ``_annotate_candidates``: main entry — statistical candidates + full
  enrichment (anchor / calibration / confidence / evidence / preview).

All evidence strings follow the shared convention ``"<source>: <content>"``
with source ∈ statistical / anchor / fit / decode / mux_hint, and the
``evidence`` field is always ``list[str]``.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from ai.services.cabana.dbc_edit import _samples_to_bytes, _statistical_candidates
from ai.services.cabana.decoder import _raw_value as _decoder_raw_value
from ai.services.cabana.truth import (
  ACCEL_LONG,
  ACCEL_VERT,
  GPS_ACCEL,
  GPS_SPEED,
  YAW_RATE,
)

_GRID_HZ = 20.0
_MAX_LAG_SEC = 0.3
_MIN_CORR_N = 20
_MIN_OVERLAP_SEC = 2.0
_ANCHOR_TARGETS = (ACCEL_LONG, ACCEL_VERT, YAW_RATE, GPS_SPEED, GPS_ACCEL)
_EVIDENCE_SOURCES = ("statistical", "anchor", "fit", "decode", "mux_hint")


# -----------------------------------------------------------------------------
# Correlation helpers
# -----------------------------------------------------------------------------

def _pearson(xs: Any, ys: Any) -> float:
  a = np.asarray(xs, dtype=float)
  b = np.asarray(ys, dtype=float)
  if a.size < 3 or a.size != b.size:
    return 0.0
  if float(a.std()) < 1e-12 or float(b.std()) < 1e-12:
    return 0.0
  r = float(np.corrcoef(a, b)[0, 1])
  return 0.0 if r != r else r


def _rank(values: np.ndarray) -> np.ndarray:
  """Average-rank transform (Spearman building block)."""
  order = np.argsort(values, kind="stable")
  ranks = np.empty(values.size, dtype=float)
  ranks[order] = np.arange(values.size, dtype=float)
  # average ties
  sorted_vals = values[order]
  i = 0
  while i < values.size:
    j = i
    while j + 1 < values.size and sorted_vals[j + 1] == sorted_vals[i]:
      j += 1
    if j > i:
      ranks[order[i: j + 1]] = (i + j) / 2.0
    i = j + 1
  return ranks


def _can_bucket_means(t: np.ndarray, v: np.ndarray, lo: float, hi: float, hz: float) -> tuple[np.ndarray | None, np.ndarray | None]:
  """Per-grid-bucket mean of CAN samples (low-frequency truth friendly)."""
  n = int((hi - lo) * hz) + 1
  if n < _MIN_CORR_N:
    return None, None
  idx = np.round((t - lo) * hz).astype(int)
  ok = (idx >= 0) & (idx < n)
  if int(ok.sum()) < _MIN_CORR_N:
    return None, None
  idx = idx[ok]
  vals = v[ok]
  sums = np.bincount(idx, weights=vals, minlength=n)
  counts = np.bincount(idx, minlength=n)
  grid = lo + np.arange(n) / hz
  mask = counts > 0
  return grid[mask], sums[mask] / counts[mask]


def _best_lag_correlation(
  can_t: list[float],
  can_v: list[float],
  truth_t: list[float],
  truth_v: list[float],
) -> dict[str, Any] | None:
  """Best lagged Pearson correlation between a CAN signal and a truth series.

  Both sides are resampled onto a uniform 20 Hz grid over their overlap
  window; lags ±0.3 s at grid step are searched and the |r|-maximizing lag is
  returned. Returns None on degenerate (constant / too short) input.
  """
  ct = np.asarray(can_t, dtype=float)
  cv = np.asarray(can_v, dtype=float)
  tt = np.asarray(truth_t, dtype=float)
  tv = np.asarray(truth_v, dtype=float)
  if ct.size < _MIN_CORR_N or tt.size < 3:
    return None
  lo = max(float(ct[0]), float(tt[0]))
  hi = min(float(ct[-1]), float(tt[-1]))
  if hi - lo < _MIN_OVERLAP_SEC:
    return None
  hz = _GRID_HZ
  grid = np.arange(lo, hi + 0.5 / hz, 1.0 / hz)
  if grid.size < _MIN_CORR_N:
    return None
  bt, bv = _can_bucket_means(ct, cv, lo, hi, hz)
  if bt is None or bt.size < _MIN_CORR_N:
    return None
  can_grid = np.interp(grid, bt, bv)
  if float(np.var(can_grid)) < 1e-9:
    return None
  truth_grid = np.interp(grid, tt, tv)
  if float(np.var(truth_grid)) < 1e-9:
    return None
  best: tuple[float, float] | None = None
  for lag in np.arange(-_MAX_LAG_SEC, _MAX_LAG_SEC + 1e-9, 1.0 / hz):
    shifted = np.interp(grid - float(lag), tt, tv)
    r = _pearson(can_grid, shifted)
    if best is None or abs(r) > abs(best[1]):
      best = (float(lag), r)
  if best is None:
    return None
  lag, r = best
  return {
    "pearson_r": round(r, 4),
    "lag_sec": round(lag, 4),
    "sign": 1 if r >= 0 else -1,
    "n": int(grid.size),
  }


# -----------------------------------------------------------------------------
# Function labeling
# -----------------------------------------------------------------------------

def _function_tags(cand: dict[str, Any], anchors: dict[str, dict[str, Any]]) -> list[str]:
  """Physical function tags for one candidate (may be empty → 'other')."""
  tags: list[str] = []
  size = int(cand.get("size", 0) or 0)
  kind = str(cand.get("kind", "signal"))
  a = anchors.get(GPS_SPEED)
  if a and a["pearson_r"] >= 0.7 and a["sign"] >= 0 and size >= 8:
    tags.append("speed")
  a = anchors.get(ACCEL_LONG)
  if a and a["pearson_r"] <= -0.5:
    tags.append("brake")
  if a and a["pearson_r"] >= 0.5:
    tags.append("throttle")
  if not tags:
    ga = anchors.get(GPS_ACCEL)
    if ga and ga["pearson_r"] >= 0.5:
      tags.append("throttle")
  a = anchors.get(YAW_RATE)
  if a and abs(a["pearson_r"]) >= 0.5:
    tags.append("steering")
  if not tags and size <= 8 and kind not in ("counter", "bool") and int(cand.get("_unique", 1 << 30)) <= 8:
    tags.append("gear")
  return tags


# -----------------------------------------------------------------------------
# Checksum / mux detection
# -----------------------------------------------------------------------------

def _detect_checksum(datas: list[bytes]) -> int | None:
  """Byte index (0..7) acting as a checksum/CRC field, or None.

  For each candidate byte i: s1 = Spearman(popcount(other bytes), data[i]),
  s2 = XOR-of-others match rate, s3 = SUM-of-others match rate. A byte with
  score ≥ 0.9 and ≥ 8 unique values is reported.
  """
  if len(datas) < 32:
    return None
  arr = np.frombuffer(b"".join(datas), dtype=np.uint8).reshape(len(datas), 8)
  for i in range(8):
    target = arr[:, i]
    if int(np.unique(target).size) < 8:
      continue
    others = np.delete(arr, i, axis=1)
    pop = np.unpackbits(others, axis=1).sum(axis=1).astype(float)
    s1 = _pearson(_rank(pop), _rank(target.astype(float)))
    xor = np.zeros(len(datas), dtype=np.uint8)
    for j in range(others.shape[1]):
      xor ^= others[:, j]
    s2 = float(np.mean(xor == target))
    s3 = float(np.mean((others.sum(axis=1) & 0xFF) == target))
    score = max(s1, s2, s3)
    if score >= 0.9:
      return i
  return None


def _mux_evidence(values: list[int], other_changed: list[bool]) -> str | None:
  """Co-occurrence evidence string for a suspected multiplexed field."""
  vals = np.asarray(values, dtype=int)
  changed = np.asarray(other_changed, dtype=bool)
  total = int(changed.sum())
  if total < 5 or vals.size != changed.size:
    return None
  uniq, counts = np.unique(vals[changed], return_counts=True)
  if uniq.size < 2 or uniq.size > 8:
    return None
  parts = []
  for u, c in zip(uniq.tolist(), counts.tolist(), strict=True):
    pct = 100.0 * c / total
    if pct >= 5.0:
      parts.append(f"{u}:{pct:.0f}%")
  if len(parts) < 2:
    return None
  return "mux_hint: values {" + ",".join(parts) + "} co-occur with other-signal changes"


# -----------------------------------------------------------------------------
# Linear calibration
# -----------------------------------------------------------------------------

def _fit_linear(raw_vals: list[float], phys_vals: list[float]) -> dict[str, Any] | None:
  """Closed-form least squares ``phys ≈ factor*raw + offset`` with R² gating.

  Acceptance: n ≥ 50, r² ≥ 0.9, 1e-4 ≤ |factor| ≤ 1e4 (sign-fixed so the
  caller can flip negative-correlated truth before fitting).
  """
  x = np.asarray(raw_vals, dtype=float)
  y = np.asarray(phys_vals, dtype=float)
  ok = np.isfinite(x) & np.isfinite(y)
  x, y = x[ok], y[ok]
  if x.size < 50:
    return None
  if float(x.std()) < 1e-9 or float(y.std()) < 1e-9:
    return None
  factor = float(np.cov(x, y, ddof=0)[0, 1] / np.var(x))
  offset = float(y.mean() - factor * x.mean())
  ss_res = float(np.sum((y - (factor * x + offset)) ** 2))
  ss_tot = float(np.sum((y - y.mean()) ** 2))
  r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
  if r2 < 0.9:
    return None
  if abs(factor) < 1e-4 or abs(factor) > 1e4:
    return None
  return {"factor": round(factor, 8), "offset": round(offset, 6), "r2": round(r2, 4), "n": int(x.size)}


def _preview_points(ts: list[float], vs: list[float], max_pts: int = 120) -> dict[str, list[float]]:
  """Uniform preview sample (≤ max_pts) for the frontend sparkline/plot."""
  n = len(ts)
  if n == 0:
    return {"t": [], "v": []}
  if n <= max_pts:
    idx = list(range(n))
  else:
    idx = [round(i * (n - 1) / (max_pts - 1)) for i in range(max_pts)]
  return {
    "t": [round(float(ts[i]), 4) for i in idx],
    "v": [round(float(vs[i]), 4) for i in idx],
  }


# -----------------------------------------------------------------------------
# Candidate enrichment
# -----------------------------------------------------------------------------

def _truth_variance_ok(truth: dict[str, Any] | None) -> bool:
  """True when at least one primary truth series has usable variance."""
  if not truth or not truth.get("available"):
    return False
  for name in (ACCEL_LONG, GPS_SPEED, YAW_RATE):
    s = (truth.get("series") or {}).get(name)
    if not s:
      continue
    v = np.asarray(s.get("v", []), dtype=float)
    if v.size >= 10 and float(np.var(v)) > 1e-9:
      return True
  return False


def _prepare_truth(truth: dict[str, Any] | None, base: float, span: tuple[float, float] | None) -> dict[str, tuple[np.ndarray, np.ndarray]]:
  """Convert truth series to route-relative (t, v) arrays, windowed to span."""
  out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
  if not truth or not truth.get("available"):
    return out
  for name, s in (truth.get("series") or {}).items():
    t_abs = np.asarray(s.get("t", []), dtype=float)
    v = np.asarray(s.get("v", []), dtype=float)
    if t_abs.size < 3 or t_abs.size != v.size:
      continue
    t_rel = t_abs - float(base)
    if span is not None:
      pad = 1.0
      keep = (t_rel >= span[0] - pad) & (t_rel <= span[1] + pad)
      t_rel, v = t_rel[keep], v[keep]
      if t_rel.size < 3:
        continue
    out[str(name)] = (t_rel, v)
  return out


def _s_stat(cand: dict[str, Any], vals: list[int]) -> float:
  """Statistical transition strength ∈ [0, 1] (counter/bool aware)."""
  n = len(vals)
  if n < 2:
    return 0.0
  kind = str(cand.get("kind", "signal"))
  mod = 1 << int(cand.get("size", 8) or 8)
  if kind == "counter":
    increments = sum(1 for i in range(1, n) if vals[i] == (vals[i - 1] + 1) % mod)
    return min(1.0, increments / (n - 1))
  transitions = sum(1 for i in range(1, n) if vals[i] != vals[i - 1])
  if kind == "bool":
    return min(1.0, transitions / (n - 1))
  return min(1.0, transitions / (n - 1) * 2.0)


def _confidence(s_stat: float, s_anchor: float | None, s_dec: float) -> int:
  """0-100 confidence; renormalized weights when no anchor is available."""
  if s_anchor is not None:
    return int(round(100 * (0.40 * s_stat + 0.45 * s_anchor + 0.15 * s_dec)))
  return int(round(100 * (0.65 * s_stat + 0.35 * s_dec)))


def _decode_selfcheck(raws: list[int | None]) -> tuple[float, str]:
  """Decode sanity in _decode_report semantics: 1.0 clean / 0.5 partial / 0."""
  total = len(raws)
  decoded = sum(1 for r in raws if r is not None)
  non_finite = 0  # raw unsigned extraction cannot produce non-finite values
  if total == 0:
    return 0.0, "decode: ok (0/0 frames, 0 non-finite)"
    # pragma: no cover
  label = f"decode: ok ({decoded}/{total} frames, {non_finite} non-finite)"
  if decoded == total:
    return 1.0, label
  if decoded > 0:
    return 0.5, label
  return 0.0, label


def _enrich_candidates(
  candidates: list[dict[str, Any]],
  frames: list[dict[str, Any]],
  truth: dict[str, Any] | None,
  base: float,
) -> list[dict[str, Any]]:
  """Attach anchor / calibration / confidence / evidence / preview to candidates.

  ``frames`` are address-filtered frames with route-relative ``time``; ``truth``
  uses absolute seconds and ``base`` is the route-relative origin (from
  ``_filter_frames_rel``). Existing names/units are preserved; calibration only
  overwrites factor/offset when the fit is accepted.
  """
  if not candidates:
    return candidates
  samples = _samples_to_bytes(frames)
  if not samples:
    return candidates
  times = [t for t, _ in samples]
  datas = [d for _, d in samples]
  span = (float(times[0]), float(times[-1]))
  truth_map = _prepare_truth(truth, base, span)
  truth_usable = _truth_variance_ok(truth) and bool(truth_map)

  # Checksum byte detection (per design: sensitivity over the raw samples).
  checksum_idx = _detect_checksum(datas) if len(datas) >= 32 else None
  if checksum_idx is not None:
    for c in candidates:
      start = int(c["start_bit"])
      size = int(c["size"])
      if str(c.get("endian")) == "little" and start <= checksum_idx * 8 and start + size >= checksum_idx * 8 + 8:
        c["flag"] = "checksum"
        c["confidence"] = None

  # Raw value series per candidate (None when the field is undecodable).
  raws_by_cand: list[list[int] | None] = []
  for c in candidates:
    sig = {
      "start_bit": int(c["start_bit"]),
      "size": int(c["size"]),
      "little_endian": str(c.get("endian", "little")) == "little",
      "signed": False,
    }
    raws: list[int] = []
    usable = True
    for d in datas:
      r = _decoder_raw_value(sig, d)
      if r is None:
        usable = False
        break
      raws.append(int(r))
    raws_by_cand.append(raws if usable else None)

  # Change flags per candidate (for mux co-occurrence evidence).
  change_flags: list[list[bool]] = []
  for raws in raws_by_cand:
    if raws:
      change_flags.append([raws[i] != raws[i - 1] for i in range(1, len(raws))])
    else:
      change_flags.append([False] * max(0, len(datas) - 1))

  for cand, raws in zip(candidates, raws_by_cand, strict=True):
    if cand.get("flag") == "checksum" or raws is None:
      continue
    size = int(cand["size"])
    kind = str(cand.get("kind", "signal"))
    unique = sorted(set(raws))
    cand["_unique"] = len(unique)

    # ---- anchoring ----
    anchors: dict[str, dict[str, Any]] = {}
    if truth_usable:
      for name, (tt, tv) in truth_map.items():
        if float(np.var(tv)) < 1e-9:
          continue
        corr = _best_lag_correlation(times, raws, tt.tolist(), tv.tolist())
        if corr is not None:
          anchors[name] = corr
    best_name: str | None = None
    best_anchor: dict[str, Any] | None = None
    for name in _ANCHOR_TARGETS:
      a = anchors.get(name)
      if a and (best_anchor is None or abs(a["pearson_r"]) > abs(best_anchor["pearson_r"])):
        best_name, best_anchor = name, a

    evidence: list[str] = list(cand.get("evidence") or [])
    if isinstance(cand.get("evidence"), str):  # legacy str evidence → normalize
      evidence = [cand["evidence"]]
    if best_anchor is not None and best_name is not None:
      a = best_anchor
      cand["anchor"] = {
        "truth": best_name,
        "pearson_r": a["pearson_r"],
        "lag_sec": a["lag_sec"],
        "sign": a["sign"],
        "n": a["n"],
      }
      evidence.append(
        "anchor: " + f"{best_name} pearson(r={a['pearson_r']}, lag={a['lag_sec']}s, "
        + f"sign={a['sign']:+d}, n={a['n']})"
      )

    # ---- function tags ----
    tags = _function_tags(cand, anchors)
    cand["functions"] = tags

    # ---- linear calibration against the primary anchored truth ----
    calibration = None
    if best_anchor is not None and best_name is not None and abs(best_anchor["pearson_r"]) >= 0.5:
      tt, tv = truth_map[best_name]
      phys = np.interp(np.asarray(times, dtype=float) - float(best_anchor["lag_sec"]), tt, tv)
      if best_anchor["sign"] < 0:
        phys = -phys  # keep factor positive for brake-style signals
      calibration = _fit_linear([float(r) for r in raws], phys.tolist())
      if calibration is not None:
        cand["calibration"] = {
          "truth": best_name,
          "factor": calibration["factor"],
          "offset": calibration["offset"],
          "r2": calibration["r2"],
          "n": calibration["n"],
        }
        evidence.append(
          "fit: " + f"{best_name} factor={calibration['factor']} offset={calibration['offset']} "
          + f"R2={calibration['r2']}"
        )
        if best_name == GPS_SPEED and not cand.get("unit"):
          cand["unit"] = "m/s"
        cand["factor"] = float(calibration["factor"])
        cand["offset"] = float(calibration["offset"])

    # ---- decode self-check ----
    s_dec, decode_evi = _decode_selfcheck(raws)
    evidence.append(decode_evi)

    # ---- mux hint ----
    if kind == "signal" and size <= 8 and 2 <= len(unique) <= 8:
      for other_idx, flags in enumerate(change_flags):
        if other_idx == candidates.index(cand) or not any(flags):
          continue
        # align: flags have len n-1, drop the first raw (no previous frame)
        evi = _mux_evidence(raws[1:], flags)
        if evi:
          evidence.append(evi)
          if not cand.get("flag"):
            cand["flag"] = "mux"
          break

    # ---- confidence ----
    s_stat = _s_stat(cand, raws)
    s_anchor = abs(best_anchor["pearson_r"]) if best_anchor is not None else None
    cand["confidence"] = _confidence(s_stat, s_anchor if truth_usable else None, s_dec)
    cand["evidence"] = evidence
    # Preview carries decoded physical values (post-calibration factor/offset).
    factor = float(cand.get("factor", 1.0) or 1.0)
    offset = float(cand.get("offset", 0.0) or 0.0)
    cand["preview"] = _preview_points(times, [float(r) * factor + offset for r in raws])

  for cand in candidates:
    cand.pop("_unique", None)
  return candidates


def _annotate_candidates(
  address: int,
  frames: list[dict[str, Any]],
  truth: dict[str, Any] | None,
  base: float,
) -> list[dict[str, Any]]:
  """Main entry: statistical candidates for one address + full enrichment."""
  candidates = _statistical_candidates(frames)
  if not candidates:
    return []
  return _enrich_candidates(candidates, frames, truth, base)
